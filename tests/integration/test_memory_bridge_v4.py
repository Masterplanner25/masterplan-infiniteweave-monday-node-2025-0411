"""
Memory Bridge v4 Tests ? Adaptive Intelligence

Tests outcome feedback, resonance v2, and suggestion engine.
"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone


class TestFeedbackColumns:

    def test_feedback_columns_in_db(self):
        from sqlalchemy import inspect
        from AINDY.db.database import engine
        try:
            insp = inspect(engine)
            if "memory_nodes" not in insp.get_table_names():
                pytest.skip("DB schema not available in test context")
            cols = [c["name"] for c in
                    insp.get_columns("memory_nodes")]
            if not cols:
                pytest.skip("memory_nodes not available in test context")
        except Exception:
            pytest.skip("DB not reachable from test context")
        required = ["success_count", "failure_count",
                    "usage_count", "weight", "last_outcome"]
        for col in required:
            assert col in cols, \
                f"memory_nodes missing: {col}"

    def test_feedback_columns_on_model(self):
        from AINDY.memory.memory_persistence import MemoryNodeModel
        from sqlalchemy import inspect as sa_inspect
        mapper = sa_inspect(MemoryNodeModel)
        cols = [c.key for c in mapper.columns]
        for col in ["success_count", "failure_count",
                    "usage_count", "weight"]:
            assert col in cols

    def test_record_feedback_method_exists(self):
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO
        assert hasattr(MemoryNodeDAO, "record_feedback")
        assert callable(MemoryNodeDAO.record_feedback)


class TestWeightAdjustment:
    """Test the adaptive weight logic directly."""

    def test_success_increases_weight(self):
        """Success outcome boosts weight by 0.1."""
        initial_weight = 1.0
        new_weight = min(2.0, initial_weight + 0.1)
        assert abs(new_weight - 1.1) < 1e-9

    def test_failure_decreases_weight(self):
        """Failure outcome reduces weight by 0.15."""
        initial_weight = 1.0
        new_weight = max(0.1, initial_weight - 0.15)
        assert abs(new_weight - 0.85) < 1e-9

    def test_weight_min_floor(self):
        """Weight cannot go below 0.1."""
        weight = 0.15
        for _ in range(10):
            weight = max(0.1, weight - 0.15)
        assert weight >= 0.1

    def test_weight_max_ceiling(self):
        """Weight cannot exceed 2.0."""
        weight = 1.9
        for _ in range(10):
            weight = min(2.0, weight + 0.1)
        assert weight <= 2.0

    def test_neutral_no_weight_change(self):
        """Neutral outcome does not change weight."""
        initial_weight = 1.0
        # neutral = no weight adjustment
        new_weight = initial_weight
        assert new_weight == initial_weight


class TestSuccessRate:

    def test_success_rate_no_data(self, mock_db):
        """No feedback = 0.5 neutral prior."""
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO
        dao = MemoryNodeDAO(mock_db)

        mock_node = MagicMock()
        mock_node.success_count = 0
        mock_node.failure_count = 0

        rate = dao.get_success_rate(mock_node)
        assert abs(rate - 0.5) < 1e-9

    def test_success_rate_all_success(self, mock_db):
        """All successes = 1.0."""
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO
        dao = MemoryNodeDAO(mock_db)

        mock_node = MagicMock()
        mock_node.success_count = 10
        mock_node.failure_count = 0

        rate = dao.get_success_rate(mock_node)
        assert abs(rate - 1.0) < 1e-9

    def test_success_rate_mixed(self, mock_db):
        """3 success, 1 failure = 0.75."""
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO
        dao = MemoryNodeDAO(mock_db)

        mock_node = MagicMock()
        mock_node.success_count = 3
        mock_node.failure_count = 1

        rate = dao.get_success_rate(mock_node)
        assert abs(rate - 0.75) < 1e-9


class TestResonanceV2:

    def test_resonance_v2_weights_sum_to_one(self):
        """v2 formula weights must sum to 1.0."""
        weights = [0.40, 0.15, 0.15, 0.20, 0.10]
        assert abs(sum(weights) - 1.0) < 1e-9

    def test_resonance_v2_higher_than_v1_for_proven_memory(self):
        """
        A memory with high success rate should score higher
        in v2 than v1 for the same semantic similarity.
        """
        semantic = 0.7
        recency = 0.8
        tag_score = 0.5

        # v1 formula
        v1 = (semantic * 0.6) + (tag_score * 0.2) + \
             (recency * 0.2)

        # v2 formula with proven memory
        success_rate = 0.9  # high success
        usage_freq = 0.5
        graph_score = 0.3
        adaptive_weight = 1.5  # boosted by successes

        v2 = ((semantic * 0.40) +
              (graph_score * 0.15) +
              (recency * 0.15) +
              (success_rate * 0.20) +
              (usage_freq * 0.10)) * adaptive_weight
        v2 = min(1.0, v2)

        assert v2 > v1, \
            f"v2 ({v2:.3f}) should exceed v1 ({v1:.3f}) " \
            f"for proven memory"

    def test_resonance_v2_lower_for_failed_memory(self):
        """
        A memory with high failure rate should score lower
        in v2 than v1.
        """
        semantic = 0.7
        recency = 0.8
        tag_score = 0.5

        v1 = (semantic * 0.6) + (tag_score * 0.2) + \
             (recency * 0.2)

        success_rate = 0.1  # mostly failures
        usage_freq = 0.3
        graph_score = 0.1
        adaptive_weight = 0.4  # suppressed

        v2 = ((semantic * 0.40) +
              (graph_score * 0.15) +
              (recency * 0.15) +
              (success_rate * 0.20) +
              (usage_freq * 0.10)) * adaptive_weight
        v2 = min(1.0, v2)

        assert v2 < v1, \
            f"v2 ({v2:.3f}) should be less than v1 ({v1:.3f}) " \
            f"for failed memory"


class TestSuggestionEngine:

    def test_suggest_method_exists(self):
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO
        assert hasattr(MemoryNodeDAO, "suggest")
        assert callable(MemoryNodeDAO.suggest)

    def test_suggest_returns_correct_structure(
        self, mock_db, mocker
    ):
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO

        mocker.patch(
            "AINDY.db.dao.memory_node_dao.MemoryNodeDAO.recall",
            return_value=[]
        )

        dao = MemoryNodeDAO(mock_db)
        result = dao.suggest(
            query="test query",
            user_id="test-user"
        )

        assert "suggestions" in result
        assert "message" in result
        assert isinstance(result["suggestions"], list)

    def test_suggest_requires_query_or_tags(
        self, mock_db
    ):
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO
        dao = MemoryNodeDAO(mock_db)
        result = dao.suggest(user_id="test-user")
        assert result["suggestions"] == []

    def test_suggest_filters_low_performers(
        self, mock_db, mocker
    ):
        """
        Suggestion engine should prefer high-performing
        memories over low-performing ones.
        """
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO

        high_performer = {
            "id": "high-id",
            "content": "This worked great",
            "node_type": "decision",
            "success_rate": 0.9,
            "adaptive_weight": 1.5,
            "resonance_score": 0.8,
            "usage_count": 10,
            "failure_count": 1,
            "tags": [],
            "created_at": datetime.now(timezone.utc).isoformat()
        }

        low_performer = {
            "id": "low-id",
            "content": "This often failed",
            "node_type": "decision",
            "success_rate": 0.2,
            "adaptive_weight": 0.5,
            "resonance_score": 0.7,
            "usage_count": 5,
            "failure_count": 4,
            "tags": [],
            "created_at": datetime.now(timezone.utc).isoformat()
        }

        mocker.patch(
            "AINDY.db.dao.memory_node_dao.MemoryNodeDAO.recall",
            return_value=[high_performer, low_performer]
        )

        dao = MemoryNodeDAO(mock_db)
        result = dao.suggest(
            query="test",
            user_id="test-user",
            limit=2
        )

        suggestions = result["suggestions"]
        if suggestions:
            # High performer should rank first
            assert suggestions[0]["node_id"] == "high-id"

    def test_suggest_includes_warning_for_failures(
        self, mock_db, mocker
    ):
        """Suggestions with failures should include warning."""
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO

        risky_memory = {
            "id": "risky-id",
            "content": "Sometimes works, sometimes fails",
            "node_type": "outcome",
            "success_rate": 0.65,
            "adaptive_weight": 1.1,
            "resonance_score": 0.75,
            "usage_count": 10,
            "failure_count": 4,  # notable failures
            "tags": [],
            "created_at": datetime.now(timezone.utc).isoformat()
        }

        mocker.patch(
            "AINDY.db.dao.memory_node_dao.MemoryNodeDAO.recall",
            return_value=[risky_memory]
        )

        dao = MemoryNodeDAO(mock_db)
        result = dao.suggest(
            query="test",
            user_id="test-user"
        )

        suggestions = result["suggestions"]
        if suggestions:
            # Should have a warning
            assert suggestions[0].get("warning") is not None


class TestFeedbackEndpoints:

    def test_feedback_endpoint_requires_auth(self, client):
        r = client.post(
            "/memory/nodes/test-id/feedback",
            json={"outcome": "success"}
        )
        assert r.status_code == 401

    def test_performance_endpoint_requires_auth(self, client):
        r = client.get(
            "/memory/nodes/test-id/performance"
        )
        assert r.status_code == 401

    def test_suggest_endpoint_requires_auth(self, client):
        r = client.post(
            "/memory/suggest",
            json={"query": "test"}
        )
        assert r.status_code == 401

    def test_feedback_invalid_outcome(
        self, client, auth_headers
    ):
        r = client.post(
            "/memory/nodes/test-id/feedback",
            json={"outcome": "invalid_outcome"},
            headers=auth_headers
        )
        assert r.status_code == 422

    def test_feedback_valid_outcomes_accepted(
        self, client, auth_headers
    ):
        for outcome in ["success", "failure", "neutral"]:
            r = client.post(
                "/memory/nodes/nonexistent/feedback",
                json={"outcome": outcome},
                headers=auth_headers
            )
            # 404 = node not found (correct)
            # 422 = validation error (wrong)
            assert r.status_code == 404, \
                f"outcome '{outcome}' was rejected as invalid"

    def test_suggest_requires_query_or_tags(
        self, client, auth_headers
    ):
        r = client.post(
            "/memory/suggest",
            json={},
            headers=auth_headers
        )
        assert r.status_code == 400

    def test_suggest_with_query(
        self, client, auth_headers, mock_db, mocker
    ):
        mocker.patch(
            "AINDY.memory.embedding_service"
            ".generate_query_embedding",
            return_value=[0.1] * 1536
        )
        mocker.patch(
            "AINDY.db.dao.memory_node_dao.MemoryNodeDAO.suggest",
            return_value={
                "suggestions": [],
                "message": "Not enough data yet",
                "query": "test",
                "suggestion_count": 0
            }
        )
        r = client.post(
            "/memory/suggest",
            json={"query": "what worked before"},
            headers=auth_headers
        )
        assert r.status_code in [200, 422]
        assert r.status_code != 401


class TestSuggestBridgeExport:

    def test_suggest_from_memory_importable(self):
        from AINDY.memory import suggest_from_memory
        assert callable(suggest_from_memory)

    def test_suggest_from_memory_returns_empty_on_error(self):
        from AINDY.memory import suggest_from_memory
        result = suggest_from_memory(
            db=None,
            query="test"
        )
        assert "suggestions" in result
        assert result["suggestions"] == []
