from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from AINDY.agents.agent_coordinator import detect_memory_write_conflict, detect_run_conflict
from AINDY.agents.agent_message_bus import acknowledge_message, get_inbox, publish_operation_request
from AINDY.db.models.agent_registry import AgentRegistry
from AINDY.db.models.agent_run import AgentRun
from AINDY.db.models.system_event import SystemEvent
from AINDY.memory.memory_persistence import MemoryNodeModel
from AINDY.utils.uuid_utils import normalize_uuid


def _make_run(db_session, test_user, *, goal: str, status: str) -> AgentRun:
    run = AgentRun(
        user_id=test_user.id,
        agent_type="default",
        goal=goal,
        plan={"steps": []},
        executive_summary="coordination test",
        overall_risk="low",
        status=status,
        steps_total=0,
        steps_completed=0,
        correlation_id=f"run_{uuid.uuid4()}",
        trace_id=f"trace-{uuid.uuid4()}",
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)
    return run


def _register_agent(db_session, agent_id: str) -> None:
    row = AgentRegistry(
        agent_id=normalize_uuid(agent_id),
        capabilities=[],
        current_state={},
        load=0.0,
        health_status="healthy",
    )
    db_session.add(row)
    db_session.commit()


def test_publish_and_get_inbox(db_session, test_user):
    agent_a = str(uuid.uuid4())
    agent_b = str(uuid.uuid4())
    _register_agent(db_session, agent_a)
    _register_agent(db_session, agent_b)

    publish_operation_request(
        db=db_session,
        sender_agent_id=agent_a,
        recipient_agent_id=agent_b,
        operation={"name": "delegate objective"},
        user_id=str(test_user.id),
        trace_id="trace-inbox",
    )

    inbox = get_inbox(db_session, agent_id=agent_b, user_id=str(test_user.id))

    assert len(inbox) == 1
    assert inbox[0]["recipient_agent_id"] == agent_b
    assert inbox[0]["message_type"] == "operation_request"


def test_inbox_excludes_acknowledged_messages(db_session, test_user):
    agent_a = str(uuid.uuid4())
    agent_b = str(uuid.uuid4())
    _register_agent(db_session, agent_a)
    _register_agent(db_session, agent_b)
    message_id = publish_operation_request(
        db=db_session,
        sender_agent_id=agent_a,
        recipient_agent_id=agent_b,
        operation={"name": "delegate objective"},
        user_id=str(test_user.id),
        trace_id="trace-ack",
    )
    acknowledge_message(
        db_session,
        message_id=message_id,
        agent_id=agent_b,
        user_id=str(test_user.id),
    )

    inbox = get_inbox(db_session, agent_id=agent_b, user_id=str(test_user.id), include_acknowledged=False)

    assert inbox == []


def test_inbox_includes_acknowledged_when_requested(db_session, test_user):
    agent_a = str(uuid.uuid4())
    agent_b = str(uuid.uuid4())
    _register_agent(db_session, agent_a)
    _register_agent(db_session, agent_b)
    message_id = publish_operation_request(
        db=db_session,
        sender_agent_id=agent_a,
        recipient_agent_id=agent_b,
        operation={"name": "delegate objective"},
        user_id=str(test_user.id),
        trace_id="trace-ack-include",
    )
    acknowledge_message(
        db_session,
        message_id=message_id,
        agent_id=agent_b,
        user_id=str(test_user.id),
    )

    inbox = get_inbox(db_session, agent_id=agent_b, user_id=str(test_user.id), include_acknowledged=True)

    assert len(inbox) == 1
    assert inbox[0]["message_id"] == str(message_id)


def test_get_inbox_filters_by_recipient(db_session, test_user):
    agent_a = str(uuid.uuid4())
    agent_b = str(uuid.uuid4())
    _register_agent(db_session, agent_a)
    _register_agent(db_session, agent_b)

    publish_operation_request(
        db=db_session,
        sender_agent_id=agent_a,
        recipient_agent_id=agent_b,
        operation={"name": "delegate objective"},
        user_id=str(test_user.id),
        trace_id="trace-recipient",
    )

    assert get_inbox(db_session, agent_id=agent_a, user_id=str(test_user.id)) == []
    assert len(get_inbox(db_session, agent_id=agent_b, user_id=str(test_user.id))) == 1


def test_detect_run_conflict_true(db_session, test_user):
    run = _make_run(db_session, test_user, goal="same objective", status="executing")

    result = detect_run_conflict(
        db_session,
        user_id=str(test_user.id),
        objective="same objective",
        agent_id=None,
    )

    assert result["conflict"] is True
    assert result["conflicting_run_id"] == str(run.id)


def test_detect_run_conflict_false_no_active_runs(db_session, test_user):
    result = detect_run_conflict(
        db_session,
        user_id=str(test_user.id),
        objective="no active objective",
        agent_id=None,
    )

    assert result["conflict"] is False


def test_detect_memory_write_conflict_no_recent_events(db_session, test_user):
    result = detect_memory_write_conflict(
        db_session,
        user_id=str(test_user.id),
        memory_path="/shared/path",
        agent_id=None,
    )

    assert result["conflict"] is False


def test_coordination_inbox_route_200(client, auth_headers):
    response = client.get(
        "/coordination/messages/inbox?agent_id=00000000-0000-0000-0000-000000000001",
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert "messages" in response.json().get("data", response.json())


def test_coordination_shared_memory_route_200(client, auth_headers, db_session, test_user):
    node = MemoryNodeModel(
        content="shared memory",
        tags=["coordination"],
        node_type="insight",
        memory_type="insight",
        visibility="shared",
        is_shared=True,
        user_id=test_user.id,
        source="test",
    )
    db_session.add(node)
    db_session.commit()

    response = client.get("/coordination/memory/shared", headers=auth_headers)

    assert response.status_code == 200
    assert "nodes" in response.json().get("data", response.json())


def test_coordination_conflict_run_route_200(client, auth_headers):
    response = client.post(
        "/coordination/conflict/run",
        json={"objective": "test objective", "agent_id": None},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert "conflict" in response.json().get("data", response.json())


def test_coordination_messages_acknowledge_route_hides_message(client, auth_headers, db_session, test_user):
    agent_a = str(uuid.uuid4())
    agent_b = str(uuid.uuid4())
    _register_agent(db_session, agent_a)
    _register_agent(db_session, agent_b)
    message_id = publish_operation_request(
        db=db_session,
        sender_agent_id=agent_a,
        recipient_agent_id=agent_b,
        operation={"name": "delegate objective"},
        user_id=str(test_user.id),
        trace_id="trace-ack-route",
    )

    ack_response = client.post(
        f"/coordination/messages/{message_id}/acknowledge",
        json={"agent_id": agent_b},
        headers=auth_headers,
    )

    assert ack_response.status_code == 200
    inbox_response = client.get(
        f"/coordination/messages/inbox?agent_id={agent_b}",
        headers=auth_headers,
    )
    assert inbox_response.status_code == 200
    messages = inbox_response.json().get("data", inbox_response.json())["messages"]
    assert all(message["message_id"] != str(message_id) for message in messages)


def test_detect_memory_write_conflict_true_recent_event(db_session, test_user):
    agent_id = str(uuid.uuid4())
    _register_agent(db_session, agent_id)
    event = SystemEvent(
        type="agent.message.memory_share",
        user_id=normalize_uuid(test_user.id),
        agent_id=normalize_uuid(agent_id),
        source="coordination",
        payload={"memory_path": "/shared/path"},
        timestamp=datetime.now(timezone.utc) - timedelta(seconds=5),
    )
    db_session.add(event)
    db_session.commit()

    result = detect_memory_write_conflict(
        db_session,
        user_id=str(test_user.id),
        memory_path="/shared/path",
        agent_id=None,
    )

    assert result["conflict"] is True
