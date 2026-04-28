from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock

import pytest

from AINDY.platform_layer.llm_client import (
    CircuitBreakerLLMClient,
    LLMCallError,
    LLMCircuitOpenError,
    LLMClient,
    get_llm_client,
)
from AINDY.platform_layer.openai_client import OpenAILLMClient


class _StubLLMClient:
    def __init__(self, responses=None, error: Exception | None = None):
        self._responses = list(responses or [])
        self._error = error
        self.calls = 0

    def chat(self, messages, model=None, temperature=0.7, max_tokens=None) -> str:
        self.calls += 1
        if self._error is not None:
            raise self._error
        if self._responses:
            return self._responses.pop(0)
        return "ok"

    def is_available(self) -> bool:
        return True


def test_openai_llm_client_chat_raises_llm_call_error_when_provider_raises():
    sdk_client = MagicMock()
    sdk_client.chat.completions.create.side_effect = RuntimeError("provider down")
    client = OpenAILLMClient(client=sdk_client, api_key="test")

    with pytest.raises(LLMCallError):
        client.chat([{"role": "user", "content": "hi"}], model="gpt-4o")


def test_circuit_breaker_llm_client_opens_after_five_failures():
    wrapped = CircuitBreakerLLMClient(
        _StubLLMClient(error=LLMCallError("boom")),
        provider="test-provider",
    )

    for _ in range(5):
        with pytest.raises(LLMCallError):
            wrapped.chat([{"role": "user", "content": "hi"}])

    assert wrapped.breaker.state.value == "open"


def test_circuit_breaker_llm_client_raises_when_open():
    wrapped = CircuitBreakerLLMClient(
        _StubLLMClient(error=LLMCallError("boom")),
        provider="test-provider",
    )

    for _ in range(5):
        with pytest.raises(LLMCallError):
            wrapped.chat([{"role": "user", "content": "hi"}])

    with pytest.raises(LLMCircuitOpenError):
        wrapped.chat([{"role": "user", "content": "hi"}])


def test_circuit_breaker_transitions_to_half_open_after_timeout():
    failing = CircuitBreakerLLMClient(
        _StubLLMClient(error=LLMCallError("boom")),
        provider="test-provider",
    )
    for _ in range(5):
        with pytest.raises(LLMCallError):
            failing.chat([{"role": "user", "content": "hi"}])

    probe_client = _StubLLMClient(responses=["recovered"])
    failing.breaker._opened_at = failing.breaker._now() - timedelta(
        seconds=failing.breaker.recovery_timeout_secs + 1
    )
    failing._client = probe_client

    result = failing.chat([{"role": "user", "content": "hi"}])

    assert result == "recovered"
    assert failing.breaker.state.value == "closed"
    assert probe_client.calls == 1


def test_get_llm_client_openai_returns_protocol_instance():
    client = get_llm_client("openai")
    assert isinstance(client, LLMClient)


def test_get_llm_client_deepseek_returns_protocol_instance():
    client = get_llm_client("deepseek")
    assert isinstance(client, LLMClient)
