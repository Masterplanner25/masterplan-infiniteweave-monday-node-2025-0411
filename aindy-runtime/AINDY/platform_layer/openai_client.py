"""
Hardened OpenAI client with retry, timeout, and Prometheus metrics.

All production OpenAI calls must go through `chat_completion()` or
`create_embedding()` - never call the client directly.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx
from openai import OpenAI
from tenacity import (
    retry,
    retry_if_exception,
    retry_if_not_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from AINDY.kernel.circuit_breaker import CircuitBreaker, CircuitOpenError
from AINDY.platform_layer.llm_client import (
    CircuitBreakerLLMClient,
    LLMCallError,
    LLMCircuitOpenError,
    LLMClient,
)

logger = logging.getLogger(__name__)

try:
    from AINDY.platform_layer.metrics import openai_errors_total, openai_retries_total

    _METRICS_AVAILABLE = True
except Exception:  # pragma: no cover
    _METRICS_AVAILABLE = False

_RETRYABLE = (
    httpx.TimeoutException,
    httpx.ConnectError,
    httpx.RemoteProtocolError,
)

_openai_breaker = CircuitBreaker(
    name="openai",
    failure_threshold=5,
    recovery_timeout_secs=60,
)


def _is_retryable(exc: BaseException) -> bool:
    """Return True for transient errors worth retrying."""
    if isinstance(exc, LLMCallError) and exc.__cause__ is not None:
        exc = exc.__cause__
    if isinstance(exc, CircuitOpenError):
        return False
    type_name = type(exc).__name__
    if type_name in {"APIConnectionError", "APITimeoutError", "RateLimitError"}:
        return True
    return isinstance(exc, _RETRYABLE)


def _on_retry_chat(retry_state) -> None:
    if _METRICS_AVAILABLE:
        try:
            openai_retries_total.labels(call_type="chat").inc()
        except Exception:
            pass
    logger.warning("[OpenAI] chat retry attempt %d", retry_state.attempt_number)


def _on_retry_embedding(retry_state) -> None:
    if _METRICS_AVAILABLE:
        try:
            openai_retries_total.labels(call_type="embedding").inc()
        except Exception:
            pass
    logger.warning("[OpenAI] embedding retry attempt %d", retry_state.attempt_number)


def _record_openai_terminal_error(call_type: str) -> None:
    if _METRICS_AVAILABLE:
        try:
            openai_errors_total.labels(call_type=call_type).inc()
        except Exception:
            pass


def _extract_message_text(response: Any) -> str:
    try:
        return str(response.choices[0].message.content or "")
    except Exception as exc:  # pragma: no cover
        raise LLMCallError("openai response did not contain assistant text") from exc


class OpenAILLMClient(LLMClient):
    def __init__(
        self,
        *,
        api_key: str | None = None,
        default_model: str = "gpt-4o",
        client: OpenAI | Any | None = None,
        chat_timeout: float | None = None,
        embedding_timeout: float | None = None,
    ) -> None:
        from AINDY.config import settings

        self._api_key = api_key if api_key is not None else settings.OPENAI_API_KEY
        self._default_model = default_model
        self._chat_timeout = settings.OPENAI_CHAT_TIMEOUT_SECONDS if chat_timeout is None else chat_timeout
        self._embedding_timeout = (
            settings.OPENAI_EMBEDDING_TIMEOUT_SECONDS if embedding_timeout is None else embedding_timeout
        )
        self._client = client if client is not None else OpenAI(api_key=self._api_key or "missing-openai-api-key")

    def chat_completion_response(
        self,
        *,
        model: str,
        messages: list[dict],
        timeout: float | None = None,
        **kwargs: Any,
    ) -> Any:
        try:
            return self._client.chat.completions.create(
                model=model,
                messages=messages,
                timeout=self._chat_timeout if timeout is None else timeout,
                **kwargs,
            )
        except Exception as exc:
            raise LLMCallError("openai chat completion failed") from exc

    def create_embedding_response(
        self,
        *,
        input: str | list[str],
        model: str = "text-embedding-3-small",
        timeout: float | None = None,
        **kwargs: Any,
    ) -> Any:
        try:
            return self._client.embeddings.create(
                input=input,
                model=model,
                timeout=self._embedding_timeout if timeout is None else timeout,
                **kwargs,
            )
        except Exception as exc:
            raise LLMCallError("openai embedding request failed") from exc

    def chat(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> str:
        response = self.chat_completion_response(
            model=model or self._default_model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return _extract_message_text(response)

    def is_available(self) -> bool:
        return bool(str(self._api_key or "").strip())


def _legacy_raise(exc: BaseException) -> None:
    if isinstance(exc, LLMCircuitOpenError):
        raise exc
    if isinstance(exc, LLMCallError) and exc.__cause__ is not None:
        raise exc.__cause__ from exc
    raise exc


def _coerce_openai_client(client: Any) -> Any:
    if isinstance(client, CircuitBreakerLLMClient):
        return client
    if isinstance(client, OpenAILLMClient):
        return client
    return OpenAILLMClient(client=client, api_key="")


@retry(
    retry=retry_if_not_exception_type(CircuitOpenError) & retry_if_exception(_is_retryable),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    before_sleep=_on_retry_chat,
    reraise=True,
)
def _chat_completion_with_retry(
    client,
    *,
    model: str,
    messages: list[dict],
    timeout: float = 30.0,
    **kwargs: Any,
) -> Any:
    normalized_client = _coerce_openai_client(client)
    try:
        if isinstance(normalized_client, CircuitBreakerLLMClient):
            return normalized_client.call_method(
                "chat_completion_response",
                model=model,
                messages=messages,
                timeout=timeout,
                **kwargs,
            )
        return get_openai_circuit_breaker().call(
            normalized_client.chat_completion_response,
            model=model,
            messages=messages,
            timeout=timeout,
            **kwargs,
        )
    except (LLMCallError, LLMCircuitOpenError) as exc:
        _legacy_raise(exc)


def chat_completion(
    client,
    *,
    model: str,
    messages: list[dict],
    timeout: float = 30.0,
    **kwargs: Any,
) -> Any:
    try:
        return _chat_completion_with_retry(
            client,
            model=model,
            messages=messages,
            timeout=timeout,
            **kwargs,
        )
    except Exception:
        _record_openai_terminal_error("chat")
        raise


@retry(
    retry=retry_if_not_exception_type(CircuitOpenError) & retry_if_exception(_is_retryable),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    before_sleep=_on_retry_embedding,
    reraise=True,
)
def _create_embedding_with_retry(
    client,
    *,
    input: str | list[str],
    model: str = "text-embedding-3-small",
    timeout: float = 15.0,
    **kwargs: Any,
) -> Any:
    normalized_client = _coerce_openai_client(client)
    try:
        if isinstance(normalized_client, CircuitBreakerLLMClient):
            return normalized_client.call_method(
                "create_embedding_response",
                input=input,
                model=model,
                timeout=timeout,
                **kwargs,
            )
        return get_openai_circuit_breaker().call(
            normalized_client.create_embedding_response,
            input=input,
            model=model,
            timeout=timeout,
            **kwargs,
        )
    except (LLMCallError, LLMCircuitOpenError) as exc:
        _legacy_raise(exc)


def create_embedding(
    client,
    *,
    input: str | list[str],
    model: str = "text-embedding-3-small",
    timeout: float = 15.0,
    **kwargs: Any,
) -> Any:
    try:
        return _create_embedding_with_retry(
            client,
            input=input,
            model=model,
            timeout=timeout,
            **kwargs,
        )
    except Exception:
        _record_openai_terminal_error("embedding")
        raise


def get_openai_circuit_breaker() -> CircuitBreaker:
    return _openai_breaker


def get_openai_client() -> LLMClient:
    """Lazily create and cache the OpenAI client using the configured API key."""
    global _client
    if _client is None:
        provider = OpenAILLMClient()
        _client = CircuitBreakerLLMClient(
            provider,
            provider="openai",
            breaker=get_openai_circuit_breaker(),
        )
    return _client


_client: LLMClient | None = None
