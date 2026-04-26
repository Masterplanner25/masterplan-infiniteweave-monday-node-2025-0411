"""Verify that the refactored bootstrap registers the same set of platform
artifacts as the original monolithic apps/bootstrap.py."""
from __future__ import annotations

import importlib
from types import SimpleNamespace


def _reset_bootstrap():
    """Reset bootstrap state so it re-runs in this test."""
    import apps.bootstrap as bs
    from AINDY.platform_layer import registry

    bs._BOOTSTRAPPED = False
    bs._DEGRADED_DOMAINS = []
    registry.publish_degraded_domains(())


def _call_bootstrap():
    import apps.bootstrap as bs
    bs.bootstrap()


# ---------------------------------------------------------------------------
# Registry state inspection helpers
# ---------------------------------------------------------------------------

def _get_registry():
    from AINDY.platform_layer import registry
    return registry


# ---------------------------------------------------------------------------
# Test: known job names are registered
# ---------------------------------------------------------------------------

def test_known_jobs_registered():
    _reset_bootstrap()
    _call_bootstrap()
    from AINDY.platform_layer.registry import get_job

    required_jobs = [
        "tasks.background.start",
        "tasks.background.stop",
        "tasks.background.is_leader",
        "analytics.kpi_snapshot",
        "analytics.infinity_execute",
        "analytics.latest_adjustment",
        "genesis.synthesize",
        "genesis.audit",
        "goals.rank",
        "goals.calculate_alignment",
        "goals.update_from_execution",
        "arm.analyzer",
        "automation.execute",
        "freelance.generate_delivery",
        "scheduler.infinity_scores",
        "scheduler.masterplan_eta",
        "scheduler.reminders",
        "scheduler.recurrence",
        "scheduler.lease_heartbeat",
    ]
    for job_name in required_jobs:
        assert get_job(job_name) is not None, f"Job '{job_name}' not registered after bootstrap"


# ---------------------------------------------------------------------------
# Test: minimum router count
# ---------------------------------------------------------------------------

def test_minimum_router_count():
    _reset_bootstrap()
    _call_bootstrap()
    from AINDY.platform_layer.registry import get_routers

    routers = get_routers()
    assert len(routers) >= 20, (
        f"Expected at least 20 routers after bootstrap, got {len(routers)}"
    )


# ---------------------------------------------------------------------------
# Test: known event types registered
# ---------------------------------------------------------------------------

def test_known_event_types_registered():
    _reset_bootstrap()
    _call_bootstrap()
    from AINDY.platform_layer.registry import get_event_types

    event_types = get_event_types()
    required = {
        "system.startup",
        "system.shutdown",
        "scheduler.tick",
        "job_log.written",
    }
    missing = required - event_types
    assert not missing, f"Missing event types after bootstrap: {missing}"


# ---------------------------------------------------------------------------
# Test: known event handlers registered
# ---------------------------------------------------------------------------

def test_known_event_handlers_registered():
    _reset_bootstrap()
    _call_bootstrap()
    from AINDY.platform_layer.registry import get_event_handlers
    from AINDY.core.system_event_types import SystemEventTypes

    assert get_event_handlers("system.startup"), "No handler for system.startup"
    assert get_event_handlers("system.shutdown"), "No handler for system.shutdown"
    assert get_event_handlers(SystemEventTypes.EXECUTION_COMPLETED), (
        f"No handler for {SystemEventTypes.EXECUTION_COMPLETED}"
    )
    assert get_event_handlers("job_log.written"), "No handler for job_log.written"


# ---------------------------------------------------------------------------
# Test: known flow result keys registered
# ---------------------------------------------------------------------------

def test_known_flow_results_registered():
    _reset_bootstrap()
    _call_bootstrap()
    from AINDY.platform_layer.registry import get_flow_result_key

    required = {
        "genesis_message": "genesis_response",
        "arm_analysis": "analysis_result",
        "leadgen_search": "search_results",
        "automation_logs_list": "automation_logs_list_result",
        "agent_run_create": "agent_run_create_result",
        "freelance_order_create": "freelance_order_create_result",
        "memory_recall": "memory_recall_result",
        "flow_runs_list": "flow_runs_list_result",
    }
    for flow_name, expected_key in required.items():
        actual = get_flow_result_key(flow_name)
        assert actual == expected_key, (
            f"Flow result key for '{flow_name}': expected '{expected_key}', got '{actual}'"
        )


# ---------------------------------------------------------------------------
# Test: bootstrap() is idempotent
# ---------------------------------------------------------------------------

def test_bootstrap_is_idempotent():
    _reset_bootstrap()
    _call_bootstrap()
    from AINDY.platform_layer.registry import get_routers
    count_after_first = len(get_routers())

    _call_bootstrap()  # second call — _BOOTSTRAPPED is True, no re-registration
    count_after_second = len(get_routers())

    assert count_after_first == count_after_second, (
        "Router count changed between bootstrap() calls — registrations are not idempotent"
    )


# ---------------------------------------------------------------------------
# Test: bootstrap_models() delegates to bootstrap()
# ---------------------------------------------------------------------------

def test_bootstrap_models_delegates():
    _reset_bootstrap()
    import apps.bootstrap as bs
    bs.bootstrap_models()
    assert bs._BOOTSTRAPPED is True, "bootstrap_models() did not set _BOOTSTRAPPED"


def test_core_domain_failure_raises(monkeypatch):
    _reset_bootstrap()
    import apps.bootstrap as bs

    monkeypatch.setattr(
        bs,
        "_load_bootstrap_metadata",
        lambda: {"tasks": {"BOOTSTRAP_DEPENDS_ON": []}},
    )
    monkeypatch.setattr(bs, "get_resolved_boot_order", lambda: ["tasks"])
    monkeypatch.setattr(
        bs,
        "_import_bootstrap_module",
        lambda app_name: SimpleNamespace(
            register=lambda: (_ for _ in ()).throw(ValueError("boom"))
        ),
    )

    try:
        try:
            bs.bootstrap()
        except RuntimeError as exc:
            assert "Core domain bootstrap failed for tasks" in str(exc)
        else:
            assert False, "Expected bootstrap() to raise for core domain failure"
    finally:
        _reset_bootstrap()


def test_peripheral_domain_failure_skips(monkeypatch):
    _reset_bootstrap()
    import apps.bootstrap as bs
    from AINDY.platform_layer.registry import get_degraded_domains

    monkeypatch.setattr(
        bs,
        "_load_bootstrap_metadata",
        lambda: {
            "tasks": {"BOOTSTRAP_DEPENDS_ON": []},
            "bridge": {"BOOTSTRAP_DEPENDS_ON": []},
        },
    )
    monkeypatch.setattr(bs, "get_resolved_boot_order", lambda: ["tasks", "bridge"])
    monkeypatch.setattr(
        bs,
        "_import_bootstrap_module",
        lambda app_name: SimpleNamespace(
            register=(lambda: None)
            if app_name == "tasks"
            else (lambda: (_ for _ in ()).throw(ValueError("bridge down")))
        ),
    )

    try:
        bs.bootstrap()
        assert bs.get_degraded_domains() == ["bridge"]
        assert get_degraded_domains() == ["bridge"]
    finally:
        _reset_bootstrap()


def test_peripheral_domain_attempts_boot_even_when_dependency_failed(monkeypatch):
    _reset_bootstrap()
    import apps.bootstrap as bs
    from AINDY.platform_layer.registry import get_degraded_domains

    calls: list[str] = []

    def _ok(name: str):
        return lambda: calls.append(name)

    def _fail():
        calls.append("bridge")
        raise ValueError("bridge down")

    monkeypatch.setattr(
        bs,
        "_load_bootstrap_metadata",
        lambda: {
            "tasks": {"BOOTSTRAP_DEPENDS_ON": []},
            "bridge": {"BOOTSTRAP_DEPENDS_ON": []},
            "automation": {"BOOTSTRAP_DEPENDS_ON": ["bridge"]},
        },
    )
    monkeypatch.setattr(bs, "get_resolved_boot_order", lambda: ["tasks", "bridge", "automation"])
    monkeypatch.setattr(
        bs,
        "_import_bootstrap_module",
        lambda app_name: SimpleNamespace(
            register={
                "tasks": _ok("tasks"),
                "bridge": _fail,
                "automation": _ok("automation"),
            }[app_name]
        ),
    )

    try:
        bs.bootstrap()
        assert calls == ["tasks", "bridge", "automation"]
        assert bs.get_degraded_domains() == ["bridge"]
        assert get_degraded_domains() == ["bridge"]
    finally:
        _reset_bootstrap()


def test_social_bootstrap_failure_does_not_block_peripheral_analytics(monkeypatch):
    _reset_bootstrap()
    import apps.bootstrap as bs
    from AINDY.platform_layer.registry import get_degraded_domains

    calls: list[str] = []

    def _ok(name: str):
        return lambda: calls.append(name)

    def _social_fail():
        calls.append("social")
        raise ValueError("social down")

    monkeypatch.setattr(
        bs,
        "_load_bootstrap_metadata",
        lambda: {
            "tasks": {"BOOTSTRAP_DEPENDS_ON": []},
            "identity": {"BOOTSTRAP_DEPENDS_ON": []},
            "social": {"BOOTSTRAP_DEPENDS_ON": []},
            "analytics": {"BOOTSTRAP_DEPENDS_ON": ["identity", "tasks"]},
        },
    )
    monkeypatch.setattr(bs, "get_resolved_boot_order", lambda: ["tasks", "identity", "social", "analytics"])
    monkeypatch.setattr(
        bs,
        "_import_bootstrap_module",
        lambda app_name: SimpleNamespace(
            register={
                "tasks": _ok("tasks"),
                "identity": _ok("identity"),
                "social": _social_fail,
                "analytics": _ok("analytics"),
            }[app_name]
        ),
    )

    try:
        bs.bootstrap()
        assert calls == ["tasks", "identity", "social", "analytics"]
        assert bs.get_degraded_domains() == ["social"]
        assert get_degraded_domains() == ["social"]
        assert bs._BOOTSTRAPPED is True
    finally:
        _reset_bootstrap()


def test_analytics_bootstrap_import_failure_is_degraded_and_health_reports_it(monkeypatch):
    _reset_bootstrap()
    import importlib
    import apps.bootstrap as bs
    health_router = importlib.import_module("AINDY.routes.health_router")
    from AINDY.platform_layer import health_service
    from AINDY.platform_layer.health_service import DependencyStatus

    calls: list[str] = []

    def _ok(name: str):
        return lambda: calls.append(name)

    monkeypatch.setattr(
        bs,
        "_load_bootstrap_metadata",
        lambda: {
            "tasks": {"BOOTSTRAP_DEPENDS_ON": []},
            "identity": {"BOOTSTRAP_DEPENDS_ON": []},
            "agent": {"BOOTSTRAP_DEPENDS_ON": []},
            "analytics": {"BOOTSTRAP_DEPENDS_ON": ["identity", "tasks"]},
        },
    )
    monkeypatch.setattr(bs, "get_resolved_boot_order", lambda: ["tasks", "identity", "agent", "analytics"])

    def _import_module(app_name: str):
        if app_name == "analytics":
            raise ImportError("broken analytics import")
        return SimpleNamespace(
            register={
                "tasks": _ok("tasks"),
                "identity": _ok("identity"),
                "agent": _ok("agent"),
            }[app_name]
        )

    monkeypatch.setattr(bs, "_import_bootstrap_module", _import_module)
    monkeypatch.setattr(
        health_service,
        "check_postgres",
        lambda: DependencyStatus(name="postgres", status="ok", critical=True),
    )
    monkeypatch.setattr(
        health_service,
        "check_redis",
        lambda: DependencyStatus(name="redis", status="ok", critical=False),
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

    try:
        bs.bootstrap()
        health_payload = health_router._testing_health_payload()
        payload = health_service.get_system_health(force=True).to_dict()
        assert calls == ["tasks", "identity", "agent"]
        assert bs.get_degraded_domains() == ["analytics"]
        assert health_payload["degraded_apps"] == ["analytics"]
        assert health_payload["status"] == "degraded"
        assert payload["degraded_apps"] == ["analytics"]
        assert payload["degraded_domains"] == ["analytics"]
        assert payload["status"] == "degraded"
        assert health_service.get_system_health(force=True).http_status == 200
        assert "tasks" not in payload["degraded_apps"]
        assert "identity" not in payload["degraded_apps"]
        assert "agent" not in payload["degraded_apps"]
    finally:
        _reset_bootstrap()
