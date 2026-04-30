from __future__ import annotations

import uuid

import pytest

from apps.agent.models.agent_event import AgentEvent
from apps.agent.models.agent_run import AgentRun, AgentStep
from AINDY.db.models.system_event import SystemEvent
from AINDY.db.models.user import User
from AINDY.core.execution_signal_helper import record_agent_event
from AINDY.agents.agent_runtime import get_run_events, replay_run
from tests.fixtures.auth import build_access_token


def _make_run(db_session, test_user, *, status: str = "completed", plan: dict | None = None) -> AgentRun:
    run = AgentRun(
        user_id=test_user.id,
        goal="ship follow-up",
        plan=plan or {
            "executive_summary": "Create a task.",
            "steps": [
                {
                    "tool": "task.create",
                    "args": {"name": "Follow up"},
                    "risk_level": "low",
                    "description": "Create the next task",
                }
            ],
            "overall_risk": "low",
        },
        executive_summary="Create a task.",
        overall_risk="low",
        status=status,
        steps_total=1,
        steps_completed=0,
        correlation_id=f"run_{uuid.uuid4()}",
        trace_id=f"trace_{uuid.uuid4()}",
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)
    return run


def _make_other_user(db_session) -> User:
    other = User(
        id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
        email="other@aindy.test",
        username="other_user",
        hashed_password="hashed",
        is_active=True,
    )
    existing = db_session.get(User, other.id)
    if existing is not None:
        return existing
    db_session.add(other)
    db_session.commit()
    db_session.refresh(other)
    return other


@pytest.mark.postgres
def test_emit_event_persists_agent_and_system_event(db_session, test_user):
    run = _make_run(db_session, test_user)

    record_agent_event(
        run_id=str(run.id),
        user_id=test_user.id,
        event_type="PLAN_CREATED",
        db=db_session,
        correlation_id=run.correlation_id,
        payload={"steps_total": 1},
        required=True,
    )

    agent_event = db_session.query(AgentEvent).filter(AgentEvent.run_id == run.id).one()
    system_event = db_session.query(SystemEvent).filter(SystemEvent.type == "agent.plan_created").one()

    assert agent_event.event_type == "PLAN_CREATED"
    assert agent_event.correlation_id == run.correlation_id
    assert system_event.user_id == test_user.id
    assert system_event.trace_id == run.correlation_id
    assert system_event.payload["run_id"] == str(run.id)


def test_get_run_events_merges_lifecycle_and_steps(db_session, test_user):
    run = _make_run(db_session, test_user)
    record_agent_event(
        run_id=str(run.id),
        user_id=test_user.id,
        event_type="PLAN_CREATED",
        db=db_session,
        correlation_id=run.correlation_id,
        payload={"steps_total": 1},
        required=True,
    )

    step = AgentStep(
        run_id=run.id,
        step_index=0,
        tool_name="task.create",
        tool_args={"name": "Follow up"},
        risk_level="low",
        description="Create the next task",
        status="success",
        result={"task_id": "123"},
        execution_ms=17,
        correlation_id=run.correlation_id,
    )
    db_session.add(step)
    db_session.commit()

    timeline = get_run_events(str(run.id), test_user.id, db_session)

    assert timeline is not None
    assert timeline["correlation_id"] == run.correlation_id
    assert [event["event_type"] for event in timeline["events"]] == [
        "PLAN_CREATED",
        "STEP_EXECUTED",
    ]
    assert timeline["events"][1]["payload"]["tool_name"] == "task.create"


def test_events_endpoint_requires_auth(client, test_user, db_session):
    run = _make_run(db_session, test_user)

    response = client.get(f"/apps/agent/runs/{run.id}/events")

    assert response.status_code in (401, 403)


def test_events_endpoint_returns_user_scoped_timeline(client, auth_headers, db_session, test_user):
    run = _make_run(db_session, test_user)
    record_agent_event(
        run_id=str(run.id),
        user_id=test_user.id,
        event_type="PLAN_CREATED",
        db=db_session,
        correlation_id=run.correlation_id,
        payload={"steps_total": 1},
        required=True,
    )

    response = client.get(f"/apps/agent/runs/{run.id}/events", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    data = body.get("data", body)
    assert data["run_id"] == str(run.id)
    assert data["correlation_id"] == run.correlation_id
    assert data["events"][0]["event_type"] == "PLAN_CREATED"


def test_events_endpoint_forbids_cross_user_access(client, db_session, test_user):
    other_user = _make_other_user(db_session)
    run = _make_run(db_session, other_user)
    foreign_headers = {
        "Authorization": f"Bearer {build_access_token(user_id=test_user.id, email=test_user.email)}"
    }

    response = client.get(f"/apps/agent/runs/{run.id}/events", headers=foreign_headers)

    assert response.status_code == 403


@pytest.mark.postgres
def test_replay_run_persists_replay_event(db_session, test_user):
    original = _make_run(db_session, test_user, status="completed")

    replayed = replay_run(original.id, test_user.id, db_session, mode="same_plan")

    assert replayed is not None
    replay_row = db_session.get(AgentRun, uuid.UUID(replayed["run_id"]))
    replay_event = (
        db_session.query(AgentEvent)
        .filter(AgentEvent.run_id == replay_row.id, AgentEvent.event_type == "REPLAY_CREATED")
        .one()
    )
    system_event = (
        db_session.query(SystemEvent)
        .filter(SystemEvent.type == "agent.replay_created", SystemEvent.user_id == test_user.id)
        .order_by(SystemEvent.timestamp.desc())
        .first()
    )

    assert replay_row.replayed_from_run_id == str(original.id)
    assert replay_event.payload["original_run_id"] == str(original.id)
    assert replay_event.payload["mode"] == "same_plan"
    assert system_event is not None
    assert system_event.payload["mode"] == "same_plan"

