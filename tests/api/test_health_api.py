from __future__ import annotations


def test_health_returns_ok_and_persists_event(client, db_session):
    from AINDY.db.models.system_event import SystemEvent

    response = client.get("/health")
    payload = response.json()

    assert response.status_code == 200
    assert payload["status"] in {"ok", "degraded"}
    assert "dependencies" in payload
    assert "domains" in payload

    events = db_session.query(SystemEvent).all()
    assert any(event.type == "health.liveness.completed" for event in events)


def test_health_detail_returns_dependency_map(client):
    response = client.get("/health/detail")

    assert response.status_code == 200
    assert "dependencies" in response.json()


def test_ready_returns_ready(client, db_session, monkeypatch):
    import importlib

    platform_loader = importlib.import_module("AINDY.platform_layer.platform_loader")
    monkeypatch.setattr(
        platform_loader,
        "_last_restore_result",
        {
            "flows": {"db_count": 1, "registry_count": 1, "ok": True},
            "nodes": {"db_count": 1, "registry_count": 1, "ok": True},
            "webhooks": {"db_count": 1, "registry_count": 1, "ok": True},
            "all_ok": True,
        },
    )
    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert "checks" in response.json()


def test_health_reports_degraded_domains(client, monkeypatch):
    import importlib

    health_router = importlib.import_module("AINDY.routes.health_router")

    monkeypatch.setattr(health_router, "get_degraded_domains", lambda: ["bridge", "autonomy"])

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["degraded_domains"] == ["bridge", "autonomy"]


def test_ready_returns_503_when_required_runtime_contract_not_met(client, monkeypatch):
    import importlib

    health_service = importlib.import_module("AINDY.platform_layer.health_service")
    platform_loader = importlib.import_module("AINDY.platform_layer.platform_loader")

    monkeypatch.setattr(
        platform_loader,
        "_last_restore_result",
        {
            "flows": {"db_count": 1, "registry_count": 1, "ok": True},
            "nodes": {"db_count": 1, "registry_count": 1, "ok": True},
            "webhooks": {"db_count": 1, "registry_count": 1, "ok": True},
            "all_ok": True,
        },
    )

    monkeypatch.setattr(
        health_service,
        "get_readiness_report",
        lambda: (
            503,
            {
                "status": "not_ready",
                "checks": {"worker": "missing"},
                "required_failures": ["worker"],
            },
        ),
    )

    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
    assert response.json()["required_failures"] == ["worker"]
