from __future__ import annotations

from collections import defaultdict
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from AINDY.agents.tool_registry import TOOL_REGISTRY, _SUGGESTION_PROVIDERS, suggest_tools
from AINDY.platform_layer import registry
from AINDY.platform_layer.deployment_contract import agent_runtime_enrichment_contract


_REGISTRY_STATE_EMPTY = {
    "_agent_tools": {},
    "_agent_planner_contexts": {},
    "_agent_run_tools": {},
    "_agent_completion_hooks": defaultdict(list),
    "_agent_event_emitters": defaultdict(list),
    "_agent_ranking_strategy": None,
    "_trigger_evaluators": {},
    "_capability_definitions": {},
    "_capability_definition_providers": [],
    "_tool_capabilities": {},
    "_agent_capabilities": {},
    "_restricted_tools": set(),
    "_loaded_plugins": set(),
    "_registered_apps": [],
    "_bootstrap_dependencies": {},
    "_active_plugin_profile": None,
    "_active_plugin_profile_source": None,
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


@pytest.fixture
def isolated_agent_registry(monkeypatch):
    tool_registry_snapshot = dict(TOOL_REGISTRY)
    suggestion_provider_snapshot = list(_SUGGESTION_PROVIDERS)
    registry_snapshot = {
        name: _copy_registry_value(getattr(registry, name))
        for name in _REGISTRY_STATE_EMPTY
    }
    monkeypatch.setenv("AINDY_BOOT_MODE", "runtime-only")
    try:
        TOOL_REGISTRY.clear()
        _SUGGESTION_PROVIDERS.clear()
        for name, value in _REGISTRY_STATE_EMPTY.items():
            setattr(registry, name, _copy_registry_value(value))
        yield
    finally:
        TOOL_REGISTRY.clear()
        TOOL_REGISTRY.update(tool_registry_snapshot)
        _SUGGESTION_PROVIDERS.clear()
        _SUGGESTION_PROVIDERS.extend(suggestion_provider_snapshot)
        for name, value in registry_snapshot.items():
            setattr(registry, name, value)


def test_agent_runtime_enrichment_contract_is_explicit():
    contract = agent_runtime_enrichment_contract()

    assert [entry["type"] for entry in contract["baseline_runtime_contract"]] == [
        "planner_context",
        "tool_catalog",
        "trigger_evaluator",
        "suggestions",
        "completion_hook",
    ]
    assert [entry["type"] for entry in contract["optional_plugin_enrichment"]] == [
        "planner_context",
        "suggestions",
        "completion_hook",
        "tool_catalog",
    ]
    assert [entry["type"] for entry in contract["ambiguous_or_refactor"]] == [
        "planner_context",
        "suggestions",
        "completion_hook",
    ]


def test_runtime_defaults_keep_agent_enrichment_generic(isolated_agent_registry):
    from AINDY.platform_layer import runtime_agent_defaults

    runtime_agent_defaults.register()

    planner_context = registry.get_planner_context("default", {"user_id": "user-1", "db": object()})
    completion_results = registry.run_agent_completion_hooks(
        "default",
        {"run": SimpleNamespace(result={}), "db": MagicMock(), "user_id": "user-1"},
    )

    assert "runtime-owned AINDY agent planner" in planner_context["system_prompt"]
    assert planner_context["context_block"] == ""
    assert suggest_tools(user_id="user-1", db=object()) == []
    assert completion_results == [None]


@pytest.mark.app_profile
def test_plugin_registration_adds_kpi_planner_context_suggestions_and_completion_enrichment(
    isolated_agent_registry,
    monkeypatch,
):
    runtime_extensions = pytest.importorskip("apps.agent.agents.runtime_extensions")
    app_tools = pytest.importorskip("apps.agent.agents.tools")

    def fake_get_job(name):
        if name == "analytics.kpi_snapshot":
            return lambda user_id, db: {
                "master_score": 82.0,
                "execution_speed": 81.0,
                "decision_efficiency": 77.0,
                "ai_productivity_boost": 79.0,
                "focus_quality": 25.0,
                "masterplan_progress": 74.0,
                "confidence": "high",
            }
        if name == "analytics.latest_adjustment":
            return lambda user_id, db: None
        if name == "analytics.infinity_execute":
            return lambda user_id, trigger_event, db: {
                "next_action": {"type": "review_plan"},
            }
        return None

    class _FailingDispatcher:
        def dispatch(self, name, payload, context):
            return {"status": "error", "data": {}, "error": f"{name} unavailable"}

    monkeypatch.setattr("AINDY.platform_layer.registry.get_job", fake_get_job)
    monkeypatch.setattr("apps.agent.agents.tools.get_dispatcher", lambda: _FailingDispatcher())

    app_tools.register()
    runtime_extensions.register()

    planner_context = registry.get_planner_context("default", {"user_id": "user-1", "db": object()})
    suggestions = suggest_tools(user_id="user-1", db=object())
    run = SimpleNamespace(result={})
    db = MagicMock()
    completion_results = registry.run_agent_completion_hooks(
        "default",
        {"run": run, "db": db, "user_id": "user-1"},
    )

    assert "User Performance Context" in planner_context["context_block"]
    assert "strategic agent planner" in planner_context["system_prompt"]
    assert suggestions[0]["tool"] == "memory.recall"
    assert run.result["loop_enforced"] is True
    assert run.result["next_action"] == {"type": "review_plan"}
    assert completion_results[0]["next_action"] == {"type": "review_plan"}
    db.commit.assert_called_once()
