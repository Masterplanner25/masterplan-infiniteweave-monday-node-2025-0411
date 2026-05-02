from __future__ import annotations

import asyncio
import importlib
from collections import defaultdict

import pytest
from fastapi.routing import APIRoute

from AINDY.agents.tool_registry import TOOL_REGISTRY
from AINDY.platform_layer import registry
from AINDY.platform_layer.deployment_contract import get_api_runtime_state, reset_runtime_state


class _StopStartup(Exception):
    pass


_REGISTRY_STATE_EMPTY = {
    "_routers": [],
    "_root_routers": [],
    "_legacy_root_routers": [],
    "_syscalls": {},
    "_jobs": {},
    "_flows": [],
    "_flow_result_keys": {},
    "_flow_result_extractors": {},
    "_flow_completion_events": {},
    "_flow_plans": {},
    "_event_handlers": defaultdict(list),
    "_event_types": set(),
    "_capture_rules": {},
    "_memory_policies": {},
    "_scheduled_jobs": {},
    "_response_adapters": {},
    "_route_guards": {},
    "_execution_adapters": {},
    "_startup_hooks": [],
    "_agent_tools": {},
    "_agent_planner_contexts": {},
    "_agent_run_tools": {},
    "_agent_completion_hooks": defaultdict(list),
    "_agent_event_emitters": defaultdict(list),
    "_agent_ranking_strategy": None,
    "_trigger_evaluators": {},
    "_flow_strategies": {},
    "_capability_definitions": {},
    "_capability_definition_providers": [],
    "_tool_capabilities": {},
    "_agent_capabilities": {},
    "_restricted_tools": set(),
    "_route_prefixes": {
        "flow": "flow",
        "memory": "flow",
        "nodus": "nodus",
        "platform": "job",
    },
    "_required_flow_nodes": [],
    "_required_syscalls": [],
    "_symbols": {},
    "_loaded_plugins": set(),
    "_registered_apps": [],
    "_bootstrap_dependencies": {},
    "_core_domains": [],
    "_degraded_domains": [],
    "_health_checks": {},
    "_active_plugin_profile": None,
    "_runtime_agent_defaults_loaded": False,
}


def _copy_registry_value(value):
    if isinstance(value, defaultdict):
        copied = defaultdict(value.default_factory)
        for key, item in value.items():
            if isinstance(item, list):
                copied[key] = list(item)
            else:
                copied[key] = item
        return copied
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, list):
        return list(value)
    if isinstance(value, set):
        return set(value)
    return value


@pytest.fixture
def platform_only_runtime(monkeypatch):
    tool_registry_snapshot = dict(TOOL_REGISTRY)
    snapshot = {
        name: _copy_registry_value(getattr(registry, name))
        for name in _REGISTRY_STATE_EMPTY
    }
    try:
        monkeypatch.setenv("AINDY_BOOT_PROFILE", "platform-only")
        TOOL_REGISTRY.clear()
        for name, value in _REGISTRY_STATE_EMPTY.items():
            setattr(registry, name, _copy_registry_value(value))
        reset_runtime_state()
        yield
    finally:
        monkeypatch.delenv("AINDY_BOOT_PROFILE", raising=False)
        TOOL_REGISTRY.clear()
        TOOL_REGISTRY.update(tool_registry_snapshot)
        for name, value in snapshot.items():
            setattr(registry, name, value)
        import AINDY.startup as startup
        import AINDY.main as main

        importlib.reload(startup)
        importlib.reload(main)
        reset_runtime_state()


def _reload_platform_only_modules():
    import AINDY.startup as startup
    import AINDY.main as main

    startup = importlib.reload(startup)
    main = importlib.reload(main)
    return startup, main


def _patch_minimal_lifespan(monkeypatch, main):
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("AINDY_ENFORCE_SCHEMA", "false")
    monkeypatch.setattr(main.settings, "TESTING", False)
    monkeypatch.setattr(main.settings, "TEST_MODE", False)
    monkeypatch.setattr(main.settings, "ENV", "development")
    monkeypatch.setattr(main.settings, "SECRET_KEY", "platform-only-startup-test-secret-key")
    monkeypatch.setattr(main.settings, "AINDY_CACHE_BACKEND", "memory")
    monkeypatch.setattr(main.FastAPICache, "init", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "ensure_mongo_ready", lambda **kwargs: None)
    monkeypatch.setattr(main, "validate_queue_backend", lambda: None)
    monkeypatch.setattr(main, "_check_worker_presence", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "emit_event", lambda *args, **kwargs: (_ for _ in ()).throw(_StopStartup()))


def test_create_app_succeeds_in_platform_only_mode(platform_only_runtime):
    _startup, main = _reload_platform_only_modules()

    app = main.create_app()
    routes = {
        route.path
        for route in app.routes
        if isinstance(route, APIRoute)
    }

    assert registry.get_active_plugin_profile() == "platform-only"
    assert registry.get_registered_apps() == []
    assert "/health" in routes
    assert "/ready" in routes
    assert any(path.startswith("/platform/") for path in routes)
    assert any(path.startswith("/apps/memory") for path in routes)
    assert not any(path.startswith("/apps/social") for path in routes)
    assert not any(path.startswith("/apps/tasks") for path in routes)


def test_platform_only_lifespan_reaches_runtime_startup(platform_only_runtime, monkeypatch):
    _startup, main = _reload_platform_only_modules()
    _patch_minimal_lifespan(monkeypatch, main)

    with pytest.raises(_StopStartup):
        asyncio.run(main.lifespan(main.app).__aenter__())

    runtime_state = get_api_runtime_state()
    assert runtime_state["boot_profile"] == "platform-only"
    assert runtime_state["app_plugins_loaded"] is False
    assert runtime_state["app_plugin_count"] == 0


def test_platform_only_registers_runtime_agent_defaults(platform_only_runtime):
    _startup, _main = _reload_platform_only_modules()

    planner_context = registry.get_planner_context("default", {"user_id": "user-1", "db": object()})
    tools = registry.get_tools_for_run("default", {"user_id": "user-1", "db": object()})
    evaluator = registry.get_trigger_evaluator("default")
    capabilities = registry.get_capability_definitions()

    assert planner_context["system_prompt"]
    assert isinstance(planner_context["context_block"], str)
    assert {tool["name"] for tool in tools} >= {"memory.recall", "memory.write"}
    assert evaluator is not None
    assert evaluator({"trigger_type": "user", "trigger": {"importance": 0.9}, "context": {}})["decision"] == "execute"
    assert {"execute_flow", "read_memory", "write_memory"} <= set(capabilities)


def test_platform_only_runtime_memory_tools_dispatch_kernel_syscalls(platform_only_runtime, monkeypatch):
    _startup, _main = _reload_platform_only_modules()
    tools = {tool["name"]: tool for tool in registry.get_tools_for_run("default", {})}

    dispatched: list[tuple[str, dict, list[str]]] = []

    class _FakeDispatcher:
        def dispatch(self, name, payload, context):
            dispatched.append((name, payload, list(context.capabilities)))
            if name == "sys.v1.memory.read":
                return {"status": "success", "data": {"nodes": [{"id": "node-1"}], "count": 1}}
            if name == "sys.v1.memory.write":
                return {"status": "success", "data": {"node": {"id": "node-2"}, "path": "/memory/test"}}
            raise AssertionError(name)

    monkeypatch.setattr("AINDY.platform_layer.runtime_agent_defaults.get_dispatcher", lambda: _FakeDispatcher())

    recall_result = TOOL_REGISTRY[tools["memory.recall"]["name"]]["fn"]({"query": "alpha"}, "user-1", None)
    write_result = TOOL_REGISTRY[tools["memory.write"]["name"]]["fn"]({"content": "beta"}, "user-1", None)

    assert recall_result["count"] == 1
    assert write_result["node_id"] == "node-2"
    assert dispatched == [
        ("sys.v1.memory.read", {"query": "alpha"}, ["memory.read"]),
        ("sys.v1.memory.write", {"source": "agent", "content": "beta"}, ["memory.write"]),
    ]


def test_startup_fails_when_default_profile_plugin_is_missing(platform_only_runtime, monkeypatch, tmp_path):
    manifest = tmp_path / "aindy_plugins.json"
    manifest.write_text(
        """
{
  "default_profile": "default-apps",
  "profiles": {
    "platform-only": {"plugins": []},
    "default-apps": {"plugins": ["missing.bootstrap.module"]}
  }
}
""".strip(),
        encoding="utf-8",
    )

    with monkeypatch.context() as scoped:
        scoped.delenv("AINDY_BOOT_PROFILE", raising=False)
        scoped.delenv("AINDY_PLUGIN_PROFILE", raising=False)
        scoped.setattr(registry, "_default_manifest_path", lambda: manifest)

        import AINDY.startup as startup

        with pytest.raises(RuntimeError, match="missing\\.bootstrap\\.module"):
            importlib.reload(startup)
