from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient


def _dep(name: str, status: str = "ok", *, critical: bool = False, metadata=None):
    return SimpleNamespace(
        name=name,
        status=status,
        critical=critical,
        metadata=metadata or {},
    )


def _health(*deps):
    return SimpleNamespace(dependencies=list(deps))


def test_get_readiness_report_ready_in_testing_mode(monkeypatch):
    from AINDY.platform_layer import health_service

    monkeypatch.setattr(
        type(health_service.settings),
        "is_testing",
        property(lambda self: True),
        raising=False,
    )

    status_code, payload = health_service.get_readiness_report()

    assert status_code == 200
    assert payload["status"] == "ready"
    assert payload["required_failures"] == []


def test_get_readiness_report_startup_incomplete_returns_503(monkeypatch):
    from AINDY.platform_layer import health_service

    monkeypatch.setattr(
        type(health_service.settings),
        "is_testing",
        property(lambda self: False),
        raising=False,
    )
    monkeypatch.setattr(
        health_service,
        "get_api_runtime_state",
        lambda: {"startup_complete": False},
    )
    monkeypatch.setattr(health_service, "get_system_health", lambda force=True: _health())

    status_code, payload = health_service.get_readiness_report()

    assert status_code == 503
    assert payload["status"] == "not_ready"
    assert "startup_incomplete" in payload["required_failures"]


def test_get_readiness_report_postgres_down_returns_503(monkeypatch):
    from AINDY.platform_layer import health_service

    monkeypatch.setattr(
        type(health_service.settings),
        "is_testing",
        property(lambda self: False),
        raising=False,
    )
    monkeypatch.setattr(
        health_service,
        "get_api_runtime_state",
        lambda: {
            "startup_complete": True,
            "scheduler_role": "disabled",
            "background_enabled": False,
            "event_bus_ready": True,
        },
    )
    monkeypatch.setattr(
        health_service,
        "get_system_health",
        lambda force=True: _health(_dep("postgres", "error", critical=True)),
    )

    status_code, payload = health_service.get_readiness_report()

    assert status_code == 503
    assert payload["status"] == "not_ready"
    assert "postgres" in payload["required_failures"]


def test_get_readiness_report_allows_peripheral_domain_degradation(monkeypatch):
    from AINDY.platform_layer import health_service

    monkeypatch.setattr(
        type(health_service.settings),
        "is_testing",
        property(lambda self: False),
        raising=False,
    )
    monkeypatch.setattr(health_service.settings, "ENV", "development")
    monkeypatch.setattr(health_service.settings, "EXECUTION_MODE", "thread")
    monkeypatch.setattr(health_service.settings, "AINDY_REQUIRE_REDIS", False)
    monkeypatch.setattr(
        health_service,
        "get_api_runtime_state",
        lambda: {
            "startup_complete": True,
            "scheduler_role": "disabled",
            "background_enabled": False,
            "event_bus_ready": False,
        },
    )
    monkeypatch.setattr(
        health_service,
        "get_system_health",
        lambda force=True: _health(
            _dep("postgres", "ok", critical=True),
            _dep("schema", "ok", critical=True),
            _dep("redis", "ok", critical=False),
            _dep("queue", "ok", critical=False, metadata={"backend": "memory"}),
        ),
    )
    monkeypatch.setattr(health_service, "get_degraded_domains", lambda: ["social", "freelance"])

    status_code, payload = health_service.get_readiness_report()

    assert status_code == 200
    assert payload["status"] == "ready"
    assert payload["checks"]["degraded_domains"] == ["social", "freelance"]


def test_ready_and_readiness_routes_return_same_shape(monkeypatch):
    from AINDY.main import app
    from AINDY.platform_layer import health_service
    from AINDY.platform_layer import platform_loader

    payload = {
        "status": "ready",
        "checks": {"startup_complete": True},
        "required_failures": [],
    }
    monkeypatch.setattr(
        health_service,
        "get_readiness_report",
        lambda: (200, payload),
    )
    monkeypatch.setattr(
        platform_loader,
        "get_last_restore_result",
        lambda: {
            "flows": {"db_count": 1, "registry_count": 1, "ok": True},
            "nodes": {"db_count": 1, "registry_count": 1, "ok": True},
            "webhooks": {"db_count": 1, "registry_count": 1, "ok": True},
            "all_ok": True,
        },
    )

    client = TestClient(app)
    ready = client.get("/ready")
    readiness = client.get("/readiness")

    assert ready.status_code == 200
    assert readiness.status_code == 200
    assert ready.json()["status"] == "ready"
    assert readiness.json()["status"] == "ready"
    assert ready.json().keys() == readiness.json().keys()


def test_ready_probe_returns_503_when_restore_incomplete(monkeypatch):
    from AINDY.main import app
    from AINDY.platform_layer import platform_loader

    monkeypatch.setattr(
        platform_loader,
        "get_last_restore_result",
        lambda: {
            "flows": {"db_count": 3, "registry_count": 2, "ok": False},
            "nodes": {"db_count": 1, "registry_count": 1, "ok": True},
            "webhooks": {"db_count": 1, "registry_count": 1, "ok": True},
            "all_ok": False,
        },
    )

    client = TestClient(app)
    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "degraded"
    assert response.json()["reason"] == "registry_restore_incomplete"
    assert response.json()["detail"]["all_ok"] is False


def test_ready_probe_returns_503_when_restore_not_run(monkeypatch):
    from AINDY.main import app
    from AINDY.platform_layer import platform_loader

    monkeypatch.setattr(platform_loader, "get_last_restore_result", lambda: None)

    client = TestClient(app)
    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready", "reason": "restore_pending"}


def test_ready_probe_returns_200_when_restore_complete(monkeypatch):
    from AINDY.main import app
    from AINDY.platform_layer import health_service, platform_loader

    monkeypatch.setattr(
        platform_loader,
        "get_last_restore_result",
        lambda: {
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
            200,
            {
                "status": "ready",
                "checks": {"startup_complete": True},
                "required_failures": [],
            },
        ),
    )

    client = TestClient(app)
    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
