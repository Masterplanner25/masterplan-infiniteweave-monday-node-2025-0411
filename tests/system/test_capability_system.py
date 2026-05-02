from __future__ import annotations

import uuid
from unittest.mock import patch

from AINDY.db.models import AgentEvent, AgentRun, AgentStep, AgentTrustSettings
from AINDY.db.models.system_event import SystemEvent
from AINDY.agents.agent_runtime import approve_run, create_run, execute_run
from AINDY.agents.capability_service import (
    check_tool_capability,
    get_auto_grantable_tools,
    mint_token,
)
from AINDY.core.system_event_types import SystemEventTypes
from AINDY.runtime.nodus_adapter import agent_execute_step


VALID_PLAN = {
    "executive_summary": "Do two safe things.",
    "steps": [
        {
            "tool": "task.create",
            "args": {"name": "Write follow-up"},
            "risk_level": "low",
            "description": "Create a task",
        },
        {
            "tool": "research.query",
            "args": {"query": "prospect research"},
            "risk_level": "low",
            "description": "Research context",
        },
    ],
    "overall_risk": "low",
}


def _make_run(db_session, test_user, *, status: str = "pending_approval", plan: dict | None = None) -> AgentRun:
    plan = plan or VALID_PLAN
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


def test_get_auto_grantable_tools_uses_real_trust_row(db_session, test_user):
    trust = AgentTrustSettings(
        user_id=test_user.id,
        auto_execute_low=False,
        auto_execute_medium=False,
        allowed_auto_grant_tools=["task.create", "research.query", "genesis.message"],
    )
    db_session.add(trust)
    db_session.commit()

    allowed = get_auto_grantable_tools(str(test_user.id), db_session)

    assert allowed == ["research.query", "task.create"]


def test_create_run_auto_mints_capability_token(db_session, test_user):
    trust = AgentTrustSettings(
        user_id=test_user.id,
        auto_execute_low=True,
        auto_execute_medium=False,
        allowed_auto_grant_tools=["task.create", "research.query"],
    )
    db_session.add(trust)
    db_session.commit()

    with patch("AINDY.agents.agent_runtime.generate_plan", return_value=VALID_PLAN):
        run = create_run("follow up with prospect", test_user.id, db_session)

    persisted = db_session.get(AgentRun, uuid.UUID(run["run_id"]))

    assert run is not None
    assert run["status"] == "approved"
    assert persisted.execution_token is not None
    assert persisted.capability_token["granted_tools"] == ["research.query", "task.create"]
    assert persisted.capability_token["allowed_capabilities"] == [
        "execute_flow",
        "external_api_call",
        "manage_tasks",
    ]


def test_approve_run_mints_token_and_executes_real_path(db_session, test_user):
    run = _make_run(db_session, test_user, status="pending_approval")

    def _complete_run(**kwargs):
        live_run = db_session.get(AgentRun, run.id)
        live_run.status = "completed"
        live_run.result = {"steps": [], "loop_enforced": True, "next_action": "review_output"}
        db_session.commit()
        return {"status": "SUCCESS", "run_id": "flow-123"}

    with patch("AINDY.runtime.nodus_adapter.NodusAgentAdapter.execute_with_flow", side_effect=_complete_run):
        approved = approve_run(run.id, test_user.id, db_session)

    db_session.refresh(run)
    approved_event = (
        db_session.query(AgentEvent)
        .filter(AgentEvent.run_id == run.id, AgentEvent.event_type == "APPROVED")
        .one()
    )

    assert approved is not None
    assert run.execution_token is not None
    assert run.capability_token["approval_mode"] == "manual"
    assert run.status == "completed"
    assert approved_event.payload["auto_executed"] is False


def test_execute_run_fails_closed_without_capability_token(db_session, test_user):
    run = _make_run(db_session, test_user, status="approved")

    result = execute_run(run.id, test_user.id, db_session)

    db_session.refresh(run)
    denied_event = (
        db_session.query(AgentEvent)
        .filter(AgentEvent.run_id == run.id, AgentEvent.event_type == "CAPABILITY_DENIED")
        .one()
    )
    mirrored = (
        db_session.query(SystemEvent)
        .filter(SystemEvent.type == "agent.capability_denied", SystemEvent.user_id == test_user.id)
        .one()
    )

    assert result["status"] == "failed"
    assert run.status == "failed"
    assert "Missing scoped capability token" in run.error_message
    assert denied_event.payload["error"] == "missing scoped capability token"
    assert mirrored.payload["run_id"] == str(run.id)


def test_check_tool_capability_uses_real_token_allow_and_deny(db_session, test_user):
    run = _make_run(db_session, test_user, status="approved")
    token = mint_token(str(run.id), test_user.id, VALID_PLAN, db_session, "manual")

    allowed = check_tool_capability(token, str(run.id), test_user.id, "task.create")
    denied = check_tool_capability(token, str(run.id), test_user.id, "arm.generate")

    assert allowed["ok"] is True
    assert denied["ok"] is False
    assert "not granted" in denied["error"]


def test_agent_execute_step_denial_persists_failed_step_and_events(db_session, test_user):
    run = _make_run(db_session, test_user, status="executing")
    token = mint_token(str(run.id), test_user.id, VALID_PLAN, db_session, "manual")

    result = agent_execute_step(
        {
            "agent_run_id": str(run.id),
            "user_id": test_user.id,
            "steps": [
                {
                    "tool": "arm.generate",
                    "args": {"prompt": "Write code"},
                    "risk_level": "medium",
                    "description": "Generate code",
                }
            ],
            "current_step_index": 0,
            "step_results": [],
            "correlation_id": run.correlation_id,
            "execution_token": token,
        },
        {"db": db_session, "trace_id": run.trace_id},
    )

    step = db_session.query(AgentStep).filter(AgentStep.run_id == run.id).one()
    denied = (
        db_session.query(AgentEvent)
        .filter(AgentEvent.run_id == run.id, AgentEvent.event_type == "CAPABILITY_DENIED")
        .one()
    )
    system_event = (
        db_session.query(SystemEvent)
        .filter(SystemEvent.type == SystemEventTypes.AGENT_STEP, SystemEvent.user_id == test_user.id)
        .order_by(SystemEvent.timestamp.desc())
        .first()
    )

    assert result["status"] == "FAILURE"
    assert step.status == "failed"
    assert "Capability denied" in step.error_message
    assert denied.payload["tool_name"] == "arm.generate"
    assert system_event.payload["tool_name"] == "arm.generate"
    assert system_event.payload["status"] == "failed"

