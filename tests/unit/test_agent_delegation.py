from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import patch

from AINDY.agents.agent_coordinator import dispatch_delegated_run, serialize_agent_registry
from AINDY.db.models.agent_registry import AgentRegistry
from AINDY.db.models.agent_run import AgentRun


def _unwrap(payload):
    if isinstance(payload, dict) and "data" in payload:
        return payload["data"]
    return payload


def _make_parent_run(db_session, test_user, *, status: str = "approved") -> AgentRun:
    run = AgentRun(
        user_id=test_user.id,
        agent_type="default",
        goal="delegate this work",
        plan={"steps": [{"tool": "task.create", "args": {"name": "Delegated Task"}}]},
        executive_summary="delegation test parent",
        overall_risk="low",
        status=status,
        steps_total=1,
        steps_completed=0,
        correlation_id=f"run_{uuid.uuid4()}",
        trace_id=f"trace-{uuid.uuid4()}",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)
    return run


def _make_agent_registry_row(db_session) -> AgentRegistry:
    row = AgentRegistry(
        agent_id=uuid.uuid4(),
        capabilities=["task.create"],
        current_state={"status": "idle"},
        load=0.2,
        health_status="healthy",
        last_seen=datetime.now(timezone.utc),
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


def test_dispatch_delegated_run_creates_child_run(db_session, test_user):
    parent = _make_parent_run(db_session, test_user)
    agent = _make_agent_registry_row(db_session)

    with patch("AINDY.agents.agent_coordinator.publish_operation_request", return_value=None):
        result = dispatch_delegated_run(
            db_session,
            parent_run=parent,
            selected_agent=serialize_agent_registry(agent),
            delegation_mode="delegate",
            user_id=str(test_user.id),
            trace_id=parent.trace_id,
        )

    assert result is not None
    child = db_session.get(AgentRun, uuid.UUID(result["run_id"]))
    assert child is not None
    assert child.parent_run_id == parent.id
    assert child.coordination_role == "delegate"
    assert child.status == "approved"


def test_dispatch_delegated_run_child_inherits_parent_objective(db_session, test_user):
    parent = _make_parent_run(db_session, test_user)
    agent = _make_agent_registry_row(db_session)

    with patch("AINDY.agents.agent_coordinator.publish_operation_request", return_value=None):
        result = dispatch_delegated_run(
            db_session,
            parent_run=parent,
            selected_agent=serialize_agent_registry(agent),
            delegation_mode="delegate",
            user_id=str(test_user.id),
            trace_id=parent.trace_id,
        )

    child = db_session.get(AgentRun, uuid.UUID(result["run_id"]))
    assert child.goal == parent.goal


def test_dispatch_delegated_run_returns_none_on_failure(db_session, test_user):
    agent = _make_agent_registry_row(db_session)

    result = dispatch_delegated_run(
        db_session,
        parent_run=object(),
        selected_agent=serialize_agent_registry(agent),
        delegation_mode="delegate",
        user_id=str(test_user.id),
        trace_id=None,
    )

    assert result is None


def test_dispatch_sets_parent_status_to_delegated(db_session, test_user):
    parent = _make_parent_run(db_session, test_user)
    agent = _make_agent_registry_row(db_session)

    with patch("AINDY.agents.agent_coordinator.publish_operation_request", return_value=None):
        dispatch_delegated_run(
            db_session,
            parent_run=parent,
            selected_agent=serialize_agent_registry(agent),
            delegation_mode="delegate",
            user_id=str(test_user.id),
            trace_id=parent.trace_id,
        )

    db_session.refresh(parent)
    assert parent.status == "delegated"


def test_child_run_parent_run_id_query(db_session, test_user):
    parent = _make_parent_run(db_session, test_user)
    agent = _make_agent_registry_row(db_session)

    with patch("AINDY.agents.agent_coordinator.publish_operation_request", return_value=None):
        dispatch_delegated_run(
            db_session,
            parent_run=parent,
            selected_agent=serialize_agent_registry(agent),
            delegation_mode="delegate",
            user_id=str(test_user.id),
            trace_id=parent.trace_id,
        )

    children = db_session.query(AgentRun).filter(AgentRun.parent_run_id == parent.id).all()
    assert len(children) == 1


def test_coordination_runs_list_route(client, auth_headers, db_session, test_user):
    parent = _make_parent_run(db_session, test_user)
    agent = _make_agent_registry_row(db_session)

    with patch("AINDY.agents.agent_coordinator.publish_operation_request", return_value=None):
        dispatch_delegated_run(
            db_session,
            parent_run=parent,
            selected_agent=serialize_agent_registry(agent),
            delegation_mode="delegate",
            user_id=str(test_user.id),
            trace_id=parent.trace_id,
        )
    db_session.commit()

    response = client.get("/coordination/runs", headers=auth_headers)

    assert response.status_code == 200
    data = _unwrap(response.json())
    assert isinstance(data, list)
    assert any(item.get("parent_run_id") == str(parent.id) for item in data)


def test_coordination_runs_children_route(client, auth_headers, db_session, test_user):
    parent = _make_parent_run(db_session, test_user)
    agent = _make_agent_registry_row(db_session)

    with patch("AINDY.agents.agent_coordinator.publish_operation_request", return_value=None):
        result = dispatch_delegated_run(
            db_session,
            parent_run=parent,
            selected_agent=serialize_agent_registry(agent),
            delegation_mode="delegate",
            user_id=str(test_user.id),
            trace_id=parent.trace_id,
        )
    db_session.commit()

    response = client.get(f"/coordination/runs/{parent.id}/children", headers=auth_headers)

    assert response.status_code == 200
    data = _unwrap(response.json())
    assert isinstance(data, list)
    assert any(item.get("run_id") == result["run_id"] for item in data)
