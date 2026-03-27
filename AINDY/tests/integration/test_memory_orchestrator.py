import pytest

from runtime.memory import MemoryOrchestrator


class FakeDAO:
    def __init__(self, db):
        self.db = db

    def recall(self, query=None, tags=None, limit=5, user_id=None, node_type=None):
        return [
            {
                "id": "n1",
                "content": "alpha memory",
                "node_type": "outcome",
                "tags": ["alpha"],
                "semantic_score": 0.9,
                "recency_score": 0.8,
                "success_rate": 0.7,
                "usage_frequency": 2,
                "graph_score": 0.1,
            },
            {
                "id": "n2",
                "content": "beta memory",
                "node_type": "insight",
                "tags": ["beta"],
                "semantic_score": 0.6,
                "recency_score": 0.6,
                "success_rate": 0.6,
                "usage_frequency": 0,
                "graph_score": 0.0,
            },
        ]


class EmptyDAO:
    def __init__(self, db):
        self.db = db

    def recall(self, **kwargs):
        return []


class FailingDAO:
    def __init__(self, db):
        self.db = db

    def recall(self, **kwargs):
        raise Exception("DB down")


class TestMemoryOrchestrator:
    def test_basic_recall_returns_context(self):
        orchestrator = MemoryOrchestrator(FakeDAO)
        context = orchestrator.get_context(
            user_id="user-1",
            query="alpha",
            task_type="analysis",
            db=object(),
            max_tokens=500,
        )
        assert context.items
        assert context.items[0].id == "n1"

    def test_token_limit_enforced(self):
        class LongDAO(FakeDAO):
            def recall(self, **kwargs):
                return [
                    {
                        "id": "n1",
                        "content": "x" * 2000,
                        "node_type": "outcome",
                        "tags": [],
                        "semantic_score": 0.9,
                        "recency_score": 0.9,
                        "success_rate": 0.9,
                        "usage_frequency": 1,
                        "graph_score": 0.1,
                    },
                    {
                        "id": "n2",
                        "content": "short",
                        "node_type": "outcome",
                        "tags": [],
                        "semantic_score": 0.8,
                        "recency_score": 0.8,
                        "success_rate": 0.8,
                        "usage_frequency": 1,
                        "graph_score": 0.1,
                    },
                ]

        orchestrator = MemoryOrchestrator(LongDAO)
        context = orchestrator.get_context(
            user_id="user-1",
            query="alpha",
            task_type="analysis",
            db=object(),
            max_tokens=100,
        )
        assert len(context.items) <= 1

    def test_empty_db_returns_safe_result(self):
        orchestrator = MemoryOrchestrator(EmptyDAO)
        context = orchestrator.get_context(
            user_id="user-1",
            query="alpha",
            task_type="analysis",
            db=object(),
            max_tokens=100,
        )
        assert context.items == []

    def test_scoring_order_correct(self):
        orchestrator = MemoryOrchestrator(FakeDAO)
        context = orchestrator.get_context(
            user_id="user-1",
            query="alpha",
            task_type="analysis",
            db=object(),
            max_tokens=500,
        )
        assert context.items[0].score >= context.items[1].score

    def test_filter_removes_low_score(self):
        class LowScoreDAO(FakeDAO):
            def recall(self, **kwargs):
                return [
                    {
                        "id": "low",
                        "content": "low",
                        "node_type": "outcome",
                        "tags": [],
                        "semantic_score": 0.1,
                        "recency_score": 0.0,
                        "success_rate": 0.0,
                        "usage_frequency": 0,
                        "graph_score": 0.0,
                    },
                    {
                        "id": "high",
                        "content": "high",
                        "node_type": "outcome",
                        "tags": [],
                        "semantic_score": 1.0,
                        "recency_score": 1.0,
                        "success_rate": 1.0,
                        "usage_frequency": 5,
                        "graph_score": 0.5,
                    },
                ]

        orchestrator = MemoryOrchestrator(LowScoreDAO)
        context = orchestrator.get_context(
            user_id="user-1",
            query="alpha",
            task_type="analysis",
            db=object(),
            max_tokens=500,
        )
        assert len(context.items) == 1
        assert context.items[0].id == "high"

    def test_failure_returns_empty_context(self):
        orchestrator = MemoryOrchestrator(FailingDAO)
        context = orchestrator.get_context(
            user_id="user-1",
            query="alpha",
            task_type="analysis",
            db=object(),
            max_tokens=500,
        )
        assert context.items == []
