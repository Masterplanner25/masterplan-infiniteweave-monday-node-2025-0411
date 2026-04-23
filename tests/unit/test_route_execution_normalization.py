from __future__ import annotations

import importlib
from unittest.mock import MagicMock


def test_agent_create_run_uses_shared_execution_wrapper(monkeypatch, persisted_user):
    agent_router = importlib.import_module("apps.agent.routes.agent_router")

    captured = {}

    def _fake_run_execution(context, fn, **kwargs):
        captured["operation"] = context.operation
        captured["source"] = context.source
        captured["payload"] = context.start_payload
        return {"status": "SUCCESS", "data": {"ok": True}, "trace_id": "trace-1"}

    monkeypatch.setattr(agent_router, "run_execution", _fake_run_execution)
    monkeypatch.setattr(
        agent_router,
        "async_heavy_execution_enabled",
        lambda: False,
        raising=False,
    )
    monkeypatch.setattr(
        agent_router,
        "_run_flow_agent",
        lambda *args, **kwargs: {"ok": True},
    )

    result = agent_router.create_agent_run(
        request=MagicMock(),
        body=agent_router.RunRequest(goal="Ship v1"),
        current_user={"sub": str(persisted_user.id)},
        db=MagicMock(),
    )

    assert result["status"] == "SUCCESS"
    assert captured["operation"] == "agent.run.create"
    assert captured["source"] == "agent"
    assert captured["payload"]["goal"] == "Ship v1"


def test_agent_tools_route_uses_shared_execution_wrapper(monkeypatch, persisted_user):
    agent_router = importlib.import_module("apps.agent.routes.agent_router")

    captured = {}

    def _fake_run_execution(context, fn, **kwargs):
        captured["operation"] = context.operation
        return {"status": "SUCCESS", "data": [], "trace_id": "trace-2"}

    monkeypatch.setattr(agent_router, "run_execution", _fake_run_execution)

    result = agent_router.list_tools(
        request=MagicMock(),
        current_user={"sub": str(persisted_user.id)},
        db=MagicMock(),
    )

    assert result["status"] == "SUCCESS"
    assert captured["operation"] == "agent.tools.list"


def test_genesis_create_session_uses_shared_execution_wrapper(monkeypatch, persisted_user):
    genesis_router = importlib.import_module("apps.masterplan.routes.genesis_router")

    captured = {}

    def _fake_run_execution(context, fn, **kwargs):
        captured["operation"] = context.operation
        captured["source"] = context.source
        return {"status": "SUCCESS", "data": {"id": 1}, "trace_id": "trace-3"}

    monkeypatch.setattr(genesis_router, "run_execution", _fake_run_execution)

    result = genesis_router.create_genesis_session(
        request=MagicMock(),
        db=MagicMock(),
        current_user={"sub": str(persisted_user.id)},
    )

    assert result["status"] == "SUCCESS"
    assert captured["operation"] == "genesis.session.create"
    assert captured["source"] == "genesis"


def test_genesis_get_session_uses_shared_execution_wrapper(monkeypatch, persisted_user):
    genesis_router = importlib.import_module("apps.masterplan.routes.genesis_router")

    captured = {}

    def _fake_run_execution(context, fn, **kwargs):
        captured["operation"] = context.operation
        captured["payload"] = context.start_payload
        return {"status": "SUCCESS", "data": {"session_id": 7}, "trace_id": "trace-4"}

    monkeypatch.setattr(genesis_router, "run_execution", _fake_run_execution)

    result = genesis_router.get_genesis_session(
        request=MagicMock(),
        session_id=7,
        db=MagicMock(),
        current_user={"sub": str(persisted_user.id)},
    )

    assert result["status"] == "SUCCESS"
    assert captured["operation"] == "genesis.session.get"
    assert captured["payload"]["session_id"] == 7
