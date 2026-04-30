from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock, patch

import httpx
import prometheus_client as _prom
import pytest

pytestmark = pytest.mark.skipif(
    getattr(_prom, "_is_stub", False),
    reason="requires real prometheus_client: pip install -r AINDY/requirements.txt",
)

from AINDY.kernel.circuit_breaker import CircuitBreaker, CircuitOpenError
from AINDY.platform_layer.deepseek_client import chat_completion_deepseek
from AINDY.platform_layer.metrics import REGISTRY


def _mock_response(content: str = "ok") -> MagicMock:
    resp = MagicMock()
    resp.choices[0].message.content = content
    return resp


def _fresh_breaker() -> CircuitBreaker:
    return CircuitBreaker("deepseek-test", failure_threshold=3, recovery_timeout_secs=60)


def _metric_value(name: str, **labels) -> float:
    value = REGISTRY.get_sample_value(name, labels=labels)
    return float(value or 0.0)


def test_deepseek_call_success_keeps_circuit_closed():
    client = MagicMock()
    success = _mock_response("deepseek ok")
    client.chat.completions.create.return_value = success
    breaker = _fresh_breaker()

    with patch("AINDY.platform_layer.deepseek_client.get_deepseek_circuit_breaker", return_value=breaker):
        result = chat_completion_deepseek(
            client,
            model="gpt-4o",
            messages=[{"role": "user", "content": "hi"}],
            timeout=1.0,
        )

    assert result is success
    assert breaker.state.value == "closed"
    assert breaker.failure_count == 0


def test_deepseek_transient_failure_retries_then_succeeds():
    client = MagicMock()
    success = _mock_response("deepseek ok")
    client.chat.completions.create.side_effect = [
        httpx.ConnectError("down"),
        httpx.ConnectError("down"),
        success,
    ]
    breaker = _fresh_breaker()

    with patch("AINDY.platform_layer.deepseek_client.get_deepseek_circuit_breaker", return_value=breaker):
        result = chat_completion_deepseek(
            client,
            model="gpt-4o",
            messages=[{"role": "user", "content": "hi"}],
            timeout=1.0,
        )

    assert result is success
    assert client.chat.completions.create.call_count == 3
    assert breaker.state.value == "closed"


def test_deepseek_repeated_failure_opens_circuit():
    client = MagicMock()
    client.chat.completions.create.side_effect = httpx.ConnectError("down")
    breaker = _fresh_breaker()

    with patch("AINDY.platform_layer.deepseek_client.get_deepseek_circuit_breaker", return_value=breaker):
        with pytest.raises(httpx.ConnectError):
            chat_completion_deepseek(
                client,
                model="gpt-4o",
                messages=[{"role": "user", "content": "hi"}],
                timeout=1.0,
            )

    assert client.chat.completions.create.call_count == 3
    assert breaker.state.value == "open"
    assert breaker.failure_count == 3


def test_deepseek_open_circuit_short_circuits_calls():
    client = MagicMock()
    breaker = _fresh_breaker()

    def _fail():
        raise httpx.ConnectError("down")

    for _ in range(3):
        with pytest.raises(httpx.ConnectError):
            breaker.call(_fail)

    with patch("AINDY.platform_layer.deepseek_client.get_deepseek_circuit_breaker", return_value=breaker):
        with pytest.raises(CircuitOpenError):
            chat_completion_deepseek(
                client,
                model="gpt-4o",
                messages=[{"role": "user", "content": "hi"}],
                timeout=1.0,
            )

    client.chat.completions.create.assert_not_called()


def test_deepseek_circuit_recovers_after_timeout():
    client = MagicMock()
    success = _mock_response("recovered")
    client.chat.completions.create.side_effect = httpx.ConnectError("down")
    breaker = _fresh_breaker()

    with patch("AINDY.platform_layer.deepseek_client.get_deepseek_circuit_breaker", return_value=breaker):
        with pytest.raises(httpx.ConnectError):
            chat_completion_deepseek(
                client,
                model="gpt-4o",
                messages=[{"role": "user", "content": "hi"}],
                timeout=1.0,
            )

    assert breaker.state.value == "open"
    breaker._opened_at = breaker._now() - timedelta(seconds=breaker.recovery_timeout_secs + 1)
    client.chat.completions.create.side_effect = [success]

    with patch("AINDY.platform_layer.deepseek_client.get_deepseek_circuit_breaker", return_value=breaker):
        result = chat_completion_deepseek(
            client,
            model="gpt-4o",
            messages=[{"role": "user", "content": "hi"}],
            timeout=1.0,
        )

    assert result is success
    assert breaker.state.value == "closed"
    assert breaker.failure_count == 0


def test_deepseek_metrics_increment_for_retries_and_errors():
    retry_before = _metric_value("aindy_deepseek_retries_total", call_type="chat")
    error_before = _metric_value("aindy_deepseek_errors_total", call_type="chat")

    client = MagicMock()
    client.chat.completions.create.side_effect = httpx.ConnectError("down")
    breaker = _fresh_breaker()

    with patch("AINDY.platform_layer.deepseek_client.get_deepseek_circuit_breaker", return_value=breaker):
        with pytest.raises(httpx.ConnectError):
            chat_completion_deepseek(
                client,
                model="gpt-4o",
                messages=[{"role": "user", "content": "hi"}],
                timeout=1.0,
            )

    retry_after = _metric_value("aindy_deepseek_retries_total", call_type="chat")
    error_after = _metric_value("aindy_deepseek_errors_total", call_type="chat")

    assert retry_after - retry_before == 2.0
    assert error_after - error_before == 1.0
