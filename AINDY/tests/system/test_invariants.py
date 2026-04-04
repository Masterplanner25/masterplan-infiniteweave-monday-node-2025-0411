from __future__ import annotations

import time
import uuid

from db.models.agent_event import AgentEvent
from db.models.agent_run import AgentRun
from db.models.agent_run import AgentTrustSettings
from db.models.automation_log import AutomationLog
from db.models.request_metric import RequestMetric
from db.models.system_event import SystemEvent
from db.models.user import User
from agents.agent_runtime import execute_run
from services.auth_service import hash_password
from agents.capability_service import mint_token
from tests.fixtures.auth import build_access_token


VALID_PLAN = {
    "executive_summary": "Create a task and gather context.",
    "steps": [
        {
            "tool": "task.create",
            "args": {"name": "Follow up"},
            "risk_level": "low",
            "description": "Create follow-up task",
        },
        {
            "tool": "research.query",
            "args": {"query": "prospect background"},
            "risk_level": "low",
            "description": "Collect research context",
        },
    ],
    "overall_risk": "low",
}


def _create_other_user(db_session) -> User:
    other = db_session.get(User, uuid.UUID("00000000-0000-0000-0000-00000000000a"))
    if other is not None:
        return other
    other = User(
        id=uuid.UUID("00000000-0000-0000-0000-00000000000a"),
        email="invariant-other@aindy.test",
        username="invariant_other",
        hashed_password=hash_password("Passw0rd!123"),
        is_active=True,
    )
    db_session.add(other)
    db_session.commit()
    db_session.refresh(other)
    return other


def _wait_for_async_job(db_session, log_id: str, timeout_s: float = 5.0) -> AutomationLog:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        db_session.expire_all()
        log = db_session.query(AutomationLog).filter(AutomationLog.id == log_id).first()
        if log and log.status in {"success", "failed"}:
            return log
        time.sleep(0.05)
    raise AssertionError(f"Timed out waiting for automation log {log_id}")


def _make_run(db_session, user_id, *, status: str = "approved", plan: dict | None = None) -> AgentRun:
    run = AgentRun(
        user_id=user_id,
        goal="follow up with prospect",
        plan=plan or VALID_PLAN,
        executive_summary=(plan or VALID_PLAN)["executive_summary"],
        overall_risk=(plan or VALID_PLAN)["overall_risk"],
        status=status,
        steps_total=len((plan or VALID_PLAN)["steps"]),
        steps_completed=0,
        correlation_id=f"run_{uuid.uuid4()}",
        trace_id=f"trace_{uuid.uuid4()}",
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)
    return run


def test_every_execution_emits_events(client, db_session, test_user, auth_headers, monkeypatch):
    from platform_layer.async_job_service import shutdown_async_jobs

    db_session.add(
        AgentTrustSettings(
            user_id=test_user.id,
            auto_execute_low=True,
            auto_execute_medium=False,
            allowed_auto_grant_tools=["task.create", "research.query"],
        )
    )
    db_session.commit()

    monkeypatch.setenv("TESTING", "false")
    monkeypatch.setenv("TEST_MODE", "false")
    monkeypatch.setenv("AINDY_ASYNC_HEAVY_EXECUTION", "true")
    monkeypatch.setattr("agents.agent_runtime.generate_plan", lambda **kwargs: VALID_PLAN)

    def _complete_run(**kwargs):
        run = db_session.get(AgentRun, uuid.UUID(str(kwargs["run_id"])))
        run.status = "completed"
        run.result = {"steps": [], "loop_enforced": True, "next_action": "review_output"}
        db_session.commit()
        return {"status": "SUCCESS", "run_id": "flow-123"}

    monkeypatch.setattr("runtime.nodus_adapter.NodusAgentAdapter.execute_with_flow", _complete_run)

    shutdown_async_jobs(wait=True)
    try:
        response = client.post("/agent/run", headers=auth_headers, json={"goal": "follow up"})
        assert response.status_code == 202
        payload = response.json()
        data = payload.get("data", payload)
        result = data.get("result", data)
        log_id = result.get("automation_log_id") or data.get("automation_log_id")

        log = _wait_for_async_job(db_session, log_id)
        assert log.status == "success"

        event_types = [
            event.type
            for event in db_session.query(SystemEvent)
            .filter(SystemEvent.trace_id == log_id)
            .order_by(SystemEvent.timestamp.asc())
            .all()
        ]
        assert "execution.started" in event_types
        assert "execution.completed" in event_types
    finally:
        shutdown_async_jobs(wait=True)


def test_no_cross_user_leakage(client, db_session, test_user, auth_headers, monkeypatch):
    other_user = _create_other_user(db_session)
    other_headers = {
        "Authorization": f"Bearer {build_access_token(user_id=other_user.id, email=other_user.email)}"
    }
    monkeypatch.setattr("memory.embedding_service.generate_embedding", lambda text: [0.0] * 1536)

    create_response = client.post(
        "/memory/nodes",
        headers=auth_headers,
        json={"content": "tenant secret", "source": "pytest", "tags": ["private"], "node_type": "insight"},
    )
    assert create_response.status_code == 201
    node_payload = create_response.json()
    node = node_payload.get("data", node_payload)
    node_id = node["id"]

    assert client.get(f"/memory/nodes/{node_id}", headers=auth_headers).status_code == 200
    assert client.get(f"/memory/nodes/{node_id}", headers=other_headers).status_code == 404

    other_run = _make_run(db_session, other_user.id, status="completed")
    runs_response = client.get("/agent/runs", headers=auth_headers)
    assert runs_response.status_code == 200
    ran_payload = runs_response.json()
    runs_data = ran_payload.get("data", ran_payload)
    returned_ids = {item["run_id"] for item in runs_data}
    assert str(other_run.id) not in returned_ids


def test_capability_enforcement_changes_execution_path(db_session, test_user):
    run = _make_run(db_session, test_user.id, status="approved")

    result = execute_run(run.id, test_user.id, db_session)

    db_session.refresh(run)
    denied = (
        db_session.query(AgentEvent)
        .filter(AgentEvent.run_id == run.id, AgentEvent.event_type == "CAPABILITY_DENIED")
        .one()
    )

    assert result["status"] == "failed"
    assert run.status == "failed"
    assert "Missing scoped capability token" in run.error_message
    assert denied.payload["error"] == "missing scoped capability token"


def test_memory_consistency(client, auth_headers, monkeypatch):
    monkeypatch.setattr("memory.embedding_service.generate_embedding", lambda text: [0.0] * 1536)

    payload = {
        "content": "Persistent memory invariant",
        "source": "pytest",
        "tags": ["invariant", "memory"],
        "node_type": "insight",
        "extra": {"kind": "consistency"},
    }
    created = client.post("/memory/nodes", headers=auth_headers, json=payload)
    assert created.status_code == 201

    node_id = created.json()["id"]
    fetched = client.get(f"/memory/nodes/{node_id}", headers=auth_headers)
    assert fetched.status_code == 200

    body = fetched.json()
    assert body["content"] == payload["content"]
    assert body["tags"] == payload["tags"]
    assert body["source"] == payload["source"]
    assert body["extra"]["kind"] == "consistency"


def test_metrics_reflect_actions(client, db_session, test_user, auth_headers):
    before_count = db_session.query(RequestMetric).filter(RequestMetric.user_id == test_user.id).count()

    tools_response = client.get("/agent/tools", headers=auth_headers)
    assert tools_response.status_code == 200

    dashboard_response = client.get("/observability/dashboard", headers=auth_headers)
    assert dashboard_response.status_code == 200

    db_session.expire_all()
    after_count = db_session.query(RequestMetric).filter(RequestMetric.user_id == test_user.id).count()
    dashboard_payload = dashboard_response.json()
    dashboard = dashboard_payload.get("data", dashboard_payload)

    assert after_count >= before_count + 2
    assert dashboard["summary"]["window_requests"] >= 1
    assert dashboard["request_metrics"]["recent"]
    assert any(item["path"] == "/agent/tools" for item in dashboard["request_metrics"]["recent"])

