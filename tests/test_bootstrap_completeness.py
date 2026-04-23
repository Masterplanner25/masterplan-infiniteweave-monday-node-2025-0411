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

    app_bootstraps = {
        "tasks": SimpleNamespace(
            BOOTSTRAP_DEPENDS_ON=[],
            register=lambda: (_ for _ in ()).throw(ValueError("boom")),
        ),
    }

    monkeypatch.setattr(bs, "discover_app_bootstraps", lambda: app_bootstraps)
    monkeypatch.setattr(bs, "resolve_boot_order", lambda _: ["tasks"])

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

    app_bootstraps = {
        "tasks": SimpleNamespace(BOOTSTRAP_DEPENDS_ON=[], register=lambda: None),
        "bridge": SimpleNamespace(
            BOOTSTRAP_DEPENDS_ON=[],
            register=lambda: (_ for _ in ()).throw(ValueError("bridge down")),
        ),
    }

    monkeypatch.setattr(bs, "discover_app_bootstraps", lambda: app_bootstraps)
    monkeypatch.setattr(bs, "resolve_boot_order", lambda _: ["tasks", "bridge"])

    try:
        bs.bootstrap()
        assert bs.get_degraded_domains() == ["bridge"]
        assert get_degraded_domains() == ["bridge"]
    finally:
        _reset_bootstrap()


def test_dependent_domain_skipped_when_dependency_fails(monkeypatch):
    _reset_bootstrap()
    import apps.bootstrap as bs
    from AINDY.platform_layer.registry import get_degraded_domains

    calls: list[str] = []

    def _ok(name: str):
        return lambda: calls.append(name)

    def _fail():
        calls.append("bridge")
        raise ValueError("bridge down")

    app_bootstraps = {
        "tasks": SimpleNamespace(BOOTSTRAP_DEPENDS_ON=[], register=_ok("tasks")),
        "bridge": SimpleNamespace(BOOTSTRAP_DEPENDS_ON=[], register=_fail),
        "automation": SimpleNamespace(
            BOOTSTRAP_DEPENDS_ON=["bridge"],
            register=_ok("automation"),
        ),
    }

    monkeypatch.setattr(bs, "discover_app_bootstraps", lambda: app_bootstraps)
    monkeypatch.setattr(bs, "resolve_boot_order", lambda _: ["tasks", "bridge", "automation"])

    try:
        bs.bootstrap()
        assert calls == ["tasks", "bridge"]
        assert bs.get_degraded_domains() == ["bridge", "automation"]
        assert get_degraded_domains() == ["bridge", "automation"]
    finally:
        _reset_bootstrap()


def test_social_bootstrap_failure_does_not_block_core_analytics(monkeypatch):
    _reset_bootstrap()
    import apps.bootstrap as bs
    from AINDY.platform_layer.registry import get_degraded_domains

    calls: list[str] = []

    def _ok(name: str):
        return lambda: calls.append(name)

    def _social_fail():
        calls.append("social")
        raise ValueError("social down")

    app_bootstraps = {
        "tasks": SimpleNamespace(BOOTSTRAP_DEPENDS_ON=[], register=_ok("tasks")),
        "identity": SimpleNamespace(BOOTSTRAP_DEPENDS_ON=[], register=_ok("identity")),
        "social": SimpleNamespace(BOOTSTRAP_DEPENDS_ON=[], register=_social_fail),
        "analytics": SimpleNamespace(
            BOOTSTRAP_DEPENDS_ON=["identity", "tasks"],
            register=_ok("analytics"),
        ),
    }

    monkeypatch.setattr(bs, "discover_app_bootstraps", lambda: app_bootstraps)
    monkeypatch.setattr(bs, "resolve_boot_order", lambda _: ["tasks", "identity", "social", "analytics"])

    try:
        bs.bootstrap()
        assert calls == ["tasks", "identity", "social", "analytics"]
        assert bs.get_degraded_domains() == ["social"]
        assert get_degraded_domains() == ["social"]
        assert bs._BOOTSTRAPPED is True
    finally:
        _reset_bootstrap()
