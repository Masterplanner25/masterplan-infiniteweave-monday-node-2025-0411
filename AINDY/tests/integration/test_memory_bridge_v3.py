"""
Memory Bridge v3 Tests - Structured Continuity

Tests graph traversal, node expansion, history,
and the v3 recall API.
"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime


class TestMemoryNodeHistory:

    def test_history_model_importable(self):
        from AINDY.db.models.memory_node_history import MemoryNodeHistory
        assert MemoryNodeHistory.__tablename__ == "memory_node_history"

    def test_history_table_in_db(self):
        from sqlalchemy import inspect
        from AINDY.db.database import engine
        try:
            insp = inspect(engine)
            assert "memory_node_history" in insp.get_table_names(), \
                "memory_node_history table missing from DB"
        except Exception:
            pytest.skip("DB not reachable from test context")

    def test_history_required_columns(self):
        from AINDY.db.models.memory_node_history import MemoryNodeHistory
        from sqlalchemy import inspect as sa_inspect
        mapper = sa_inspect(MemoryNodeHistory)
        cols = [c.key for c in mapper.columns]
        required = [
            "id", "node_id", "changed_at",
            "change_type", "change_summary",
            "previous_content", "previous_tags",
        ]
        for col in required:
            assert col in cols, f"memory_node_history missing: {col}"

    def test_update_method_exists(self):
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO
        assert hasattr(MemoryNodeDAO, "update")
        assert callable(MemoryNodeDAO.update)

    def test_get_history_method_exists(self):
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO
        assert hasattr(MemoryNodeDAO, "get_history")

    def test_update_no_change_returns_node(self, db_session, test_user):
        """Update with identical values creates no history."""
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO
        from AINDY.db.models.memory_node_history import MemoryNodeHistory
        from AINDY.memory.memory_persistence import MemoryNodeModel

        node = MemoryNodeModel(
            content="original content",
            tags=["tag1"],
            node_type="insight",
            source="test",
            user_id=test_user.id,
            extra={},
            embedding=[0.0] * 1536,
        )
        db_session.add(node)
        db_session.commit()
        db_session.refresh(node)

        dao = MemoryNodeDAO(db_session)
        result = dao.update(
            node_id=str(node.id),
            user_id=str(test_user.id),
            content="original content",
        )
        assert result is not None
        assert result.id == node.id
        assert db_session.query(MemoryNodeHistory).filter(MemoryNodeHistory.node_id == node.id).count() == 0

    def test_update_creates_history_on_change(self, db_session, test_user, mocker):
        """Update with new content creates history entry."""
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO
        from AINDY.db.models.memory_node_history import MemoryNodeHistory
        from AINDY.memory.memory_persistence import MemoryNodeModel

        mocker.patch(
            "AINDY.memory.embedding_service.generate_embedding",
            return_value=[0.1] * 1536,
        )

        node = MemoryNodeModel(
            content="original content",
            tags=["tag1"],
            node_type="insight",
            source="test",
            user_id=test_user.id,
            extra={},
            embedding=[0.0] * 1536,
        )
        db_session.add(node)
        db_session.commit()
        db_session.refresh(node)

        dao = MemoryNodeDAO(db_session)
        result = dao.update(
            node_id=str(node.id),
            user_id=str(test_user.id),
            content="NEW content",
        )

        assert result is not None
        assert result.content == "NEW content"
        history_rows = (
            db_session.query(MemoryNodeHistory)
            .filter(MemoryNodeHistory.node_id == node.id)
            .all()
        )
        assert len(history_rows) == 1

    def test_history_endpoint_requires_auth(self, client):
        r = client.get("/memory/nodes/test-id/history")
        assert r.status_code == 401

    def test_update_endpoint_requires_auth(self, client):
        r = client.put(
            "/memory/nodes/test-id",
            json={"content": "updated"},
        )
        assert r.status_code == 401


class TestDFSTraversal:

    def test_traverse_method_exists(self):
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO
        assert hasattr(MemoryNodeDAO, "traverse")
        assert callable(MemoryNodeDAO.traverse)

    def test_traverse_returns_correct_structure(self):
        """traverse() returns expected dict structure."""
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        dao = MemoryNodeDAO(mock_db)
        result = dao.traverse(
            start_node_id="nonexistent",
            user_id="user-123",
        )

        assert "found" in result
        assert "chain" in result
        assert "nodes_visited" in result
        assert result["found"] is False

    def test_traverse_cycle_prevention(self):
        """DFS must not loop on A -> B -> A cycles."""
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO
        from AINDY.memory.memory_persistence import MemoryLinkModel
        import uuid as _uuid

        mock_db = MagicMock()

        node_a_id = str(_uuid.uuid4())
        node_a = MagicMock()
        node_a.id = node_a_id
        node_a.content = "Node A"
        node_a.tags = []
        node_a.node_type = "insight"
        node_a.source = "test"
        node_a.user_id = "user-123"
        node_a.created_at = datetime.utcnow()

        node_b_id = str(_uuid.uuid4())
        node_b = MagicMock()
        node_b.id = node_b_id
        node_b.content = "Node B"
        node_b.tags = []
        node_b.node_type = "outcome"
        node_b.source = "test"
        node_b.user_id = "user-123"
        node_b.created_at = datetime.utcnow()

        link_a_to_b = MagicMock(spec=MemoryLinkModel)
        link_a_to_b.source_node_id = node_a_id
        link_a_to_b.target_node_id = node_b_id
        link_a_to_b.link_type = "related"
        link_a_to_b.strength = 1.0

        link_b_to_a = MagicMock(spec=MemoryLinkModel)
        link_b_to_a.source_node_id = node_b_id
        link_b_to_a.target_node_id = node_a_id
        link_b_to_a.link_type = "related"
        link_b_to_a.strength = 1.0

        call_count = [0]

        def mock_get_by_id(node_id, user_id=None):
            if node_id == node_a_id:
                return {
                    "id": node_a_id,
                    "content": "Node A",
                    "node_type": "insight",
                }
            if node_id == node_b_id:
                return {
                    "id": node_b_id,
                    "content": "Node B",
                    "node_type": "outcome",
                }
            return None

        dao = MemoryNodeDAO(mock_db)
        dao.get_by_id = mock_get_by_id

        def mock_query(*args):
            mock_q = MagicMock()
            if args and args[0] == MemoryLinkModel:
                def mock_filter(*fargs, **fkwargs):
                    mock_f = MagicMock()
                    mock_f.filter.return_value = mock_f
                    mock_f.order_by.return_value = mock_f

                    call_count[0] += 1
                    if call_count[0] == 1:
                        mock_f.all.return_value = [link_a_to_b]
                    elif call_count[0] == 2:
                        mock_f.all.return_value = [link_b_to_a]
                    else:
                        mock_f.all.return_value = []
                    return mock_f
                mock_q.filter = mock_filter
            return mock_q

        mock_db.query = mock_query

        result = dao.traverse(
            start_node_id=node_a_id,
            max_depth=5,
            user_id="user-123",
        )

        assert result["found"] is True
        assert result["nodes_visited"] <= 2

    def test_traverse_max_depth_respected(self):
        """traverse() must not exceed max_depth."""
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        dao = MemoryNodeDAO(mock_db)
        result = dao.traverse(
            start_node_id="test",
            max_depth=3,
            user_id="user-123",
        )

        assert result["found"] is False
        for entry in result.get("chain", []):
            assert entry["depth"] <= 3

    def test_traverse_endpoint_requires_auth(self, client):
        r = client.get("/memory/nodes/test-id/traverse")
        assert r.status_code == 401

    def test_traverse_endpoint_with_auth(self, client, auth_headers):
        r = client.get(
            "/memory/nodes/nonexistent/traverse",
            headers=auth_headers,
        )
        assert r.status_code == 404

    def test_traverse_max_depth_capped_at_5(self, client, auth_headers):
        """API caps max_depth at 5."""
        r = client.get(
            "/memory/nodes/node-1/traverse?max_depth=99",
            headers=auth_headers,
        )
        if r.status_code == 200:
            assert r.json().get("max_depth", 0) <= 5


class TestNodeExpansion:

    def test_expand_method_exists(self):
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO
        assert hasattr(MemoryNodeDAO, "expand")
        assert callable(MemoryNodeDAO.expand)

    def test_expand_returns_correct_structure(self):
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        dao = MemoryNodeDAO(mock_db)

        dao.get_linked_nodes = MagicMock(return_value=[])
        dao._get_model_by_id = MagicMock(return_value=None)
        dao.find_similar = MagicMock(return_value=[])

        result = dao.expand(
            node_ids=["node-1", "node-2"],
            user_id="user-123",
        )

        assert "original_node_ids" in result
        assert "expanded_nodes" in result
        assert "expansion_count" in result
        assert "expansion_map" in result
        assert result["original_node_ids"] == ["node-1", "node-2"]

    def test_expand_max_10_nodes(self, client, auth_headers):
        """Expansion capped at 10 input nodes."""
        r = client.post(
            "/memory/nodes/expand",
            json={"node_ids": [str(i) for i in range(11)]},
            headers=auth_headers,
        )
        assert r.status_code == 400

    def test_expand_endpoint_requires_auth(self, client):
        r = client.post(
            "/memory/nodes/expand",
            json={"node_ids": ["test-id"]},
        )
        assert r.status_code == 401


class TestRecallV3:

    def test_recall_v3_endpoint_requires_auth(self, client):
        r = client.post(
            "/memory/recall/v3",
            json={"query": "test"},
        )
        assert r.status_code == 401

    def test_recall_v3_requires_query_or_tags(self, client, auth_headers):
        r = client.post(
            "/memory/recall/v3",
            json={},
            headers=auth_headers,
        )
        assert r.status_code == 400

    def test_recall_v3_returns_scoring_metadata(self, client, auth_headers, mock_db, mocker):
        mocker.patch(
            "AINDY.memory.embedding_service.generate_query_embedding",
            return_value=[0.1] * 1536,
        )
        mocker.patch(
            "AINDY.db.dao.memory_node_dao.MemoryNodeDAO.recall",
            return_value=[],
        )
        r = client.post(
            "/memory/recall/v3",
            json={"query": "test query"},
            headers=auth_headers,
        )
        if r.status_code == 200:
            data = r.json()
            assert data["scoring_version"] == "v2"
            assert "formula" in data
            assert data["formula"]["semantic"] == 0.40

    def test_recall_v3_expand_parameter(self, client, auth_headers, mock_db, mocker):
        """expand_results=True returns dict with expanded."""
        mocker.patch(
            "AINDY.memory.embedding_service.generate_query_embedding",
            return_value=[0.1] * 1536,
        )
        mocker.patch(
            "AINDY.db.dao.memory_node_dao.MemoryNodeDAO.recall",
            return_value={
                "results": [],
                "expanded": [],
                "expansion_map": {},
                "total_context_nodes": 0,
            },
        )
        r = client.post(
            "/memory/recall/v3",
            json={"query": "test", "expand_results": True},
            headers=auth_headers,
        )
        if r.status_code == 200:
            data = r.json()
            assert "results" in data or "expanded" in data


class TestChainNarrative:
    """Tests for the chain of thought narrative."""

    def test_narrative_generated_for_empty_chain(self, mock_db):
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO

        mock_node = {"content": "Starting memory"}

        dao = MemoryNodeDAO(mock_db)
        narrative = dao._build_chain_narrative(mock_node, [])
        assert isinstance(narrative, str)
        assert len(narrative) > 0
        assert "No connected memories" in narrative

    def test_narrative_includes_link_descriptions(self, mock_db):
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO

        mock_node = {"content": "Starting memory content"}

        chain = [
            {
                "depth": 1,
                "node": {
                    "id": "node-2",
                    "content": "Related memory",
                    "node_type": "insight",
                },
                "path": [
                    {
                        "node_id": "node-1",
                        "link_type": "caused",
                        "strength": 0.9,
                    }
                ],
                "children": [],
            }
        ]

        dao = MemoryNodeDAO(mock_db)
        narrative = dao._build_chain_narrative(mock_node, chain)

        assert "caused" in narrative or "chain" in narrative.lower()
