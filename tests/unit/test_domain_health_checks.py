from __future__ import annotations

import importlib
import json
import time


def test_register_health_check_registers_function(monkeypatch):
    from AINDY.platform_layer import registry

    monkeypatch.setattr(registry, "_health_checks", {})

    def _check():
        return {"status": "ok"}

    registry.register_health_check("analytics", _check)

    checks = registry.get_all_health_checks()
    assert checks["analytics"] is _check


def test_get_domain_health_aggregates_all_registered_checks(monkeypatch):
    from AINDY.platform_layer import health_service

    monkeypatch.setattr(
        health_service,
        "get_all_health_checks",
        lambda: {
            "analytics": lambda: {"status": "ok"},
            "tasks": lambda: {"status": "degraded", "reason": "db slow"},
        },
    )

    results = health_service.get_domain_health(timeout_seconds=0.2)

    assert results == {
        "analytics": {"status": "ok"},
        "tasks": {"status": "degraded", "reason": "db slow"},
    }


def test_get_domain_health_marks_raised_check_degraded(monkeypatch):
    from AINDY.platform_layer import health_service

    def _boom():
        raise RuntimeError("boom")

    monkeypatch.setattr(
        health_service,
        "get_all_health_checks",
        lambda: {"analytics": _boom},
    )

    results = health_service.get_domain_health(timeout_seconds=0.2)

    assert results["analytics"]["status"] == "degraded"
    assert "boom" in results["analytics"]["reason"]


def test_get_domain_health_marks_timed_out_check_degraded(monkeypatch):
    from AINDY.platform_layer import health_service

    def _slow():
        time.sleep(0.2)
        return {"status": "ok"}

    monkeypatch.setattr(
        health_service,
        "get_all_health_checks",
        lambda: {"analytics": _slow},
    )

    results = health_service.get_domain_health(timeout_seconds=0.05)

    assert results["analytics"] == {
        "status": "degraded",
        "reason": "health check timed out",
    }


def test_health_route_returns_200_degraded_when_domain_check_fails(monkeypatch):
    from AINDY.platform_layer import health_service

    health_router = importlib.import_module("AINDY.routes.health_router")

    monkeypatch.setattr(
        health_service,
        "get_domain_health",
        lambda timeout_seconds=2.0: {
            "analytics": {"status": "degraded", "reason": "orchestrator import failed"},
        },
    )
    monkeypatch.setattr(health_router, "_get_degraded_domains", lambda: [])
    monkeypatch.setattr(health_router, "_emit_health_event", lambda payload: None)

    response = health_router._build_health_response(force=False)
    payload = json.loads(response.body)

    assert response.status_code == 200
    assert payload["status"] == "degraded"
    assert payload["domains"]["analytics"]["status"] == "degraded"


def test_health_route_returns_503_when_platform_component_is_degraded(monkeypatch):
    health_router = importlib.import_module("AINDY.routes.health_router")

    class _FakeSystemHealth:
        http_status = 503

        def to_dict(self):
            return {
                "status": "unhealthy",
                "tier": "critical",
                "timestamp": "2026-04-25T00:00:00+00:00",
                "version": "test",
                "degraded_domains": [],
                "degraded_apps": [],
                "platform": {
                    "execution_engine": "ok",
                    "scheduler": "ok",
                    "database": "degraded",
                    "cache": "ok",
                },
                "domains": {},
                "memory_ingest_queue": {
                    "depth": 0,
                    "capacity": 500,
                    "dropped_total": 0,
                    "worker_running": True,
                },
                "deployment_contract": {},
                "dependencies": {
                    "postgres": {
                        "status": "unavailable",
                        "latency_ms": None,
                        "detail": "db down",
                    },
                },
            }

    monkeypatch.setattr(health_router.settings, "TESTING", False)
    monkeypatch.setattr(health_router.settings, "TEST_MODE", False)
    monkeypatch.setattr(health_router.settings, "ENV", "production")
    monkeypatch.setattr(health_router, "_emit_health_event", lambda payload: None)
    monkeypatch.setattr(
        "AINDY.platform_layer.health_service.get_system_health",
        lambda force=False: _FakeSystemHealth(),
    )

    response = health_router._build_health_response(force=False)
    payload = json.loads(response.body)

    assert response.status_code == 503
    assert payload["status"] == "unhealthy"
    assert payload["platform"]["database"] == "degraded"
