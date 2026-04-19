"""Unit tests for Prometheus metrics instrumentation."""
from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from prometheus_client import CollectorRegistry, Counter, Histogram

from AINDY.core.execution_pipeline import ExecutionContext, ExecutionPipeline


# ── Isolated registry helpers ─────────────────────────────────────────────────

def _make_isolated_metrics():
    """Return fresh Counter and Histogram on an isolated registry."""
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
    return total, duration, reg


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
    """Return a list of patches that stub out all DB/EU side effects."""
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


# ── Pipeline counter tests ────────────────────────────────────────────────────

def test_execution_total_increments_on_success():
    """Successful handler increments status='success' counter by 1."""
    total, duration, reg = _make_isolated_metrics()
    pipeline = ExecutionPipeline()
    ctx = ExecutionContext(request_id="r1", route_name="test.route")

    patches = _pipeline_mocks(pipeline) + [
        patch("AINDY.core.execution_pipeline.execution_total", total),
        patch("AINDY.core.execution_pipeline.execution_duration_seconds", duration),
        patch("AINDY.core.execution_pipeline._METRICS_AVAILABLE", True),
    ]
    with _apply_patches(patches):
        result = _run_pipeline(pipeline, ctx, lambda c: {"data": "ok"})

    assert result.success is True
    # prometheus_client strips _total from the metric name; sample is named aindy_execution_total
    val = _sample_value(reg, "aindy_execution_total", {"route": "test.route", "status": "success"})
    assert val == 1.0


def test_execution_total_increments_on_failure():
    """Handler that raises increments status='failed' counter by 1."""
    total, duration, reg = _make_isolated_metrics()
    pipeline = ExecutionPipeline()
    ctx = ExecutionContext(request_id="r2", route_name="test.route")

    def _failing_handler(_ctx):
        raise ValueError("boom")

    patches = _pipeline_mocks(pipeline) + [
        patch("AINDY.core.execution_pipeline.execution_total", total),
        patch("AINDY.core.execution_pipeline.execution_duration_seconds", duration),
        patch("AINDY.core.execution_pipeline._METRICS_AVAILABLE", True),
    ]
    with _apply_patches(patches):
        result = _run_pipeline(pipeline, ctx, _failing_handler)

    assert result.success is False
    val = _sample_value(reg, "aindy_execution_total", {"route": "test.route", "status": "failed"})
    assert val == 1.0


def test_execution_duration_observed():
    """Successful handler produces at least one histogram observation."""
    total, duration, reg = _make_isolated_metrics()
    pipeline = ExecutionPipeline()
    ctx = ExecutionContext(request_id="r3", route_name="test.route")

    patches = _pipeline_mocks(pipeline) + [
        patch("AINDY.core.execution_pipeline.execution_total", total),
        patch("AINDY.core.execution_pipeline.execution_duration_seconds", duration),
        patch("AINDY.core.execution_pipeline._METRICS_AVAILABLE", True),
    ]
    with _apply_patches(patches):
        asyncio.run(pipeline.run(ctx, lambda c: {"data": "ok"}))

    # Histogram count sample tells us how many observations were made
    count = _sample_value(
        reg,
        "aindy_execution_duration_seconds_count",
        {"route": "test.route"},
    )
    assert count >= 1.0


# ── /metrics endpoint tests ───────────────────────────────────────────────────

def test_metrics_endpoint_accessible():
    """GET /metrics returns 200 and body contains aindy_execution_total."""
    from AINDY.main import app

    client = TestClient(app, raise_server_exceptions=False)
    # TestClient connects from 127.0.0.1 — passes the loopback IP check
    response = client.get("/metrics")
    assert response.status_code == 200
    assert b"aindy_execution_total" in response.content


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


# ── Helpers ───────────────────────────────────────────────────────────────────

from contextlib import ExitStack


def _apply_patches(patches):
    """Context manager that activates a list of patch objects."""
    stack = ExitStack()
    for p in patches:
        stack.enter_context(p)
    return stack
