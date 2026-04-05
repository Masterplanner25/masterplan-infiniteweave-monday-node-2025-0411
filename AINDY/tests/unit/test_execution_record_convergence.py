from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4


def test_build_queued_response_includes_execution_record():
    from platform_layer.async_job_service import build_queued_response

    response = build_queued_response("log-1", task_name="agent.create_run", source="agent")

    assert response["status"] == "QUEUED"
    assert response["execution_record"]["run_id"] == "log-1"
    assert response["execution_record"]["trace_id"] == "log-1"
    assert response["result"]["execution_record"]["workflow_type"] == "agent.create_run"


def test_flow_execution_response_includes_execution_record():
    from runtime.flow_engine import _format_execution_response

    response = _format_execution_response(
        status="SUCCESS",
        trace_id="trace-1",
        result={"ok": True},
        run_id="run-1",
        state={"workflow_type": "nodus_execute"},
    )

    assert response["execution_record"]["run_id"] == "run-1"
    assert response["execution_record"]["trace_id"] == "trace-1"
    assert response["execution_record"]["workflow_type"] == "nodus_execute"
    assert response["execution_record"]["source"] == "flow"


def test_run_to_dict_includes_execution_record():
    from agents.agent_runtime import _run_to_dict

    run = SimpleNamespace(
        id=uuid4(),
        user_id=uuid4(),
        agent_type="default",
        goal="Create follow-up",
        executive_summary="summary",
        overall_risk="medium",
        status="executing",
        steps_total=3,
        steps_completed=1,
        plan={"steps": []},
        result={"ok": True},
        error_message=None,
        flow_run_id="flow-1",
        replayed_from_run_id=None,
        execution_token=None,
        capability_token={},
        correlation_id="run_123",
        trace_id="trace-agent-1",
        created_at=datetime.now(timezone.utc),
        approved_at=None,
        started_at=datetime.now(timezone.utc),
        completed_at=None,
    )

    payload = _run_to_dict(run)

    assert payload["execution_record"]["run_id"] == str(run.id)
    assert payload["execution_record"]["trace_id"] == "trace-agent-1"
    assert payload["execution_record"]["execution_unit_id"] == "flow-1"
    assert payload["execution_record"]["source"] == "agent"
