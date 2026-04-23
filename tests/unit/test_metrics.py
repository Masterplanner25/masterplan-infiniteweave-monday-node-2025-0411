"""Unit tests for Prometheus metrics instrumentation."""
from __future__ import annotations

import asyncio
from contextlib import ExitStack
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

from AINDY.core.execution_pipeline import ExecutionContext, ExecutionPipeline
from AINDY.kernel.circuit_breaker import CircuitBreaker


def _make_isolated_metrics():
    """Return fresh pipeline metrics on an isolated registry."""
    reg = CollectorRegistry(auto_describe=True)
    total = Counter(
        "aindy_execution_total",
        "Total executions by route and outcome",
        ["route", "status"],
        registry=reg,
    )
    duration = Histogram(
        "aindy_execution_duration_seconds",
        "Execution handler duration in seconds",
        ["route"],
        buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0],
        registry=reg,
    )
    active = Gauge(
        "aindy_active_executions_total",
        "Total active executions across all tenants (in-memory counter)",
        registry=reg,
    )
    return total, duration, active, reg


def _make_isolated_openai_metrics():
    """Return fresh OpenAI metrics on an isolated registry."""
    reg = CollectorRegistry(auto_describe=True)
    retries = Counter(
        "aindy_openai_retries_total",
        "Total OpenAI call retries",
        ["call_type"],
        registry=reg,
    )
    errors = Counter(
        "aindy_openai_errors_total",
        "Total OpenAI call failures after all retries exhausted",
        ["call_type"],
        registry=reg,
    )
    return retries, errors, reg


def _make_isolated_circuit_breaker_metric():
    reg = CollectorRegistry(auto_describe=True)
    gauge = Gauge(
        "aindy_ai_circuit_breaker_state",
        "Circuit breaker state (0=closed, 1=half_open, 2=open)",
        ["provider"],
        registry=reg,
    )
    return gauge, reg


def _fresh_openai_breaker() -> CircuitBreaker:
    return CircuitBreaker("openai-test", failure_threshold=3, recovery_timeout_secs=60)


def _sample_value(registry, sample_name: str, labels: dict) -> float:
    """Return the value of the first sample matching sample_name and labels."""
    for metric in registry.collect():
        for sample in metric.samples:
            if sample.name == sample_name and all(
                sample.labels.get(k) == v for k, v in labels.items()
            ):
                return sample.value
    return 0.0


def _pipeline_mocks(pipeline):
    """Return a list of patches that stub out DB/EU side effects."""
    return [
        patch.object(pipeline, "_safe_emit_event", return_value=None),
        patch.object(pipeline, "_safe_set_parent_event", return_value=None),
        patch.object(pipeline, "_safe_set_pipeline_active", return_value=None),
        patch.object(pipeline, "_safe_set_current_execution_context", return_value=None),
        patch.object(pipeline, "_safe_require_eu", return_value=None),
        patch.object(pipeline, "_safe_check_quota", return_value=True),
        patch.object(pipeline, "_safe_rm_mark_started"),
        patch.object(pipeline, "_safe_rm_record_and_complete"),
        patch.object(pipeline, "_safe_finalize_eu"),
        patch.object(pipeline, "_safe_reset_current_execution_context"),
        patch.object(pipeline, "_safe_reset_pipeline_active"),
        patch.object(pipeline, "_safe_reset_parent_event"),
        patch.object(pipeline, "_set_event_refs"),
    ]


def _run_pipeline(pipeline, ctx, handler):
    """Run the async pipeline in a fresh event loop and return the result."""
    return asyncio.run(pipeline.run(ctx, handler))


def _apply_patches(patches):
    """Context manager that activates a list of patch objects."""
    stack = ExitStack()
    for p in patches:
        stack.enter_context(p)
    return stack


def test_execution_total_increments_on_success():
    """Successful handler increments success counter and clears active gauge."""
    total, duration, active, reg = _make_isolated_metrics()
    pipeline = ExecutionPipeline()
    ctx = ExecutionContext(request_id="r1", route_name="test.route")

    async def _handler(_ctx):
        assert _sample_value(reg, "aindy_active_executions_total", {}) == 1.0
        return {"data": "ok"}

    patches = _pipeline_mocks(pipeline) + [
        patch("AINDY.core.execution_pipeline.execution_total", total),
        patch("AINDY.core.execution_pipeline.execution_duration_seconds", duration),
        patch("AINDY.core.execution_pipeline.aindy_active_executions_total", active),
        patch("AINDY.core.execution_pipeline._METRICS_AVAILABLE", True),
    ]
    with _apply_patches(patches):
        result = _run_pipeline(pipeline, ctx, _handler)

    assert result.success is True
    assert _sample_value(reg, "aindy_active_executions_total", {}) == 0.0
    val = _sample_value(
        reg,
        "aindy_execution_total",
        {"route": "test.route", "status": "success"},
    )
    assert val == 1.0


def test_active_executions_decrements_on_exception():
    """Active execution gauge decrements even when the handler raises."""
    total, duration, active, reg = _make_isolated_metrics()
    pipeline = ExecutionPipeline()
    ctx = ExecutionContext(request_id="r2", route_name="test.route")

    async def _failing_handler(_ctx):
        assert _sample_value(reg, "aindy_active_executions_total", {}) == 1.0
        raise ValueError("boom")

    patches = _pipeline_mocks(pipeline) + [
        patch("AINDY.core.execution_pipeline.execution_total", total),
        patch("AINDY.core.execution_pipeline.execution_duration_seconds", duration),
        patch("AINDY.core.execution_pipeline.aindy_active_executions_total", active),
        patch("AINDY.core.execution_pipeline._METRICS_AVAILABLE", True),
    ]
    with _apply_patches(patches):
        result = _run_pipeline(pipeline, ctx, _failing_handler)

    assert result.success is False
    assert _sample_value(reg, "aindy_active_executions_total", {}) == 0.0
    val = _sample_value(
        reg,
        "aindy_execution_total",
        {"route": "test.route", "status": "failed"},
    )
    assert val == 1.0


def test_execution_duration_observed():
    """Successful handler records a histogram observation."""
    total, duration, active, reg = _make_isolated_metrics()
    pipeline = ExecutionPipeline()
    ctx = ExecutionContext(request_id="r3", route_name="test.route")
    duration_child = duration.labels(route="test.route")

    patches = _pipeline_mocks(pipeline) + [
        patch("AINDY.core.execution_pipeline.execution_total", total),
        patch("AINDY.core.execution_pipeline.execution_duration_seconds", duration),
        patch("AINDY.core.execution_pipeline.aindy_active_executions_total", active),
        patch("AINDY.core.execution_pipeline._METRICS_AVAILABLE", True),
    ]
    with patch.object(duration_child, "observe", wraps=duration_child.observe) as observe_spy:
        with _apply_patches(patches):
            asyncio.run(pipeline.run(ctx, lambda c: {"data": "ok"}))

    observe_spy.assert_called_once()
    count = _sample_value(
        reg,
        "aindy_execution_duration_seconds_count",
        {"route": "test.route"},
    )
    assert count >= 1.0


def test_openai_errors_increment_on_terminal_failure():
    """Terminal OpenAI failures increment the error counter."""
    _, errors, reg = _make_isolated_openai_metrics()

    class _AlwaysFailChat:
        def create(self, **_kwargs):
            raise RuntimeError("chat failed")

    class _FakeClient:
        def __init__(self):
            self.chat = type("_ChatNamespace", (), {"completions": _AlwaysFailChat()})()

    from AINDY.platform_layer import openai_client

    with pytest.raises(RuntimeError, match="chat failed"):
        with _apply_patches([
            patch("AINDY.platform_layer.openai_client.openai_errors_total", errors),
            patch("AINDY.platform_layer.openai_client.get_openai_circuit_breaker", return_value=_fresh_openai_breaker()),
            patch("AINDY.platform_layer.openai_client._METRICS_AVAILABLE", True),
        ]):
            openai_client.chat_completion(
                _FakeClient(),
                model="gpt-test",
                messages=[{"role": "user", "content": "ping"}],
            )

    val = _sample_value(reg, "aindy_openai_errors_total", {"call_type": "chat"})
    assert val == 1.0


def test_circuit_breaker_state_metric_updates_on_transitions():
    from AINDY.kernel.circuit_breaker import CircuitState

    gauge, reg = _make_isolated_circuit_breaker_metric()
    breaker = CircuitBreaker("openai-test", failure_threshold=1, recovery_timeout_secs=60)

    base_now = breaker._now()
    timeline = {"now": base_now}
    breaker._now = lambda: timeline["now"]  # type: ignore[method-assign]

    with patch("AINDY.platform_layer.metrics.ai_circuit_breaker_state", gauge):
        breaker.reset()
        assert _sample_value(reg, "aindy_ai_circuit_breaker_state", {"provider": "openai-test"}) == 0.0

        with pytest.raises(RuntimeError):
            breaker.call(lambda: (_ for _ in ()).throw(RuntimeError("down")))

        assert breaker.state == CircuitState.OPEN
        assert _sample_value(reg, "aindy_ai_circuit_breaker_state", {"provider": "openai-test"}) == 2.0

        from datetime import timedelta

        timeline["now"] = base_now + timedelta(seconds=61)
        assert breaker.call(lambda: "ok") == "ok"
        assert breaker.state == CircuitState.CLOSED
        assert _sample_value(reg, "aindy_ai_circuit_breaker_state", {"provider": "openai-test"}) == 0.0


def test_metrics_endpoint_accessible():
    """GET /metrics returns 200 and body contains aindy_execution_total."""
    from AINDY.main import app

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/metrics")
    assert response.status_code == 200
    assert b"aindy_execution_total" in response.content


def test_metrics_endpoint_exposes_infinity_score_write_failures_counter():
    from AINDY.main import app
    from AINDY.platform_layer.metrics import infinity_score_write_failures_total

    infinity_score_write_failures_total.labels(reason="concurrent_write").inc()

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/metrics")
    assert response.status_code == 200
    assert b"aindy_infinity_score_write_failures_total" in response.content


def test_metrics_endpoint_blocked_without_auth():
    """GET /metrics from an external IP without a valid key returns 403."""
    from AINDY import main as _main_module
    from AINDY.main import app

    original_key = _main_module._AINDY_SERVICE_KEY
    try:
        _main_module._AINDY_SERVICE_KEY = "test-secret-key"
        client = TestClient(app, raise_server_exceptions=False)
        with patch("AINDY.main._is_metrics_ip_allowed", return_value=False):
            response = client.get("/metrics")
        assert response.status_code == 403
    finally:
        _main_module._AINDY_SERVICE_KEY = original_key
