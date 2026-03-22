import asyncio
from types import SimpleNamespace

import pytest

from runtime.memory.memory_feedback import MemoryFeedbackEngine
from runtime.execution_loop import ExecutionLoop
from runtime.memory import MemoryOrchestrator, MemoryContext, MemoryItem


class FakeNode:
    def __init__(self):
        self.usage_count = 0
        self.success_count = 0
        self.failure_count = 0
        self.extra = {}


class FakeDB:
    def __init__(self, node):
        self.node = node
        self.committed = False
        self.rolled_back = False

    def get(self, model, node_id):
        return self.node

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


class FakeDAO:
    def __init__(self, db):
        self.db = db

    def recall(self, **kwargs):
        return [
            {
                "id": "mem-1",
                "content": "alpha",
                "node_type": "outcome",
                "semantic_score": 0.8,
                "recency_score": 0.8,
                "success_rate": 0.7,
                "usage_frequency": 2,
                "graph_score": 0.2,
                "tags": ["alpha"],
            }
        ]


class FakeRuntime:
    def __init__(self):
        self.registered = {}
        self.run_kwargs = None

    def register_function(self, name, fn, arity=None):
        self.registered[name] = (fn, arity)

    def run_source(self, *args, **kwargs):
        self.run_kwargs = kwargs
        return {"ok": True, "stdout": "done"}


@pytest.mark.asyncio
async def test_nodus_execution_injects_memory_context(monkeypatch):
    from routes.memory_router import NodusTaskRequest, execute_nodus_task

    def fake_get_context(*args, **kwargs):
        return MemoryContext(
            items=[
                MemoryItem(
                    id="mem-1",
                    content="alpha",
                    node_type="outcome",
                    score=0.9,
                )
            ],
            total_tokens=10,
            metadata={},
            formatted="[OUTCOME | score=0.90]\nalpha",
        )

    monkeypatch.setattr(
        "runtime.memory.orchestrator.MemoryOrchestrator.get_context",
        fake_get_context,
    )

    fake_runtime = FakeRuntime()

    import types
    import sys

    embedding_module = types.ModuleType("nodus.runtime.embedding")
    embedding_module.NodusRuntime = lambda: fake_runtime

    runtime_module = types.ModuleType("nodus.runtime")
    runtime_module.embedding = embedding_module

    nodus_module = types.ModuleType("nodus")
    nodus_module.runtime = runtime_module

    monkeypatch.setitem(sys.modules, "nodus", nodus_module)
    monkeypatch.setitem(sys.modules, "nodus.runtime", runtime_module)
    monkeypatch.setitem(sys.modules, "nodus.runtime.embedding", embedding_module)

    monkeypatch.setattr(
        "bridge.create_memory_node",
        lambda *args, **kwargs: None,
    )

    body = NodusTaskRequest(
        task_name="test",
        task_code="task test { }",
        session_tags=["unit"],
    )

    result = await execute_nodus_task(
        body=body,
        db=SimpleNamespace(),
        current_user={"sub": "user-1"},
    )

    assert result["status"] == "executed"
    assert "recall_tool" in fake_runtime.registered
    assert fake_runtime.run_kwargs["initial_globals"]["memory_context"]
    assert fake_runtime.run_kwargs["host_globals"]["memory_bridge"]


def test_memory_feedback_updates_counts():
    node = FakeNode()
    db = FakeDB(node)

    engine = MemoryFeedbackEngine()
    engine.record_usage(["00000000-0000-0000-0000-000000000000"], 0.9, db)

    assert node.usage_count == 1
    assert node.success_count == 1
    assert node.extra.get("success_rate") is not None
    assert db.committed is True


def test_execution_loop_runs_and_feedback(monkeypatch):
    orchestrator = MemoryOrchestrator(FakeDAO)

    def executor(task, context):
        return {"success_score": 0.8, "result": "ok"}

    loop = ExecutionLoop(orchestrator, executor=executor)

    called = {"ids": None}

    def fake_record_usage(memory_ids, success_score, db):
        called["ids"] = memory_ids

    monkeypatch.setattr(loop.feedback, "record_usage", fake_record_usage)
    monkeypatch.setattr("runtime.execution_loop.create_memory_node", lambda *args, **kwargs: None)

    task = SimpleNamespace(type="analysis", input="alpha", tags=["t"])
    result = loop.run(task, user_id="user-1", db=object())

    assert result["result"] == "ok"
    assert called["ids"] == ["mem-1"]
