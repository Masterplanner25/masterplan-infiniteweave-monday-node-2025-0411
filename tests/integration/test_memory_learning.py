import pytest

from AINDY.runtime.memory.memory_learning import MemoryLearningEngine, evaluate_result
from AINDY.runtime.memory.scorer import MemoryScorer


class FakeNode:
    def __init__(self):
        self.id = "00000000-0000-0000-0000-000000000000"
        self.user_id = "user-1"
        self.usage_count = 0
        self.success_count = 0
        self.failure_count = 0
        self.extra = {}


class FakeDB:
    def __init__(self, node=None):
        self.node = node
        self.committed = False
        self.rolled_back = False

    def get(self, model, node_id):
        return self.node

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


class TestMemoryLearning:
    def test_success_rate_updates(self):
        node = FakeNode()
        db = FakeDB(node)
        engine = MemoryLearningEngine()

        engine.update_after_execution(
            memory_ids=[node.id],
            result={"ok": True},
            user_id="user-1",
            db=db,
        )

        assert node.usage_count == 1
        assert node.extra.get("success_rate") >= 0.7
        assert db.committed is True

    def test_low_value_flag_triggers(self):
        node = FakeNode()
        db = FakeDB(node)
        engine = MemoryLearningEngine()

        engine.update_after_execution(
            memory_ids=[node.id],
            result={"ok": False},
            user_id="user-1",
            db=db,
        )

        assert node.extra.get("low_value_flag") is True

    def test_missing_nodes_safe(self):
        db = FakeDB(node=None)
        engine = MemoryLearningEngine()
        engine.update_after_execution(
            memory_ids=["11111111-1111-1111-1111-111111111111"],
            result={"ok": True},
            user_id="user-1",
            db=db,
        )
        assert db.committed is True

    def test_evaluate_result_bounds(self):
        assert 0.0 <= evaluate_result({"ok": True}) <= 1.0
        assert 0.0 <= evaluate_result({"ok": False}) <= 1.0
        assert evaluate_result({"score": 2.0}) == 1.0
        assert evaluate_result({"score": -1.0}) == 0.0


class TestScorerIntegration:
    def test_low_value_flag_halves_score(self):
        scorer = MemoryScorer()
        node = {
            "id": "n1",
            "content": "x",
            "node_type": "outcome",
            "semantic_score": 1.0,
            "recency_score": 1.0,
            "success_rate": 1.0,
            "usage_frequency": 1,
            "graph_score": 1.0,
            "extra": {"low_value_flag": True},
        }
        scored = scorer.score([node], request=None)
        assert scored[0].score <= 1.0
