from __future__ import annotations

import time
import uuid

from apps.automation.models import AutomationLog
from AINDY.db.models.memory_metrics import MemoryMetric
from AINDY.db.models.system_event import SystemEvent
from AINDY.db.models.user import User
from AINDY.services.auth_service import create_access_token
from AINDY.services.auth_service import hash_password


def _unwrap(payload):
    if isinstance(payload, dict) and "data" in payload:
        return payload["data"]
    return payload


def _create_other_user(db_session) -> User:
    other_user = User(
        id=uuid.UUID("00000000-0000-0000-0000-000000000004"),
        email="memory-other@aindy.test",
        username="memory_other_user",
        hashed_password=hash_password("Passw0rd!123"),
        is_active=True,
    )
    db_session.add(other_user)
    db_session.commit()
    db_session.refresh(other_user)
    return other_user


def _wait_for_async_job(db_or_factory, log_id: str, timeout_s: float = 5.0) -> AutomationLog:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if callable(db_or_factory):
            db_session = db_or_factory()
            should_close = True
        else:
            db_session = db_or_factory
            should_close = False
        try:
            db_session.expire_all()
            log = db_session.query(AutomationLog).filter(AutomationLog.id == log_id).first()
        finally:
            if should_close:
                db_session.close()
        if log and log.status in {"success", "failed"}:
            return log
        time.sleep(0.05)
    raise AssertionError(f"Timed out waiting for automation log {log_id}")


def test_memory_routes_require_auth(client):
    assert client.get("/apps/memory/metrics").status_code == 401
    assert client.post("/apps/memory/nodes", json={"content": "x"}).status_code == 401


def test_memory_nodus_route_rejects_token_for_missing_user(client):
    missing_user_id = uuid.uuid4()
    headers = {
        "Authorization": f"Bearer {create_access_token({'sub': str(missing_user_id), 'email': 'missing-memory@aindy.test'})}"
    }

    response = client.post(
        "/apps/memory/nodus/execute",
        headers=headers,
        json={
            "task_name": "memory async smoke",
            "task_code": "task smoke { }",
            "session_tags": ["pytest"],
        },
    )

    assert response.status_code == 401


def test_memory_node_create_and_get_are_db_backed_and_user_scoped(
    client,
    db_session,
    testing_session_factory,
    test_user,
    auth_headers,
    monkeypatch,
):
    other_user = _create_other_user(db_session)
    monkeypatch.setattr("AINDY.memory.embedding_service.generate_embedding", lambda text: [0.0] * 1536)

    create_response = client.post(
        "/apps/memory/nodes",
        headers=auth_headers,
        json={
            "content": "Remember this detail",
            "source": "pytest",
            "tags": ["alpha", "beta"],
            "node_type": "insight",
            "extra": {"origin": "test"},
        },
    )

    assert create_response.status_code == 201
    created = _unwrap(create_response.json())
    assert created["content"] == "Remember this detail"
    assert created["user_id"] == str(test_user.id)

    get_response = client.get(f"/apps/memory/nodes/{created['id']}", headers=auth_headers)

    assert get_response.status_code == 200
    fetched = _unwrap(get_response.json())
    assert fetched["id"] == created["id"]
    assert fetched["tags"] == ["alpha", "beta"]

    # Insert another user's node directly to validate route scoping.
    from AINDY.db.dao.memory_node_dao import MemoryNodeDAO

    dao = MemoryNodeDAO(db_session)
    hidden = dao.save(
        content="Other tenant node",
        source="pytest",
        tags=["hidden"],
        user_id=str(other_user.id),
        node_type="insight",
        extra={"origin": "other"},
    )

    hidden_response = client.get(f"/apps/memory/nodes/{hidden['id']}", headers=auth_headers)
    assert hidden_response.status_code == 404


def test_memory_link_create_rejects_cross_user_target_node(
    client,
    db_session,
    test_user,
    auth_headers,
    monkeypatch,
):
    other_user = _create_other_user(db_session)
    monkeypatch.setattr("AINDY.memory.embedding_service.generate_embedding", lambda text: [0.0] * 1536)

    from AINDY.db.dao.memory_node_dao import MemoryNodeDAO

    dao = MemoryNodeDAO(db_session)
    own_node = dao.save(
        content="Own node",
        source="pytest",
        tags=["own"],
        user_id=str(test_user.id),
        node_type="insight",
    )
    other_node = dao.save(
        content="Other tenant node",
        source="pytest",
        tags=["other"],
        user_id=str(other_user.id),
        node_type="insight",
    )

    response = client.post(
        "/apps/memory/links",
        headers=auth_headers,
        json={
            "source_id": own_node["id"],
            "target_id": other_node["id"],
            "link_type": "related",
            "weight": 0.5,
        },
    )

    assert response.status_code == 404

    other_headers = {
        "Authorization": f"Bearer {create_access_token({'sub': str(other_user.id), 'email': other_user.email})}"
    }
    reverse_response = client.post(
        "/apps/memory/links",
        headers=other_headers,
        json={
            "source_id": other_node["id"],
            "target_id": own_node["id"],
            "link_type": "related",
            "weight": 0.5,
        },
    )

    assert reverse_response.status_code == 404


def test_memory_metrics_summary_and_dashboard_use_real_db(
    client,
    db_session,
    test_user,
    auth_headers,
):
    other_user = _create_other_user(db_session)
    db_session.add_all(
        [
            MemoryMetric(
                user_id=test_user.id,
                task_type="analysis",
                impact_score=0.8,
                memory_count=3,
                avg_similarity=0.9,
            ),
            MemoryMetric(
                user_id=test_user.id,
                task_type="analysis",
                impact_score=0.0,
                memory_count=1,
                avg_similarity=0.5,
            ),
            MemoryMetric(
                user_id=other_user.id,
                task_type="analysis",
                impact_score=-0.4,
                memory_count=2,
                avg_similarity=0.2,
            ),
        ]
    )
    db_session.commit()

    summary_response = client.get("/apps/memory/metrics", headers=auth_headers)
    assert summary_response.status_code == 200
    summary = _unwrap(summary_response.json())
    assert summary["total_runs"] == 2
    assert summary["positive_impact_rate"] == 0.5
    assert summary["zero_impact_rate"] == 0.5
    assert summary["negative_impact_rate"] == 0.0

    dashboard_response = client.get("/apps/memory/metrics/dashboard", headers=auth_headers)
    assert dashboard_response.status_code == 200
    dashboard = _unwrap(dashboard_response.json())
    assert dashboard["summary"]["total_runs"] == 2
    assert len(dashboard["recent_runs"]) == 2
    assert all(run["task_type"] == "analysis" for run in dashboard["recent_runs"])
    assert dashboard["insights"]


def test_memory_nodus_async_route_emits_system_events(
    client,
    db_session,
    test_user,
    auth_headers,
    monkeypatch,
):
    from AINDY.platform_layer.async_job_service import shutdown_async_jobs

    monkeypatch.setenv("TESTING", "false")
    monkeypatch.setenv("TEST_MODE", "false")
    monkeypatch.setenv("AINDY_ASYNC_HEAVY_EXECUTION", "true")
    monkeypatch.setattr(
        "runtime.nodus_execution_service.execute_nodus_task_payload",
        lambda **kwargs: {
            "task_name": kwargs["task_name"],
            "status": "executed",
            "memory_bridge": "restricted",
            "result": {"ok": True, "stdout": "done"},
        },
    )

    shutdown_async_jobs(wait=True)
    try:
        response = client.post(
            "/apps/memory/nodus/execute",
            headers=auth_headers,
            json={
                "task_name": "memory async smoke",
                "task_code": "set_state('smoke', True)",
                "session_tags": ["pytest"],
            },
        )

        assert response.status_code == 202
        payload = response.json()
        data = _unwrap(payload)
        result = data.get("result", data) if isinstance(data, dict) else data
        log_id = result.get("automation_log_id") or data.get("automation_log_id")
        assert log_id

        log = _wait_for_async_job(db_session, log_id)
        assert log.status == "success"
        assert log.user_id == test_user.id

        db_session.expire_all()
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
