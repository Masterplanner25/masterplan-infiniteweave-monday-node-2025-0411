from __future__ import annotations

import logging
from typing import Any, Protocol, runtime_checkable

from AINDY.kernel.circuit_breaker import CircuitBreaker, CircuitOpenError


class LLMCallError(Exception):
    """Normalized error for provider-backed LLM calls."""


class LLMCircuitOpenError(CircuitOpenError, LLMCallError):
    """Raised when the LLM circuit breaker rejects a call."""


@runtime_checkable
class LLMClient(Protocol):
    """Abstraction for all LLM provider calls."""

    def chat(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> str:
        """Send a chat completion request. Returns the assistant message text."""
        ...

    def is_available(self) -> bool:
        """Return True if the underlying provider appears reachable."""
        ...


class CircuitBreakerLLMClient:
    """LLMClient wrapper that guards calls with a circuit breaker."""

    def __init__(
        self,
        client: LLMClient,
        *,
        provider: str,
        breaker: CircuitBreaker | None = None,
    ) -> None:
        if not isinstance(client, LLMClient):
            raise TypeError(f"client must satisfy LLMClient protocol, got {type(client)!r}")
        self._client = client
        self._provider = provider
        self._breaker = breaker or CircuitBreaker(
            name=provider,
            failure_threshold=5,
            recovery_timeout_secs=60,
        )

    @property
    def breaker(self) -> CircuitBreaker:
        return self._breaker

    def _call_with_breaker(self, func, *args, **kwargs):
        try:
            return self._breaker.call(func, *args, **kwargs)
        except CircuitOpenError as exc:
            logging.warning("[LLM:%s] circuit open; rejecting call", self._provider)
            raise LLMCircuitOpenError(str(exc)) from exc
        except LLMCallError:
            raise
        except Exception as exc:  # pragma: no cover
            raise LLMCallError(f"{self._provider} call failed") from exc

    def chat(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> str:
        return self._call_with_breaker(
            self._client.chat,
            messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def call_method(self, method_name: str, *args, **kwargs) -> Any:
        method = getattr(self._client, method_name)
        return self._call_with_breaker(method, *args, **kwargs)

    def is_available(self) -> bool:
        return self._client.is_available()


def get_llm_client(provider: str = "openai") -> LLMClient:
    """Return a circuit-breaker-wrapped LLM client for the given provider."""
    normalized = str(provider or "openai").strip().lower()
    if normalized == "openai":
        from AINDY.platform_layer.openai_client import get_openai_client

        return get_openai_client()
    if normalized == "deepseek":
        from AINDY.platform_layer.deepseek_client import get_deepseek_client

        return get_deepseek_client()
    raise ValueError(f"Unsupported LLM provider: {provider}")
