from __future__ import annotations


def test_health_returns_ok_and_persists_event(client, db_session):
    from AINDY.db.models.system_event import SystemEvent

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"

    events = db_session.query(SystemEvent).all()
    assert any(event.type == "health.liveness.completed" for event in events)


def test_ready_returns_ready(client, db_session):
    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
