from __future__ import annotations

import importlib
import sys
from collections import defaultdict

import pytest
from fastapi.testclient import TestClient


def _patch_session_aliases(monkeypatch, session_factory, engine):
    import AINDY.db.database as db_database

    monkeypatch.setattr(db_database, "SessionLocal", session_factory, raising=False)
    monkeypatch.setattr(db_database, "engine", engine, raising=False)

    for module_name, module in list(sys.modules.items()):
        if not module_name:
            continue
        if (
            module_name == "AINDY.platform_layer.async_job_service"
            and engine.dialect.name == "postgresql"
        ):
            # Async job polling tests expect JobLog writes to be visible from a
            # separate committed session. Keeping this module on its original
            # engine-bound SessionLocal preserves that behavior on PostgreSQL.
            continue
        if not (
            module_name == "main"
            or module_name == "AINDY.main"
            or module_name.startswith("routes.")
            or module_name.startswith("services.")
            or module_name.startswith("platform_layer.")
            or module_name.startswith("runtime.")
            or module_name.startswith("agents.")
            or module_name.startswith("memory.")
            or module_name.startswith("apps.")
            or module_name.startswith("core.")
            or module_name == "worker"
            or module_name.startswith("AINDY.routes.")
            or module_name.startswith("AINDY.services.")
            or module_name.startswith("AINDY.platform_layer.")
            or module_name.startswith("AINDY.runtime.")
            or module_name.startswith("AINDY.agents.")
            or module_name.startswith("AINDY.memory.")
            or module_name.startswith("AINDY.core.")
        ):
            continue
        if hasattr(module, "SessionLocal"):
            monkeypatch.setattr(module, "SessionLocal", session_factory, raising=False)
        if hasattr(module, "engine"):
            monkeypatch.setattr(module, "engine", engine, raising=False)


_EMPTY_REGISTRY_STATE = {
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
            copied[key] = list(item) if isinstance(item, list) else item
        return copied
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, list):
        return list(value)
    if isinstance(value, set):
        return set(value)
    return value


def _fresh_main_app():
    from AINDY.agents.tool_registry import TOOL_REGISTRY
    from AINDY.platform_layer import registry
    from AINDY.platform_layer.deployment_contract import reset_runtime_state
    import apps.bootstrap as apps_bootstrap
    import AINDY.main as main_module
    import AINDY.startup as startup_module

    TOOL_REGISTRY.clear()
    for name, value in _EMPTY_REGISTRY_STATE.items():
        setattr(registry, name, _copy_registry_value(value))
    apps_bootstrap._BOOTSTRAPPED = False
    apps_bootstrap._DEGRADED_DOMAINS = []
    reset_runtime_state()
    registry.load_plugins()

    importlib.reload(startup_module)
    main_module = importlib.reload(main_module)
    return main_module.app


@pytest.fixture
def app(db_session_factory, testing_session_factory, test_engine, monkeypatch):
    from AINDY.db.database import get_db

    fastapi_app = _fresh_main_app()

    session_factory = (
        db_session_factory
        if test_engine.dialect.name == "postgresql"
        else testing_session_factory
    )
    _patch_session_aliases(monkeypatch, session_factory, test_engine)

    def _get_test_db():
        db = db_session_factory()
        try:
            yield db
        finally:
            db.close()

    fastapi_app.dependency_overrides[get_db] = _get_test_db
    yield fastapi_app
    fastapi_app.dependency_overrides.clear()


@pytest.fixture
def client(app):
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
