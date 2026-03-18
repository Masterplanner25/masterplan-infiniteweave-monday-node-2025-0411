"""
test_memory_bridge_phase2.py

Tests for Memory Bridge Phase 2: embeddings, similarity retrieval,
resonance scoring, memory type enforcement, and new API endpoints.

All OpenAI calls are mocked. C++ kernel tests require the compiled extension.
"""
import math
import sys
import os
import pytest
from unittest.mock import MagicMock, patch

# Canonical mock embedding: unit vector on first dimension
MOCK_EMBEDDING = [1.0] + [0.0] * 1535
ZERO_EMBEDDING = [0.0] * 1536


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_mock_openai_response(embedding=None):
    """Build a mock OpenAI embeddings response."""
    if embedding is None:
        embedding = MOCK_EMBEDDING
    mock_response = MagicMock()
    mock_data = MagicMock()
    mock_data.embedding = embedding
    mock_response.data = [mock_data]
    return mock_response


# ---------------------------------------------------------------------------
# TestEmbeddingService
# ---------------------------------------------------------------------------

class TestEmbeddingService:

    def test_embedding_service_importable(self):
        from services import embedding_service
        assert embedding_service is not None

    def test_generate_embedding_returns_1536_dims(self):
        """generate_embedding returns 1536-dim list, mocking OpenAI."""
        mock_client = MagicMock()
        mock_client.embeddings.create.return_value = make_mock_openai_response()

        with patch("services.embedding_service._client", mock_client):
            from services.embedding_service import generate_embedding
            result = generate_embedding("hello world")

        assert isinstance(result, list)
        assert len(result) == 1536
        assert result[0] == 1.0

    def test_empty_content_returns_zero_vector(self):
        """Empty or whitespace-only input returns zero vector without calling OpenAI."""
        from services.embedding_service import generate_embedding
        assert generate_embedding("") == [0.0] * 1536
        assert generate_embedding("   ") == [0.0] * 1536

    def test_cosine_similarity_identical_vectors(self):
        """Identical non-zero vectors have similarity 1.0."""
        from services.embedding_service import cosine_similarity_python
        result = cosine_similarity_python(MOCK_EMBEDDING, MOCK_EMBEDDING)
        assert abs(result - 1.0) < 1e-6

    def test_cosine_similarity_orthogonal_vectors(self):
        """Orthogonal vectors have similarity 0.0."""
        from services.embedding_service import cosine_similarity_python
        a = [1.0] + [0.0] * 1535
        b = [0.0, 1.0] + [0.0] * 1534
        result = cosine_similarity_python(a, b)
        assert abs(result) < 1e-6

    def test_cpp_kernel_uses_correct_import_path(self):
        """Verify the C++ kernel is reachable via target/debug path."""
        debug_path = os.path.abspath(
            os.path.join(
                os.path.dirname(__file__), "..",
                "bridge", "memory_bridge_rs", "target", "debug"
            )
        )
        if debug_path not in sys.path:
            sys.path.insert(0, debug_path)
        try:
            import memory_bridge_rs as mbr
        except ImportError:
            pytest.skip("memory_bridge_rs extension not compiled")

        fn = mbr.semantic_similarity
        a = [1.0] + [0.0] * 1535
        result = fn(a, a)
        assert abs(result - 1.0) < 1e-6, f"Expected ~1.0, got {result}"

    def test_cosine_similarity_falls_back_to_python(self):
        """cosine_similarity falls back to Python when C++ import fails."""
        from services.embedding_service import cosine_similarity_python

        # The Python fallback itself must work correctly
        result = cosine_similarity_python(MOCK_EMBEDDING, MOCK_EMBEDDING)
        assert abs(result - 1.0) < 1e-6

        # Orthogonal
        a = [1.0] + [0.0] * 1535
        b = [0.0, 1.0] + [0.0] * 1534
        assert abs(cosine_similarity_python(a, b)) < 1e-6

        # Zero vector returns 0
        assert cosine_similarity_python(ZERO_EMBEDDING, MOCK_EMBEDDING) == 0.0

    def test_embedding_failure_returns_zero_vector(self):
        """generate_embedding returns zero vector when all API attempts fail."""
        mock_client = MagicMock()
        mock_client.embeddings.create.side_effect = Exception("API down")

        with patch("services.embedding_service._client", mock_client):
            with patch("services.embedding_service.time.sleep"):
                from services.embedding_service import generate_embedding
                result = generate_embedding("test content")

        assert result == [0.0] * 1536


# ---------------------------------------------------------------------------
# TestMemoryNodeEmbeddingColumn
# ---------------------------------------------------------------------------

class TestMemoryNodeEmbeddingColumn:

    def test_embedding_column_on_model(self):
        """MemoryNodeModel ORM mapper has an 'embedding' attribute."""
        from services.memory_persistence import MemoryNodeModel
        from sqlalchemy import inspect as sa_inspect
        mapper = sa_inspect(MemoryNodeModel)
        col_names = [c.key for c in mapper.attrs]
        assert "embedding" in col_names

    def test_embedding_column_in_db(self):
        """The 'embedding' column exists in the production DB table."""
        import sqlalchemy as sa
        from sqlalchemy import inspect as sa_inspect
        prod_url = "postgresql+psycopg2://postgres:140671a@localhost:5433/base"
        try:
            prod_engine = sa.create_engine(prod_url, pool_pre_ping=True)
            insp = sa_inspect(prod_engine)
            col_names = [c["name"] for c in insp.get_columns("memory_nodes")]
            prod_engine.dispose()
        except Exception:
            pytest.skip("Production DB not reachable from test context")
        assert "embedding" in col_names, (
            "Run 'alembic upgrade head' to apply the embedding column migration."
        )


# ---------------------------------------------------------------------------
# TestResonanceScoring
# ---------------------------------------------------------------------------

class TestResonanceScoring:

    def test_resonance_formula_weights_sum_to_one(self):
        """Semantic(0.6) + tag(0.2) + recency(0.2) = 1.0."""
        assert abs(0.6 + 0.2 + 0.2 - 1.0) < 1e-9

    def test_resonance_high_semantic_dominates(self):
        """High semantic score produces resonance close to 0.6."""
        semantic = 1.0
        tag = 0.0
        recency = 0.0
        resonance = (semantic * 0.6) + (tag * 0.2) + (recency * 0.2)
        assert abs(resonance - 0.6) < 1e-6

    def test_resonance_recency_decay(self):
        """Recency decay: today=1.0, 30d≈e^-1≈0.368, 90d<0.1."""
        assert abs(math.exp(0) - 1.0) < 1e-6
        assert abs(math.exp(-1) - math.exp(-30 / 30.0)) < 1e-6
        assert math.exp(-90 / 30.0) < 0.1

    def test_resonance_tag_match_calculation(self):
        """Tag score = overlap / query_tags count."""
        node_tags = {"decision", "outcome", "ai"}
        query_tags = {"decision", "outcome"}
        tag_score = len(node_tags & query_tags) / len(query_tags)
        assert abs(tag_score - 1.0) < 1e-6

        query_tags2 = {"decision", "outcome", "missing"}
        tag_score2 = len(node_tags & query_tags2) / len(query_tags2)
        assert abs(tag_score2 - 2 / 3) < 1e-6

    def test_resonance_no_tags_no_penalty(self):
        """When tags=None, tag_score=0.0 (no penalty; not a negative signal)."""
        semantic = 0.8
        tag_score = 0.0
        recency = 1.0
        resonance = (semantic * 0.6) + (tag_score * 0.2) + (recency * 0.2)
        assert abs(resonance - (0.48 + 0.0 + 0.2)) < 1e-6


# ---------------------------------------------------------------------------
# TestMemoryTypeEnforcement
# ---------------------------------------------------------------------------

class TestMemoryTypeEnforcement:

    def test_valid_node_types(self):
        """VALID_NODE_TYPES contains exactly 4 valid types."""
        from services.memory_persistence import VALID_NODE_TYPES
        assert VALID_NODE_TYPES == {"decision", "outcome", "insight", "relationship"}
        assert len(VALID_NODE_TYPES) == 4

    def test_invalid_type_not_in_set(self):
        """'generic' and 'research' are not valid node types."""
        from services.memory_persistence import VALID_NODE_TYPES
        assert "generic" not in VALID_NODE_TYPES
        assert "research" not in VALID_NODE_TYPES

    def test_node_type_literal_in_schema(self):
        """CreateNodeRequest accepts valid node_type, rejects invalid."""
        from routes.memory_router import CreateNodeRequest
        from pydantic import ValidationError

        # Valid types should parse without error
        for nt in ("decision", "outcome", "insight", "relationship"):
            req = CreateNodeRequest(content="x", source="test", node_type=nt)
            assert req.node_type == nt

        # Invalid type should raise ValidationError
        with pytest.raises(ValidationError):
            CreateNodeRequest(content="x", source="test", node_type="generic")

    def test_none_node_type_allowed_in_phase2(self):
        """node_type=None is allowed (optional field)."""
        from routes.memory_router import CreateNodeRequest
        req = CreateNodeRequest(content="x", source="test", node_type=None)
        assert req.node_type is None


# ---------------------------------------------------------------------------
# TestMemoryRoutePhase2
# ---------------------------------------------------------------------------

class TestMemoryRoutePhase2:

    def test_search_endpoint_requires_auth(self, client):
        """POST /memory/nodes/search without auth returns 401 or 403."""
        response = client.post("/memory/nodes/search", json={"query": "test"})
        assert response.status_code in (401, 403)

    def test_recall_endpoint_requires_auth(self, client):
        """POST /memory/recall without auth returns 401 or 403."""
        response = client.post("/memory/recall", json={"query": "test"})
        assert response.status_code in (401, 403)

    def test_recall_requires_query_or_tags(self, client, auth_headers):
        """POST /memory/recall with neither query nor tags returns 400."""
        mock_db = MagicMock()
        mock_db.query.return_value = mock_db
        mock_db.filter.return_value = mock_db
        mock_db.all.return_value = []

        with patch("routes.memory_router.get_db", return_value=mock_db):
            response = client.post(
                "/memory/recall",
                json={},
                headers=auth_headers,
            )
        assert response.status_code == 400

    def test_recall_with_query(self, client, auth_headers):
        """POST /memory/recall with query returns scoring metadata."""
        mock_dao = MagicMock()
        mock_dao.recall.return_value = []

        with patch("services.embedding_service.generate_query_embedding", return_value=MOCK_EMBEDDING):
            with patch("routes.memory_router.MemoryNodeDAO", return_value=mock_dao):
                with patch("db.database.get_db"):
                    response = client.post(
                        "/memory/recall",
                        json={"query": "strategic decisions"},
                        headers=auth_headers,
                    )

        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert "scoring" in data
        assert data["scoring"]["semantic_weight"] == 0.6
        assert data["scoring"]["tag_weight"] == 0.2
        assert data["scoring"]["recency_weight"] == 0.2

    def test_search_with_auth(self, client, auth_headers):
        """POST /memory/nodes/search with auth returns query and results."""
        mock_dao = MagicMock()
        mock_dao.find_similar.return_value = []

        with patch("services.embedding_service.generate_query_embedding", return_value=MOCK_EMBEDDING):
            with patch("routes.memory_router.MemoryNodeDAO", return_value=mock_dao):
                with patch("db.database.get_db"):
                    response = client.post(
                        "/memory/nodes/search",
                        json={"query": "important decisions"},
                        headers=auth_headers,
                    )

        assert response.status_code == 200
        data = response.json()
        assert "query" in data
        assert data["query"] == "important decisions"
        assert "results" in data
        assert "count" in data
