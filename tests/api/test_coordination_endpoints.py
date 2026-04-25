from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from AINDY.db.models.agent_registry import AgentRegistry
from AINDY.utils.uuid_utils import normalize_uuid


def _unwrap(payload):
    if isinstance(payload, dict) and "data" in payload:
        return payload["data"]
    return payload


def test_register_agent_creates_registry_row(client, auth_headers, db_session):
    agent_id = str(uuid.uuid4())

    response = client.post(
        "/coordination/agents/register",
        json={
            "agent_id": agent_id,
            "capabilities": ["task.read"],
            "load": 0.2,
            "health_status": "healthy",
        },
        headers=auth_headers,
    )

    assert response.status_code == 200
    body = _unwrap(response.json())
    assert body["agent_id"] == agent_id
    assert body["health_status"] == "healthy"

    row = db_session.query(AgentRegistry).filter(AgentRegistry.agent_id == normalize_uuid(agent_id)).first()
    assert row is not None


def test_register_agent_upserts_on_duplicate_id(client, auth_headers):
    agent_id = str(uuid.uuid4())

    first = client.post(
        "/coordination/agents/register",
        json={"agent_id": agent_id, "load": 0.1},
        headers=auth_headers,
    )
    assert first.status_code == 200

    response = client.post(
        "/coordination/agents/register",
        json={"agent_id": agent_id, "load": 0.9},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert _unwrap(response.json())["load"] == 0.9


def test_heartbeat_updates_last_seen(client, auth_headers, db_session):
    agent_id = str(uuid.uuid4())
    client.post("/coordination/agents/register", json={"agent_id": agent_id}, headers=auth_headers)

    row = db_session.query(AgentRegistry).filter(AgentRegistry.agent_id == normalize_uuid(agent_id)).first()
    assert row is not None
    row.last_seen = datetime.now(timezone.utc) - timedelta(minutes=15)
    db_session.add(row)
    db_session.commit()

    response = client.post(
        f"/coordination/agents/{agent_id}/heartbeat",
        json={"load": 0.5, "health_status": "degraded"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    body = _unwrap(response.json())
    assert body["health_status"] == "degraded"
    assert body["was_stale"] is True


def test_heartbeat_404_for_unknown_agent(client, auth_headers):
    response = client.post(
        f"/coordination/agents/{uuid.uuid4()}/heartbeat",
        json={},
        headers=auth_headers,
    )

    assert response.status_code == 404


def test_heartbeat_rejects_local_agent(client, auth_headers):
    response = client.post(
        "/coordination/agents/00000000-0000-0000-0000-000000000001/heartbeat",
        json={},
        headers=auth_headers,
    )

    assert response.status_code == 400


def test_deregister_removes_agent(client, auth_headers, db_session):
    agent_id = str(uuid.uuid4())
    client.post("/coordination/agents/register", json={"agent_id": agent_id}, headers=auth_headers)

    response = client.delete(
        f"/coordination/agents/{agent_id}",
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert _unwrap(response.json())["status"] == "deregistered"

    row = db_session.query(AgentRegistry).filter(AgentRegistry.agent_id == normalize_uuid(agent_id)).first()
    assert row is None


def test_deregister_rejects_local_agent(client, auth_headers):
    response = client.delete(
        "/coordination/agents/00000000-0000-0000-0000-000000000001",
        headers=auth_headers,
    )

    assert response.status_code == 400


def test_list_agents_without_stale_by_default(client, auth_headers):
    response = client.get("/coordination/agents", headers=auth_headers)

    assert response.status_code == 200
