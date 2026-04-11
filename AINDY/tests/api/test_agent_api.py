from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone

from AINDY.db.models.agent_run import AgentRun, AgentTrustSettings
from AINDY.db.models.automation_log import AutomationLog
from AINDY.db.models.system_event import SystemEvent
from AINDY.db.models.user import User
from AINDY.services.auth_service import hash_password


def _unwrap(payload):
    if isinstance(payload, dict) and "data" in payload:
        return payload["data"]
    return payload


def _seed_run(*, db_session, user_id, goal: str, status: str, trace_id: str) -> AgentRun:
    run = AgentRun(
        user_id=user_id,
        goal=goal,
        plan={"steps": [], "overall_risk": "low", "executive_summary": "seeded"},
        executive_summary="seeded",
        overall_risk="low",
        status=status,
        steps_total=0,
        steps_completed=0,
        correlation_id=f"run_{uuid.uuid4()}",
        trace_id=trace_id,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)
    return run


def _wait_for_async_job(db_session, log_id: str, timeout_s: float = 5.0) -> AutomationLog:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        db_session.expire_all()
        log = db_session.query(AutomationLog).filter(AutomationLog.id == log_id).first()
        if log and log.status in {"success", "failed"}:
            return log
        time.sleep(0.05)
    raise AssertionError(f"Timed out waiting for automation log {log_id}")


def test_agent_routes_require_auth(client):
    assert client.get("/apps/agent/runs").status_code == 401
    assert client.get("/apps/agent/tools").status_code == 401
    assert client.get("/apps/agent/trust").status_code == 401
    assert client.post("/apps/agent/run", json={"goal": "test"}).status_code == 401


def test_agent_tools_list_authenticated(client, auth_headers):
    response = client.get("/apps/agent/tools", headers=auth_headers)

    assert response.status_code == 200
    payload = response.json()
    data = _unwrap(payload)
    assert isinstance(data, list)
    assert any(tool["name"] == "task.create" for tool in data)


def test_agent_trust_get_and_put_use_real_db(
    client,
    db_session,
    test_user,
    auth_headers,
):
    get_response = client.get("/apps/agent/trust", headers=auth_headers)

    assert get_response.status_code == 200
    initial = get_response.json()
    initial_data = _unwrap(initial)
    assert initial_data["user_id"] == str(test_user.id)
    assert initial_data["auto_execute_low"] is False

    put_response = client.put(
        "/apps/agent/trust",
        headers=auth_headers,
        json={
            "auto_execute_low": True,
            "auto_execute_medium": False,
            "allowed_auto_grant_tools": ["task.create", "genesis.message"],
        },
    )

    assert put_response.status_code == 200
    payload = put_response.json()
    data = _unwrap(payload)
    assert data["auto_execute_low"] is True
    assert data["auto_execute_medium"] is False
    assert data["allowed_auto_grant_tools"] == ["task.create"]

    db_session.expire_all()
    trust = (
        db_session.query(AgentTrustSettings)
        .filter(AgentTrustSettings.user_id == test_user.id)
        .first()
    )
    assert trust is not None
    assert trust.auto_execute_low is True
    assert trust.allowed_auto_grant_tools == ["task.create"]


def test_agent_runs_are_user_scoped(
    client,
    db_session,
    test_user,
    auth_headers,
):
    other_user_id = uuid.UUID("00000000-0000-0000-0000-000000000003")
    db_session.add(
        User(
            id=other_user_id,
            email="agent-other@aindy.test",
            username="agent_other_user",
            hashed_password=hash_password("Passw0rd!123"),
            is_active=True,
        )
    )
    db_session.commit()

    _seed_run(
        db_session=db_session,
        user_id=test_user.id,
        goal="visible run",
        status="pending_approval",
        trace_id="trace-visible",
    )
    _seed_run(
        db_session=db_session,
        user_id=other_user_id,
        goal="hidden run",
        status="pending_approval",
        trace_id="trace-hidden",
    )

    response = client.get("/apps/agent/runs", headers=auth_headers)

    assert response.status_code == 200
    payload = response.json()
    data = _unwrap(payload)
    assert len(data) == 1
    assert data[0]["goal"] == "visible run"
    assert str(data[0]["user_id"]) == str(test_user.id)


def test_agent_run_async_create_persists_log_run_and_events(
    client,
    db_session,
    test_user,
    auth_headers,
    monkeypatch,
):
    class _FakeMessage:
        content = json.dumps(
            {
                "executive_summary": "Create a follow-up task",
                "steps": [
                    {
                        "tool": "task.create",
                        "args": {"name": "Follow up"},
                        "risk_level": "low",
                        "description": "Create the task",
                    }
                ],
                "overall_risk": "low",
            }
        )

    class _FakeChoice:
        message = _FakeMessage()

    class _FakeResponse:
        choices = [_FakeChoice()]

    from AINDY.platform_layer.async_job_service import shutdown_async_jobs
    import AINDY.agents.agent_runtime as agent_runtime

    monkeypatch.setenv("TESTING", "false")
    monkeypatch.setenv("TEST_MODE", "false")
    monkeypatch.setenv("AINDY_ASYNC_HEAVY_EXECUTION", "true")
    monkeypatch.setattr(agent_runtime, "perform_external_call", lambda **kwargs: _FakeResponse())

    shutdown_async_jobs(wait=True)
    try:
        response = client.post(
            "/apps/agent/run",
            json={"goal": "Create a follow-up task"},
            headers=auth_headers,
        )

        assert response.status_code == 202
        payload = response.json()
        data = _unwrap(payload)
        assert payload["status"] == "QUEUED"
        log_id = data["automation_log_id"]
        assert payload["trace_id"] == log_id

        log = _wait_for_async_job(db_session, log_id)
        assert log.status == "success"
        assert log.user_id == test_user.id

        db_session.expire_all()
        run = (
            db_session.query(AgentRun)
            .filter(
                AgentRun.user_id == test_user.id,
                AgentRun.goal == "Create a follow-up task",
            )
            .first()
        )
        assert run is not None
        assert run.status == "pending_approval"
        assert run.trace_id == log_id

        events = (
            db_session.query(SystemEvent)
            .filter(SystemEvent.trace_id == log_id)
            .order_by(SystemEvent.timestamp.asc())
            .all()
        )
        event_types = [event.type for event in events]
        assert "execution.started" in event_types
        assert "execution.completed" in event_types
    finally:
        shutdown_async_jobs(wait=True)

