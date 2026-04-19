"""
Hardened OpenAI client with retry, timeout, and Prometheus metrics.

All production OpenAI calls must go through `chat_completion()` or
`create_embedding()` — never call the client directly.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx
from openai import OpenAI
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

try:
    from AINDY.platform_layer.metrics import openai_retries_total, openai_errors_total
    _METRICS_AVAILABLE = True
except Exception:  # pragma: no cover
    _METRICS_AVAILABLE = False

# Exceptions that are safe to retry (transient)
_RETRYABLE = (
    httpx.TimeoutException,
    httpx.ConnectError,
    httpx.RemoteProtocolError,
)


def _is_retryable(exc: BaseException) -> bool:
    """Return True for transient errors worth retrying."""
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


@retry(
    retry=retry_if_exception(_is_retryable),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    before_sleep=_on_retry_chat,
    reraise=True,
)
def chat_completion(
    client,
    *,
    model: str,
    messages: list[dict],
    timeout: float = 30.0,
    **kwargs: Any,
) -> Any:
    """Call chat completions with retry and timeout."""
    return client.chat.completions.create(
        model=model,
        messages=messages,
        timeout=timeout,
        **kwargs,
    )


@retry(
    retry=retry_if_exception(_is_retryable),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    before_sleep=_on_retry_embedding,
    reraise=True,
)
def create_embedding(
    client,
    *,
    input: str | list[str],
    model: str = "text-embedding-3-small",
    timeout: float = 15.0,
    **kwargs: Any,
) -> Any:
    """Call embeddings with retry and timeout."""
    return client.embeddings.create(
        input=input,
        model=model,
        timeout=timeout,
        **kwargs,
    )


def get_openai_client() -> OpenAI:
    """Lazily create and cache the OpenAI client using the configured API key."""
    global _client
    if _client is None:
        from AINDY.config import settings
        _client = OpenAI(api_key=settings.OPENAI_API_KEY)
    return _client


_client: OpenAI | None = None
