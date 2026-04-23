import asyncio
import json
from types import SimpleNamespace

import pytest

from AINDY.runtime.memory.memory_feedback import MemoryFeedbackEngine
from AINDY.runtime.memory_loop import ExecutionLoop
from AINDY.runtime.memory import MemoryOrchestrator, MemoryContext, MemoryItem


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
async def test_nodus_execution_injects_memory_context(monkeypatch, persisted_user):
    from AINDY.routes.memory_router import NodusTaskRequest, execute_nodus_task

    monkeypatch.setenv("NODUS_SOURCE_PATH", "/tmp/nodus-src")

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
        "AINDY.runtime.memory.orchestrator.MemoryOrchestrator.get_context",
        fake_get_context,
    )

    monkeypatch.setattr(
        "AINDY.memory.bridge.create_memory_node",
        lambda *args, **kwargs: None,
    )

    captured: dict[str, object] = {}

    def fake_subprocess_run(args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        payload = json.loads(kwargs["input"])
        captured["payload"] = payload
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "status": "success",
                    "output_state": {},
                    "emitted_events": [],
                    "memory_writes": [],
                    "error": None,
                    "stdout_log": "",
                }
            ),
            stderr="",
        )

    monkeypatch.setattr(
        "AINDY.runtime.nodus_runtime_adapter.subprocess.run",
        fake_subprocess_run,
    )

    body = NodusTaskRequest(
        task_name="test",
        task_code="set_state('test', True)",
        session_tags=["unit"],
    )

    result = await execute_nodus_task(
        body=body,
        db=SimpleNamespace(),
        current_user={"sub": str(persisted_user.id)},
    )

    assert result["status"] == "executed"
    assert captured["args"][0].endswith("python.exe") or "python" in captured["args"][0].lower()
    assert captured["payload"]["memory_context"]
    assert captured["payload"]["allowed_operations"] == [
        "recall",
        "recall_all",
        "recall_from",
        "recall_tool",
        "suggest",
    ]


@pytest.mark.asyncio
async def test_nodus_execution_blocks_restricted_source(monkeypatch, persisted_user):
    from fastapi import HTTPException
    from AINDY.routes.memory_router import NodusTaskRequest, execute_nodus_task

    body = NodusTaskRequest(
        task_name="blocked",
        task_code="import os\nset_state('blocked', True)",
        session_tags=["unit"],
    )

    with pytest.raises(HTTPException) as exc:
        await execute_nodus_task(
            body=body,
            db=SimpleNamespace(),
            current_user={"sub": str(persisted_user.id)},
        )

    assert exc.value.status_code == 403
    assert exc.value.detail["error"] == "nodus_security_violation"


@pytest.mark.asyncio
async def test_nodus_execution_blocks_write_ops_without_token(monkeypatch, persisted_user):
    from fastapi import HTTPException
    from AINDY.routes.memory_router import NodusTaskRequest, execute_nodus_task

    body = NodusTaskRequest(
        task_name="blocked-write",
        task_code="remember(\"x\")",
        allowed_operations=["remember"],
        session_tags=["unit"],
    )

    with pytest.raises(HTTPException) as exc:
        await execute_nodus_task(
            body=body,
            db=SimpleNamespace(),
            current_user={"sub": str(persisted_user.id)},
        )

    assert exc.value.status_code == 403
    assert "scoped capability token" in exc.value.detail["message"]


def test_memory_feedback_updates_counts():
    node = FakeNode()
    db = FakeDB(node)

    engine = MemoryFeedbackEngine()
    engine.record_usage(["00000000-0000-0000-0000-000000000000"], 0.9, db)

    assert node.usage_count == 1
    assert node.success_count == 1
    assert node.extra.get("success_rate") is not None
    assert db.committed is True


def test_memory_loop_runs_and_feedback(monkeypatch, persisted_user):
    orchestrator = MemoryOrchestrator(FakeDAO)

    def executor(task, context):
        return {"success_score": 0.8, "result": "ok"}

    loop = ExecutionLoop(orchestrator, executor=executor)

    called = {"ids": None}

    def fake_record_usage(memory_ids, success_score, db):
        called["ids"] = memory_ids

    monkeypatch.setattr(loop.feedback, "record_usage", fake_record_usage)
    monkeypatch.setattr("AINDY.runtime.memory_loop.create_memory_node", lambda *args, **kwargs: None)

    task = SimpleNamespace(type="analysis", input="alpha", tags=["t"])
    result = loop.run(
        task,
        user_id=str(persisted_user.id),
        db=object(),
    )

    assert result["result"] == "ok"
    assert called["ids"] == ["mem-1"]
