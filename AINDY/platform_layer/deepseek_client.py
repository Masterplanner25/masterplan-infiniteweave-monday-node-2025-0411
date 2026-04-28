"""
Hardened DeepSeek client with retry, timeout, and Prometheus metrics.

All production DeepSeek calls must go through ``chat_completion_deepseek()``.
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
    from AINDY.platform_layer.metrics import deepseek_errors_total, deepseek_retries_total

    _METRICS_AVAILABLE = True
except Exception:  # pragma: no cover
    _METRICS_AVAILABLE = False

_RETRYABLE = (
    httpx.TimeoutException,
    httpx.ConnectError,
    httpx.RemoteProtocolError,
)

_deepseek_breaker = CircuitBreaker(
    name="deepseek",
    failure_threshold=5,
    recovery_timeout_secs=60,
)


def _is_retryable(exc: BaseException) -> bool:
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
            deepseek_retries_total.labels(call_type="chat").inc()
        except Exception:
            pass
    logger.warning("[DeepSeek] chat retry attempt %d", retry_state.attempt_number)


def _record_deepseek_terminal_error(call_type: str) -> None:
    if _METRICS_AVAILABLE:
        try:
            deepseek_errors_total.labels(call_type=call_type).inc()
        except Exception:
            pass


def _extract_message_text(response: Any) -> str:
    try:
        return str(response.choices[0].message.content or "")
    except Exception as exc:  # pragma: no cover
        raise LLMCallError("deepseek response did not contain assistant text") from exc


class DeepSeekLLMClient(LLMClient):
    def __init__(
        self,
        *,
        api_key: str | None = None,
        default_model: str = "deepseek-chat",
        client: Any | None = None,
        chat_timeout: float = 30.0,
    ) -> None:
        from AINDY.config import settings

        self._api_key = api_key if api_key is not None else settings.DEEPSEEK_API_KEY
        self._default_model = default_model
        self._chat_timeout = chat_timeout
        self._client = client if client is not None else OpenAI(api_key=self._api_key or "missing-deepseek-api-key")

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
            raise LLMCallError("deepseek chat completion failed") from exc

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


def _coerce_deepseek_client(client: Any) -> Any:
    if isinstance(client, CircuitBreakerLLMClient):
        return client
    if isinstance(client, DeepSeekLLMClient):
        return client
    return DeepSeekLLMClient(client=client, api_key="")


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
    normalized_client = _coerce_deepseek_client(client)
    try:
        if isinstance(normalized_client, CircuitBreakerLLMClient):
            return normalized_client.call_method(
                "chat_completion_response",
                model=model,
                messages=messages,
                timeout=timeout,
                **kwargs,
            )
        return get_deepseek_circuit_breaker().call(
            normalized_client.chat_completion_response,
            model=model,
            messages=messages,
            timeout=timeout,
            **kwargs,
        )
    except (LLMCallError, LLMCircuitOpenError) as exc:
        _legacy_raise(exc)


def chat_completion_deepseek(
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
        _record_deepseek_terminal_error("chat")
        raise


def get_deepseek_circuit_breaker() -> CircuitBreaker:
    return _deepseek_breaker


def get_deepseek_client() -> LLMClient:
    global _client
    if _client is None:
        provider = DeepSeekLLMClient()
        _client = CircuitBreakerLLMClient(
            provider,
            provider="deepseek",
            breaker=get_deepseek_circuit_breaker(),
        )
    return _client


_client: LLMClient | None = None
