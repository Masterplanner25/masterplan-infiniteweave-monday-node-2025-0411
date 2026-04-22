from __future__ import annotations


def test_system_health_critical_when_postgres_down(monkeypatch):
    from AINDY.platform_layer import health_service
    from AINDY.platform_layer.health_service import DependencyStatus

    monkeypatch.setattr(
        health_service,
        "check_postgres",
        lambda: DependencyStatus(name="postgres", status="unavailable", critical=True),
    )
    monkeypatch.setattr(
        health_service,
        "check_redis",
        lambda: DependencyStatus(name="redis", status="ok"),
    )
    monkeypatch.setattr(
        health_service,
        "check_mongo",
        lambda: DependencyStatus(name="mongo", status="ok"),
    )
    monkeypatch.setattr(
        health_service,
        "check_schema",
        lambda: DependencyStatus(name="schema", status="ok", critical=True),
    )

    health = health_service.get_system_health(force=True)
    assert health.tier == "critical"
    assert health.http_status == 503


def test_system_health_degraded_when_mongo_down(monkeypatch):
    from AINDY.platform_layer import health_service
    from AINDY.platform_layer.health_service import DependencyStatus

    monkeypatch.setattr(
        health_service,
        "check_postgres",
        lambda: DependencyStatus(name="postgres", status="ok", critical=True),
    )
    monkeypatch.setattr(
        health_service,
        "check_redis",
        lambda: DependencyStatus(name="redis", status="ok"),
    )
    monkeypatch.setattr(
        health_service,
        "check_mongo",
        lambda: DependencyStatus(name="mongo", status="unavailable", critical=False),
    )
    monkeypatch.setattr(
        health_service,
        "check_schema",
        lambda: DependencyStatus(name="schema", status="ok", critical=True),
    )

    health = health_service.get_system_health(force=True)
    assert health.tier == "degraded"
    assert health.http_status == 200


def test_system_health_payload_includes_degraded_domains(monkeypatch):
    from AINDY.platform_layer import health_service
    from AINDY.platform_layer.health_service import DependencyStatus

    monkeypatch.setattr(
        health_service,
        "check_postgres",
        lambda: DependencyStatus(name="postgres", status="ok", critical=True),
    )
    monkeypatch.setattr(
        health_service,
        "check_redis",
        lambda: DependencyStatus(name="redis", status="ok"),
    )
    monkeypatch.setattr(
        health_service,
        "check_mongo",
        lambda: DependencyStatus(name="mongo", status="ok"),
    )
    monkeypatch.setattr(
        health_service,
        "check_schema",
        lambda: DependencyStatus(name="schema", status="ok", critical=True),
    )
    monkeypatch.setattr(
        "apps.bootstrap.get_degraded_domains",
        lambda: ["bridge", "autonomy"],
    )

    payload = health_service.get_system_health(force=True).to_dict()
    assert payload["degraded_domains"] == ["bridge", "autonomy"]
