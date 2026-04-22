"""
Hardened DeepSeek client with retry, timeout, and Prometheus metrics.

All production DeepSeek calls must go through ``chat_completion_deepseek()``.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception,
    retry_if_not_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from AINDY.kernel.circuit_breaker import CircuitOpenError, get_deepseek_circuit_breaker as _kernel_get_deepseek_circuit_breaker
from AINDY.platform_layer.openai_client import OpenAI

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


def _is_retryable(exc: BaseException) -> bool:
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
    cb = get_deepseek_circuit_breaker()
    return cb.call(
        client.chat.completions.create,
        model=model,
        messages=messages,
        timeout=timeout,
        **kwargs,
    )


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


def get_deepseek_client() -> Any:
    global _client
    if _client is None:
        from AINDY.config import settings

        _client = OpenAI(api_key=settings.DEEPSEEK_API_KEY)
    return _client


_client: Any | None = None


def get_deepseek_circuit_breaker():
    return _kernel_get_deepseek_circuit_breaker()
