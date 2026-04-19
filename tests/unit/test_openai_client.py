"""Unit tests for the hardened OpenAI wrapper in platform_layer/openai_client.py."""
from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import httpx
import pytest

from AINDY.kernel.circuit_breaker import CircuitBreaker, CircuitOpenError
from AINDY.platform_layer.openai_client import chat_completion, create_embedding


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mock_response(content: str = "ok") -> MagicMock:
    resp = MagicMock()
    resp.choices[0].message.content = content
    return resp


def _mock_embedding_response() -> MagicMock:
    resp = MagicMock()
    resp.data[0].embedding = [0.1] * 10
    return resp


def _fresh_breaker() -> CircuitBreaker:
    return CircuitBreaker("openai-test", failure_threshold=3, recovery_timeout_secs=60)


# ── chat_completion tests ─────────────────────────────────────────────────────

def test_chat_completion_retries_on_connection_error():
    """Wrapper retries on ConnectError and returns the successful result."""
    client = MagicMock()
    success = _mock_response("plan result")
    client.chat.completions.create.side_effect = [
        httpx.ConnectError("refused"),
        httpx.ConnectError("refused"),
        success,
    ]

    with patch("AINDY.platform_layer.openai_client.get_openai_circuit_breaker", return_value=_fresh_breaker()):
        result = chat_completion(
            client,
            model="gpt-4o",
            messages=[{"role": "user", "content": "hi"}],
            timeout=1.0,
        )

    assert result is success
    assert client.chat.completions.create.call_count == 3


def test_chat_completion_raises_after_max_retries():
    """Wrapper re-raises after exhausting 3 attempts."""
    client = MagicMock()
    client.chat.completions.create.side_effect = httpx.ConnectError("down")

    with patch("AINDY.platform_layer.openai_client.get_openai_circuit_breaker", return_value=_fresh_breaker()):
        with pytest.raises(httpx.ConnectError):
            chat_completion(
                client,
                model="gpt-4o",
                messages=[{"role": "user", "content": "hi"}],
                timeout=1.0,
            )

    assert client.chat.completions.create.call_count == 3


def test_chat_completion_passes_timeout():
    """timeout kwarg is forwarded to the underlying client call."""
    client = MagicMock()
    client.chat.completions.create.return_value = _mock_response()

    with patch("AINDY.platform_layer.openai_client.get_openai_circuit_breaker", return_value=_fresh_breaker()):
        chat_completion(
            client,
            model="gpt-4o",
            messages=[{"role": "user", "content": "hi"}],
            timeout=42.0,
        )

    client.chat.completions.create.assert_called_once_with(
        model="gpt-4o",
        messages=[{"role": "user", "content": "hi"}],
        timeout=42.0,
    )


# ── create_embedding tests ────────────────────────────────────────────────────

def test_embedding_retries_on_timeout():
    """create_embedding retries on TimeoutException and returns on success."""
    client = MagicMock()
    success = _mock_embedding_response()
    client.embeddings.create.side_effect = [
        httpx.TimeoutException("timeout"),
        httpx.TimeoutException("timeout"),
        success,
    ]

    with patch("AINDY.platform_layer.openai_client.get_openai_circuit_breaker", return_value=_fresh_breaker()):
        result = create_embedding(
            client,
            input="embed this",
            model="text-embedding-3-small",
            timeout=1.0,
        )

    assert result is success
    assert client.embeddings.create.call_count == 3


def test_chat_completion_does_not_retry_when_circuit_is_open():
    client = MagicMock()
    breaker = _fresh_breaker()

    def _fail():
        raise httpx.ConnectError("down")

    for _ in range(3):
        with pytest.raises(httpx.ConnectError):
            breaker.call(_fail)

    with patch("AINDY.platform_layer.openai_client.get_openai_circuit_breaker", return_value=breaker):
        with pytest.raises(CircuitOpenError):
            chat_completion(
                client,
                model="gpt-4o",
                messages=[{"role": "user", "content": "hi"}],
                timeout=1.0,
            )

    client.chat.completions.create.assert_not_called()
