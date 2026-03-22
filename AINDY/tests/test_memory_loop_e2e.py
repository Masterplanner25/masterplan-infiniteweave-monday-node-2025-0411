import uuid
from dataclasses import dataclass, field
from datetime import datetime

import pytest

from runtime.execution_loop import ExecutionLoop
from runtime.memory import MemoryOrchestrator


@dataclass
class InMemoryNode:
    id: uuid.UUID
    content: str
    tags: list
    node_type: str
    user_id: str
    created_at: datetime = field(default_factory=datetime.utcnow)
    usage_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    extra: dict = field(default_factory=dict)


class InMemoryDB:
    def __init__(self):
        self.nodes: dict[uuid.UUID, InMemoryNode] = {}
        self.committed = False

    def get(self, model, node_id):
        return self.nodes.get(node_id)

    def query(self, model):
        return self

    def get_node(self, node_id):
        return self.nodes.get(node_id)

    def commit(self):
        self.committed = True

    def rollback(self):
        pass


class InMemoryDAO:
    def __init__(self, db: InMemoryDB):
        self.db = db

    def recall(self, query=None, tags=None, limit=5, user_id=None, node_type=None):
        results = []
        for node in self.db.nodes.values():
            if user_id and node.user_id != user_id:
                continue
            if node_type and node.node_type != node_type:
                continue
            if tags and not set(tags).issubset(set(node.tags)):
                continue

            success_rate = node.extra.get("success_rate", 0.5)
            results.append(
                {
                    "id": str(node.id),
                    "content": node.content,
                    "tags": node.tags,
                    "node_type": node.node_type,
                    "created_at": node.created_at,
                    "semantic_score": 0.9,
                    "recency_score": 1.0,
                    "success_rate": success_rate,
                    "usage_frequency": float(node.usage_count or 0),
                    "graph_score": 0.1,
                    "extra": node.extra,
                }
            )

        return results[:limit]


class FailingDAO(InMemoryDAO):
    def recall(self, *args, **kwargs):
        raise Exception("recall failed")


class FakeTask:
    def __init__(self, task_type: str, task_input: str):
        self.type = task_type
        self.input = task_input
        self.tags = ["memory-loop", "test"]
        self.source = "e2e_test"
        self.node_type = "outcome"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def has_memory_context(result: dict) -> bool:
    return bool(result.get("used_memory_ids"))


def memory_nodes_exist(db: InMemoryDB, user_id: str) -> bool:
    return any(node.user_id == user_id for node in db.nodes.values())


def measure_difference(a: dict, b: dict) -> float:
    return float(len(str(b)) - len(str(a)))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestMemoryLoopE2E:
    def test_memory_improves_execution(self, monkeypatch):
        db = InMemoryDB()
        user_id = "test-user-e2e"
        task = FakeTask("analysis", "optimize lead generation strategy")

        def fake_create_memory_node(content, source=None, tags=None, user_id=None, db=None, node_type=None):
            node_id = uuid.uuid4()
            node = InMemoryNode(
                id=node_id,
                content=content,
                tags=tags or [],
                node_type=node_type or "outcome",
                user_id=user_id,
            )
            db.nodes[node_id] = node
            return {
                "id": str(node_id),
                "content": content,
                "tags": tags or [],
                "node_type": node.node_type,
            }

        monkeypatch.setattr("runtime.execution_loop.create_memory_node", fake_create_memory_node)

        orchestrator = MemoryOrchestrator(InMemoryDAO)

        def executor(task_obj, context):
            used = context.ids
            output = (
                f"no-memory:{task_obj.input}" if not used else f"with-memory:{context.formatted}"
            )
            return {
                "output": output,
                "used_memory_ids": used,
                "success_score": 0.9,
            }

        loop = ExecutionLoop(orchestrator, executor=executor)

        # Step 1: ensure clean state
        assert memory_nodes_exist(db, user_id) is False

        # Step 2: first run (no memory)
        result_1 = loop.run(task, user_id, db)
        assert result_1
        assert has_memory_context(result_1) is False

        # Step 3: verify memory write
        assert memory_nodes_exist(db, user_id) is True
        node = next(iter(db.nodes.values()))
        assert node.node_type in {"outcome", "insight"}
        assert node.content
        assert node.tags

        # Step 4: second run (with memory)
        result_2 = loop.run(task, user_id, db)

        # Step 5: verify recall
        assert has_memory_context(result_2) is True

        # Step 6: verify difference / memory impact
        assert result_2["output"] != result_1["output"]
        delta = measure_difference(result_1, result_2)
        print(f"Memory impact score: {delta}")

        # Step 7: third run (learning)
        result_3 = loop.run(task, user_id, db)
        assert has_memory_context(result_3) is True
        node = next(iter(db.nodes.values()))
        assert node.usage_count >= 1
        assert node.extra.get("success_rate") is not None

    def test_memory_failure_safe(self, monkeypatch):
        db = InMemoryDB()
        user_id = "test-user-e2e"
        task = FakeTask("analysis", "optimize lead generation strategy")

        def fake_create_memory_node(content, source=None, tags=None, user_id=None, db=None, node_type=None):
            node_id = uuid.uuid4()
            node = InMemoryNode(
                id=node_id,
                content=content,
                tags=tags or [],
                node_type=node_type or "outcome",
                user_id=user_id,
            )
            db.nodes[node_id] = node
            return {"id": str(node_id)}

        monkeypatch.setattr("runtime.execution_loop.create_memory_node", fake_create_memory_node)

        orchestrator = MemoryOrchestrator(FailingDAO)

        def executor(task_obj, context):
            return {
                "output": "fallback",
                "used_memory_ids": context.ids,
                "success_score": 0.5,
            }

        loop = ExecutionLoop(orchestrator, executor=executor)
        result = loop.run(task, user_id, db)
        assert result is not None
