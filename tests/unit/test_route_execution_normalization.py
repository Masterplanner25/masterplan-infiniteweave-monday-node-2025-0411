from __future__ import annotations

import importlib
from types import SimpleNamespace
from unittest.mock import MagicMock


def test_agent_create_run_uses_shared_execution_wrapper(monkeypatch, persisted_user):
    agent_router = importlib.import_module("AINDY.routes.agent_router")

    captured = {}

    def _fake_execute_with_pipeline_sync(*args, **kwargs):
        captured["operation"] = kwargs["route_name"]
        captured["source"] = kwargs["metadata"]["source"]
        captured["payload"] = kwargs["input_payload"]
        return SimpleNamespace(success=True, data={"ok": True}, metadata={"eu_id": "eu-1", "trace_id": "trace-1"})

    monkeypatch.setattr(agent_router, "execute_with_pipeline_sync", _fake_execute_with_pipeline_sync)
    result = agent_router.create_agent_run(
        request=MagicMock(),
        body=agent_router.RunRequest(goal="Ship v1"),
        current_user={"sub": str(persisted_user.id)},
        db=MagicMock(),
    )

    assert result["ok"] is True
    assert captured["operation"] == "agent.run.create"
    assert captured["source"] == "agent"
    assert captured["payload"]["goal"] == "Ship v1"


def test_agent_tools_route_uses_shared_execution_wrapper(monkeypatch, persisted_user):
    agent_router = importlib.import_module("AINDY.routes.agent_router")

    captured = {}

    def _fake_execute_with_pipeline_sync(*args, **kwargs):
        captured["operation"] = kwargs["route_name"]
        return SimpleNamespace(success=True, data=[], metadata={"eu_id": "eu-2", "trace_id": "trace-2"})

    monkeypatch.setattr(agent_router, "execute_with_pipeline_sync", _fake_execute_with_pipeline_sync)

    result = agent_router.list_tools(
        request=MagicMock(),
        current_user={"sub": str(persisted_user.id)},
        db=MagicMock(),
    )

    assert result["data"] == []
    assert captured["operation"] == "agent.tools.list"


def test_genesis_create_session_uses_shared_execution_wrapper(monkeypatch, persisted_user):
    genesis_router = importlib.import_module("apps.masterplan.routes.genesis_router")

    captured = {}

    def _fake_execute_with_pipeline_sync(*args, **kwargs):
        captured["operation"] = kwargs["route_name"]
        captured["source"] = kwargs["metadata"]["source"]
        return SimpleNamespace(success=True, data={"id": 1}, metadata={"eu_id": "eu-3", "trace_id": "trace-3"})

    monkeypatch.setattr(genesis_router, "execute_with_pipeline_sync", _fake_execute_with_pipeline_sync)
    monkeypatch.setattr(genesis_router, "_genesis_run_flow", lambda *args, **kwargs: {"id": 1})

    result = genesis_router.create_genesis_session(
        request=MagicMock(),
        db=MagicMock(),
        current_user={"sub": str(persisted_user.id)},
    )

    assert result["id"] == 1
    assert captured["operation"] == "genesis.session.create"
    assert captured["source"] == "genesis"


def test_genesis_get_session_uses_shared_execution_wrapper(monkeypatch, persisted_user):
    genesis_router = importlib.import_module("apps.masterplan.routes.genesis_router")

    captured = {}

    def _fake_execute_with_pipeline_sync(*args, **kwargs):
        captured["operation"] = kwargs["route_name"]
        captured["payload"] = kwargs["input_payload"]
        return SimpleNamespace(success=True, data={"session_id": 7}, metadata={"eu_id": "eu-4", "trace_id": "trace-4"})

    monkeypatch.setattr(genesis_router, "execute_with_pipeline_sync", _fake_execute_with_pipeline_sync)
    monkeypatch.setattr(genesis_router, "_genesis_run_flow", lambda *args, **kwargs: {"session_id": 7})

    result = genesis_router.get_genesis_session(
        request=MagicMock(),
        session_id=7,
        db=MagicMock(),
        current_user={"sub": str(persisted_user.id)},
    )

    assert result["session_id"] == 7
    assert captured["operation"] == "genesis.session.get"
    assert captured["payload"]["session_id"] == 7
