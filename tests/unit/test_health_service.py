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
    monkeypatch.setattr(
        health_service,
        "check_ai_providers",
        lambda: DependencyStatus(name="ai_providers", status="ok", critical=False),
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
        health_service,
        "check_ai_providers",
        lambda: DependencyStatus(name="ai_providers", status="ok", critical=False),
    )
    monkeypatch.setattr(
        health_service,
        "get_degraded_domains",
        lambda: ["bridge", "autonomy"],
    )

    payload = health_service.get_system_health(force=True).to_dict()
    assert payload["degraded_domains"] == ["bridge", "autonomy"]


def test_system_health_marks_redis_critical_when_required(monkeypatch):
    from AINDY.platform_layer import health_service
    from AINDY.platform_layer.health_service import DependencyStatus

    monkeypatch.setattr(health_service.settings, "AINDY_REQUIRE_REDIS", True)
    monkeypatch.setattr(health_service.settings, "ENV", "production")
    monkeypatch.setattr(
        health_service,
        "check_postgres",
        lambda: DependencyStatus(name="postgres", status="ok", critical=True),
    )
    monkeypatch.setattr(
        health_service,
        "check_redis",
        lambda: DependencyStatus(name="redis", status="unavailable", critical=True),
    )
    monkeypatch.setattr(
        health_service,
        "check_queue",
        lambda: DependencyStatus(name="queue", status="ok", critical=False),
    )
    monkeypatch.setattr(
        health_service,
        "check_mongo",
        lambda: DependencyStatus(name="mongo", status="ok", critical=False),
    )
    monkeypatch.setattr(
        health_service,
        "check_schema",
        lambda: DependencyStatus(name="schema", status="ok", critical=True),
    )
    monkeypatch.setattr(
        health_service,
        "check_ai_providers",
        lambda: DependencyStatus(name="ai_providers", status="ok", critical=False),
    )

    health = health_service.get_system_health(force=True)
    assert health.tier == "critical"
    assert health.http_status == 503


def test_system_health_payload_includes_ai_provider_circuit_state(monkeypatch):
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
        "check_queue",
        lambda: DependencyStatus(name="queue", status="ok"),
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
        health_service,
        "check_ai_providers",
        lambda: DependencyStatus(
            name="ai_providers",
            status="degraded",
            critical=False,
            metadata={
                "openai": {"circuit": "open", "failure_count": 3},
                "deepseek": {"circuit": "closed", "failure_count": 0},
            },
        ),
    )

    payload = health_service.get_system_health(force=True).to_dict()
    assert payload["dependencies"]["ai_providers"]["status"] == "degraded"
    assert payload["dependencies"]["ai_providers"]["openai"]["circuit"] == "open"
    assert payload["dependencies"]["ai_providers"]["deepseek"]["circuit"] == "closed"


def test_readiness_requires_worker_in_distributed_mode(monkeypatch):
    from AINDY.platform_layer import health_service
    from AINDY.platform_layer.deployment_contract import publish_api_runtime_state, reset_runtime_state
    from AINDY.platform_layer.health_service import DependencyStatus

    reset_runtime_state()
    publish_api_runtime_state(
        startup_complete=True,
        background_enabled=False,
        scheduler_role="disabled",
        event_bus_ready=True,
    )
    monkeypatch.setattr(health_service.settings, "TESTING", False)
    monkeypatch.setattr(health_service.settings, "TEST_MODE", False)
    monkeypatch.setattr(health_service.settings, "ENV", "production")
    monkeypatch.setattr(health_service.settings, "EXECUTION_MODE", "distributed")
    monkeypatch.setattr(health_service.settings, "REDIS_URL", "redis://example")
    monkeypatch.setattr(
        health_service,
        "get_system_health",
        lambda force=True: health_service.SystemHealth(
            tier="healthy",
            http_status=200,
            dependencies=[
                DependencyStatus(name="postgres", status="ok", critical=True),
                DependencyStatus(name="redis", status="ok", critical=True),
                DependencyStatus(name="queue", status="ok", critical=True),
                DependencyStatus(name="schema", status="ok", critical=True),
            ],
        ),
    )
    monkeypatch.setattr(
        health_service,
        "_check_worker_heartbeat",
        lambda: {"status": "missing", "detail": "No worker heartbeat in Redis"},
    )

    status_code, payload = health_service.get_readiness_report()
    assert status_code == 503
    assert payload["status"] == "not_ready"
    assert "worker" in payload["required_failures"]


def test_readiness_allows_degraded_peripheral_domains_when_requirements_met(monkeypatch):
    from AINDY.platform_layer import health_service
    from AINDY.platform_layer.deployment_contract import publish_api_runtime_state, reset_runtime_state
    from AINDY.platform_layer.health_service import DependencyStatus

    reset_runtime_state()
    publish_api_runtime_state(
        startup_complete=True,
        background_enabled=True,
        scheduler_role="follower",
        event_bus_ready=False,
    )
    monkeypatch.setattr(health_service.settings, "TESTING", False)
    monkeypatch.setattr(health_service.settings, "TEST_MODE", False)
    monkeypatch.setattr(health_service.settings, "ENV", "development")
    monkeypatch.setattr(health_service.settings, "AINDY_REQUIRE_REDIS", False)
    monkeypatch.setattr(health_service.settings, "EXECUTION_MODE", "thread")
    monkeypatch.setattr(
        health_service,
        "get_system_health",
        lambda force=True: health_service.SystemHealth(
            tier="degraded",
            http_status=200,
            dependencies=[
                DependencyStatus(name="postgres", status="ok", critical=True),
                DependencyStatus(name="redis", status="degraded", critical=False),
                DependencyStatus(name="queue", status="degraded", critical=False),
                DependencyStatus(name="schema", status="ok", critical=True),
            ],
        ),
    )
    monkeypatch.setattr(health_service, "get_degraded_domains", lambda: ["bridge"])

    status_code, payload = health_service.get_readiness_report()
    assert status_code == 200
    assert payload["status"] == "ready"
    assert payload["checks"]["degraded_domains"] == ["bridge"]


def test_readiness_requires_event_bus_when_redis_contract_requires_it(monkeypatch):
    from AINDY.platform_layer import health_service
    from AINDY.platform_layer.deployment_contract import publish_api_runtime_state, reset_runtime_state
    from AINDY.platform_layer.health_service import DependencyStatus

    reset_runtime_state()
    publish_api_runtime_state(
        startup_complete=True,
        background_enabled=False,
        scheduler_role="disabled",
        event_bus_ready=False,
    )
    monkeypatch.setattr(health_service.settings, "TESTING", False)
    monkeypatch.setattr(health_service.settings, "TEST_MODE", False)
    monkeypatch.setattr(health_service.settings, "ENV", "production")
    monkeypatch.setattr(health_service.settings, "AINDY_REQUIRE_REDIS", True)
    monkeypatch.setattr(health_service.settings, "EXECUTION_MODE", "thread")
    monkeypatch.setattr(
        health_service,
        "get_system_health",
        lambda force=True: health_service.SystemHealth(
            tier="healthy",
            http_status=200,
            dependencies=[
                DependencyStatus(name="postgres", status="ok", critical=True),
                DependencyStatus(name="redis", status="ok", critical=True),
                DependencyStatus(name="queue", status="ok", critical=False),
                DependencyStatus(name="schema", status="ok", critical=True),
            ],
        ),
    )

    status_code, payload = health_service.get_readiness_report()
    assert status_code == 503
    assert payload["status"] == "not_ready"
    assert "event_bus" in payload["required_failures"]


def test_readiness_in_prod_allows_degraded_peripheral_domains_when_core_runtime_is_ready(monkeypatch):
    from types import SimpleNamespace

    from AINDY.platform_layer import health_service
    from AINDY.platform_layer.deployment_contract import publish_api_runtime_state, reset_runtime_state
    from AINDY.platform_layer.health_service import DependencyStatus

    reset_runtime_state()
    publish_api_runtime_state(
        startup_complete=True,
        background_enabled=True,
        scheduler_role="leader",
        event_bus_ready=True,
    )
    monkeypatch.setattr(health_service.settings, "TESTING", False)
    monkeypatch.setattr(health_service.settings, "TEST_MODE", False)
    monkeypatch.setattr(health_service.settings, "ENV", "production")
    monkeypatch.setattr(health_service.settings, "AINDY_REQUIRE_REDIS", True)
    monkeypatch.setattr(health_service.settings, "EXECUTION_MODE", "distributed")
    monkeypatch.setattr(health_service.settings, "REDIS_URL", "redis://example")
    monkeypatch.setattr(
        health_service,
        "get_system_health",
        lambda force=True: health_service.SystemHealth(
            tier="degraded",
            http_status=200,
            dependencies=[
                DependencyStatus(name="postgres", status="ok", critical=True),
                DependencyStatus(name="redis", status="ok", critical=True),
                DependencyStatus(name="queue", status="ok", critical=True),
                DependencyStatus(name="schema", status="ok", critical=True),
            ],
        ),
    )
    monkeypatch.setattr(
        health_service,
        "_check_worker_heartbeat",
        lambda: {"status": "ok", "detail": "last_beat=2026-04-22T12:00:00+00:00"},
    )
    monkeypatch.setattr(health_service, "get_degraded_domains", lambda: ["bridge"])
    monkeypatch.setattr(
        "AINDY.platform_layer.scheduler_service.get_scheduler",
        lambda: SimpleNamespace(running=True),
    )

    status_code, payload = health_service.get_readiness_report()
    assert status_code == 200
    assert payload["status"] == "ready"
    assert payload["checks"]["scheduler"] == "ok"
    assert payload["checks"]["degraded_domains"] == ["bridge"]
    assert payload["required_failures"] == []
