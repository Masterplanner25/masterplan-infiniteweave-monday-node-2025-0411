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

    monkeypatch.setattr(health_service.settings, "TESTING", True)
    monkeypatch.setattr(health_service.settings, "TEST_MODE", False)
    monkeypatch.setattr(health_service.settings, "ENV", "development")

    status_code, payload = health_service.get_readiness_report()

    assert status_code == 200
    assert payload["status"] == "ready"
    assert payload["required_failures"] == []


def test_get_readiness_report_startup_incomplete_returns_503(monkeypatch):
    from AINDY.platform_layer import health_service

    monkeypatch.setattr(health_service.settings, "TESTING", False)
    monkeypatch.setattr(health_service.settings, "TEST_MODE", False)
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

    monkeypatch.setattr(health_service.settings, "TESTING", False)
    monkeypatch.setattr(health_service.settings, "TEST_MODE", False)
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

    monkeypatch.setattr(health_service.settings, "TESTING", False)
    monkeypatch.setattr(health_service.settings, "TEST_MODE", False)
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

    client = TestClient(app)
    ready = client.get("/ready")
    readiness = client.get("/readiness")

    assert ready.status_code == 200
    assert readiness.status_code == 200
    assert ready.json()["status"] == "ready"
    assert readiness.json()["status"] == "ready"
    assert ready.json().keys() == readiness.json().keys()
