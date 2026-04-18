from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from AINDY.core.execution_pipeline import ExecutionContext, ExecutionPipeline


def _ctx(*, db=None, user_id: str | None = "user-1") -> ExecutionContext:
    ctx = ExecutionContext(
        request_id="trace-reliability-1",
        route_name="agent.run",
        user_id=user_id,
    )
    if db is not None:
        ctx.metadata["db"] = db
    return ctx


def _run(ctx: ExecutionContext, handler):
    return asyncio.run(ExecutionPipeline().run(ctx, handler))


def test_db_backed_authenticated_route_reports_missing_execution_unit():
    ctx = _ctx(db=MagicMock())

    def handler(_ctx):
        return {"ok": True}

    with patch("AINDY.core.execution_gate.require_execution_unit", return_value=None), \
         patch("AINDY.core.system_event_service.emit_system_event", return_value="event-1"), \
         patch("AINDY.core.execution_pipeline.ExecutionPipeline._safe_recall_memory_count", return_value=0):
        result = _run(ctx, handler)

    response = result.to_response()
    side_effects = response["metadata"]["side_effects"]

    assert result.success is True
    assert response["eu_id"] is None
    assert side_effects["execution_unit.create"]["required"] is True
    assert side_effects["execution_unit.create"]["status"] == "missing"
    assert "execution_unit.create" in response["metadata"]["degraded_side_effects"]


def test_required_failed_event_emission_is_visible_on_failure_response():
    ctx = _ctx(db=MagicMock())

    def handler(_ctx):
        raise RuntimeError("handler exploded")

    with patch(
        "AINDY.core.execution_gate.require_execution_unit",
        return_value=SimpleNamespace(id="eu-1"),
    ), patch(
        "AINDY.core.system_event_service.emit_system_event",
        side_effect=RuntimeError("event store down"),
    ), patch(
        "AINDY.core.execution_pipeline.ExecutionPipeline._safe_finalize_eu"
    ), patch(
        "AINDY.core.execution_pipeline.ExecutionPipeline._safe_recall_memory_count",
        return_value=0,
    ):
        result = _run(ctx, handler)

    response = result.to_response()
    failed_event = response["metadata"]["side_effects"]["system_event.execution.failed"]

    assert result.success is False
    assert failed_event["required"] is True
    assert failed_event["status"] == "failed"
    assert "event store down" in failed_event["error"]
    assert "system_event.execution.failed" in response["metadata"]["degraded_side_effects"]


def test_wait_without_execution_unit_fails_closed_in_db_backed_context():
    ctx = _ctx(db=MagicMock())

    def handler(_ctx):
        return {"status": "WAITING", "wait_for": "approval.received"}

    with patch("AINDY.core.execution_gate.require_execution_unit", return_value=None), \
         patch("AINDY.core.system_event_service.emit_system_event", return_value="event-1"), \
         patch("AINDY.core.execution_pipeline.ExecutionPipeline._safe_finalize_eu"):
        result = _run(ctx, handler)

    response = result.to_response()

    assert result.success is False
    assert response["status"] == "error"
    assert response["metadata"]["status_code"] == 500
    assert "eu_id is absent" in response["metadata"]["error"]
    assert result.eu_status != "waiting"


def test_successful_execution_keeps_canonical_response_shape():
    ctx = _ctx(db=None, user_id=None)

    def handler(_ctx):
        return {"value": 1}

    with patch(
        "AINDY.core.execution_pipeline.ExecutionPipeline._safe_recall_memory_count",
        return_value=0,
    ):
        result = _run(ctx, handler)

    response = result.to_response()

    assert set(response) == {
        "status",
        "data",
        "trace_id",
        "eu_id",
        "memory_context_count",
        "metadata",
    }
    assert response["status"] == "success"
    assert response["trace_id"] == "trace-reliability-1"
    assert response["eu_id"] is None
    assert "events" in response["metadata"]
    assert "next_action" in response["metadata"]
    assert response["data"]["value"] == 1
