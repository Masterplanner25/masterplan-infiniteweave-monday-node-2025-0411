from __future__ import annotations

import random
import uuid
from unittest.mock import patch

from AINDY.db.models.agent_event import AgentEvent
from AINDY.db.models.agent_run import AgentRun, AgentStep
from AINDY.db.models.system_event import SystemEvent
from AINDY.agents.agent_runtime import execute_run
from AINDY.agents.capability_service import mint_token
from AINDY.core.system_event_types import SystemEventTypes
from AINDY.runtime.nodus_adapter import (
    NodusAgentAdapter,
    agent_execute_step,
    agent_finalize_run,
    agent_validate_steps,
)


def _make_run(db_session, test_user, *, status: str = "approved", plan: dict | None = None) -> AgentRun:
    plan = plan or {
        "executive_summary": "Create a task and finish.",
        "steps": [
            {
                "tool": "task.create",
                "args": {"name": "Follow up"},
                "risk_level": "low",
                "description": "Create the next task",
            }
        ],
        "overall_risk": "low",
    }
    run = AgentRun(
        user_id=test_user.id,
        goal="follow up with prospect",
        plan=plan,
        executive_summary=plan["executive_summary"],
        overall_risk=plan["overall_risk"],
        status=status,
        steps_total=len(plan["steps"]),
        steps_completed=0,
        correlation_id=f"run_{uuid.uuid4()}",
        trace_id=f"trace_{uuid.uuid4()}",
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)
    return run


def test_agent_validate_steps_enforces_non_empty_plan():
    ok = agent_validate_steps(
        {"agent_run_id": "run-1", "user_id": "u1", "steps": [{"tool": "task.create"}]},
        {},
    )
    failure = agent_validate_steps({"agent_run_id": "run-1", "user_id": "u1", "steps": []}, {})

    assert ok["status"] == "SUCCESS"
    assert ok["output_patch"]["current_step_index"] == 0
    assert failure["status"] == "FAILURE"
    assert "no steps" in failure["error"].lower()


def test_agent_execute_step_persists_step_and_updates_run(db_session, test_user):
    run = _make_run(db_session, test_user, status="executing")

    state = {
        "agent_run_id": str(run.id),
        "user_id": test_user.id,
        "steps": run.plan["steps"],
        "current_step_index": 0,
        "step_results": [],
        "correlation_id": run.correlation_id,
    }

    with patch("runtime.nodus_adapter.execute_tool", return_value={"success": True, "result": {"task_id": "t1"}}):
        result = agent_execute_step(state, {"db": db_session, "trace_id": run.trace_id})

    db_session.refresh(run)
    step = db_session.query(AgentStep).filter(AgentStep.run_id == run.id).one()
    system_event = (
        db_session.query(SystemEvent)
        .filter(SystemEvent.type == SystemEventTypes.AGENT_STEP, SystemEvent.user_id == test_user.id)
        .one()
    )

    assert result["status"] == "SUCCESS"
    assert run.steps_completed == 1
    assert run.current_step == 1
    assert step.status == "success"
    assert step.result["task_id"] == "t1"
    assert system_event.payload["tool_name"] == "task.create"
    assert system_event.payload["status"] == "success"


def test_agent_finalize_run_marks_completed_and_emits_events(db_session, test_user):
    run = _make_run(db_session, test_user, status="executing")

    with patch(
        "domain.infinity_orchestrator.execute",
        return_value={"next_action": "ship_the_followup"},
    ):
        result = agent_finalize_run(
            {
                "agent_run_id": str(run.id),
                "user_id": test_user.id,
                "step_results": [{"step_index": 0, "tool": "task.create", "status": "success"}],
                "correlation_id": run.correlation_id,
            },
            {"db": db_session},
        )

    db_session.refresh(run)
    lifecycle = (
        db_session.query(AgentEvent)
        .filter(AgentEvent.run_id == run.id, AgentEvent.event_type == "COMPLETED")
        .one()
    )
    mirrored = (
        db_session.query(SystemEvent)
        .filter(SystemEvent.type == "agent.completed", SystemEvent.user_id == test_user.id)
        .one()
    )

    assert result["status"] == "SUCCESS"
    assert run.status == "completed"
    assert run.result["loop_enforced"] is True
    assert run.result["next_action"] == "ship_the_followup"
    assert lifecycle.payload["steps_completed"] == 1
    assert mirrored.payload["run_id"] == str(run.id)


def test_execute_run_persists_started_and_completed_state(db_session, test_user):
    random.seed(42)
    run = _make_run(db_session, test_user, status="approved")
    run.capability_token = mint_token(str(run.id), test_user.id, run.plan, db_session, "manual")
    run.execution_token = run.capability_token["execution_token"]
    db_session.commit()

    def _complete_run(**kwargs):
        live_run = db_session.get(AgentRun, run.id)
        live_run.status = "completed"
        live_run.flow_run_id = "flow-123"
        live_run.result = {"steps": [], "loop_enforced": True, "next_action": "review_output"}
        db_session.commit()
        return {"status": "SUCCESS", "run_id": "flow-123"}

    with patch("runtime.nodus_execution_service.execute_agent_run_via_nodus", side_effect=_complete_run):
        result = execute_run(run.id, test_user.id, db_session)

    db_session.refresh(run)
    started = (
        db_session.query(AgentEvent)
        .filter(AgentEvent.run_id == run.id, AgentEvent.event_type == "EXECUTION_STARTED")
        .one()
    )

    assert result is not None
    assert run.status == "completed"
    assert run.flow_run_id == "flow-123"
    assert started.correlation_id == run.correlation_id


def test_execute_with_flow_denies_missing_capability_token(db_session, test_user):
    run = _make_run(db_session, test_user, status="executing")

    result = NodusAgentAdapter.execute_with_flow(
        run_id=str(run.id),
        plan=run.plan,
        user_id=test_user.id,
        db=db_session,
        correlation_id=run.correlation_id,
        execution_token=None,
    )

    db_session.refresh(run)
    denied = (
        db_session.query(AgentEvent)
        .filter(AgentEvent.run_id == run.id, AgentEvent.event_type == "CAPABILITY_DENIED")
        .one()
    )

    assert result["status"] == "FAILED"
    assert run.status == "failed"
    assert "missing scoped capability token" in result["error"]
    assert denied.payload["capability"] == "execute_flow"


