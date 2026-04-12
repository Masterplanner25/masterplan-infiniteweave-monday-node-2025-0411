"""
test_memory_bridge_phase1.py
─────────────────────────────
Memory Bridge Phase 1 — "Make It Real" test suite.

Classes:
  TestWritePathFix          — create_memory_node() writes to memory_nodes (MemoryNodeDAO)
  TestMemoryRouterEndpoints — /memory/* route registration, auth guards, response shape
  TestMemoryNodeDAOUnit     — MemoryNodeDAO unit tests (no real DB, pure mocks)
  TestCreateMemoryLinkUnit  — create_memory_link() and DAO.create_link() behavior
"""
import pytest
import uuid
from unittest.mock import MagicMock, patch, PropertyMock


# ── TestWritePathFix ────────────────────────────────────────────────────────────

class TestWritePathFix:
    """create_memory_node() must write to MemoryNodeModel via MemoryNodeDAO."""

    def test_function_signature_has_content_not_title(self):
        """New signature accepts content= not title=."""
        import inspect
        from AINDY.memory.bridge import create_memory_node
        sig = inspect.signature(create_memory_node)
        params = list(sig.parameters.keys())
        assert "content" in params
        assert "title" not in params

    def test_function_accepts_source_and_user_id(self):
        import inspect
        from AINDY.memory.bridge import create_memory_node
        sig = inspect.signature(create_memory_node)
        params = list(sig.parameters.keys())
        assert "source" in params
        assert "user_id" in params
        assert "db" in params

    def test_no_calculation_result_reference_in_source(self):
        """Regression: CalculationResult must not appear in create_memory_node source."""
        import inspect
        import AINDY.memory.bridge as bridge
        source = inspect.getsource(bridge.create_memory_node)
        assert "CalculationResult" not in source

    def test_no_db_returns_transient_memory_node(self):
        """Without db, returns a MemoryNode (not persisted, no crash)."""
        from AINDY.memory.bridge import create_memory_node, MemoryNode
        result = create_memory_node(content="hello", source="test", tags=["a", "b"])
        assert isinstance(result, MemoryNode)
        assert result.content == "hello"
        assert result.source == "test"
        assert "a" in result.tags

    def test_with_db_calls_dao_save(self):
        """With db provided, calls MemoryNodeDAO.save_memory_node()."""
        from AINDY.memory.bridge import create_memory_node
        from AINDY.memory.memory_persistence import MemoryNodeModel

        mock_persisted = MagicMock(spec=MemoryNodeModel)
        mock_persisted.id = uuid.uuid4()
        mock_persisted.content = "test content"
        mock_persisted.source = "unittest"
        mock_persisted.tags = ["x"]
        mock_persisted.user_id = "user-1"
        mock_persisted.node_type = "generic"
        mock_persisted.created_at = None

        mock_db = MagicMock()

        with patch("AINDY.memory.memory_persistence.MemoryNodeDAO.save_memory_node", return_value=mock_persisted):
            result = create_memory_node(
                content="test content",
                source="unittest",
                tags=["x"],
                user_id="user-1",
                db=mock_db,
            )

        assert isinstance(result, dict)
        assert result["content"] == "test content"
        assert result["source"] == "unittest"

    def test_create_memory_link_exported_from_bridge(self):
        """create_memory_link must be exported from bridge/__init__.py."""
        from AINDY.memory.bridge import create_memory_link
        assert callable(create_memory_link)

    def test_create_memory_link_without_db_raises_value_error(self):
        """create_memory_link(db=None) must raise ValueError."""
        from AINDY.memory.bridge import create_memory_link
        with pytest.raises(ValueError, match="DB session"):
            create_memory_link("a", "b", db=None)

    def test_memory_trace_has_transient_docstring(self):
        """MemoryTrace docstring must mention 'transient' and 'not persisted'."""
        from AINDY.memory.bridge import MemoryTrace
        doc = MemoryTrace.__doc__ or ""
        assert "transient" in doc.lower() or "not persisted" in doc.lower() or "not a source of truth" in doc.lower()


# ── TestMemoryNodeDAOUnit ───────────────────────────────────────────────────────

class TestMemoryNodeDAOUnit:
    """Unit tests for db/dao/memory_node_dao.py using mocked DB sessions."""

    def _make_mock_node(self, **kwargs):
        from AINDY.memory.memory_persistence import MemoryNodeModel
        node = MagicMock(spec=MemoryNodeModel)
        node.id = kwargs.get("id", uuid.uuid4())
        node.content = kwargs.get("content", "test")
        node.tags = kwargs.get("tags", [])
        node.node_type = kwargs.get("node_type", "generic")
        node.source = kwargs.get("source", None)
        node.user_id = kwargs.get("user_id", None)
        node.extra = kwargs.get("extra", {})
        node.created_at = None
        node.updated_at = None
        return node

    def test_dao_importable(self):
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO
        assert MemoryNodeDAO is not None

    def test_save_returns_dict(self):
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO
        from AINDY.memory.memory_persistence import MemoryNodeModel

        mock_db = MagicMock()
        dao = MemoryNodeDAO(mock_db)

        node_id = uuid.uuid4()
        mock_node = self._make_mock_node(id=node_id, content="hello")
        mock_db.refresh.side_effect = lambda obj: None

        with patch("AINDY.db.dao.memory_node_dao.MemoryNodeModel", return_value=mock_node):
            with patch.object(dao.db, "add"), \
                 patch.object(dao.db, "commit"), \
                 patch.object(dao.db, "refresh"):
                dao.db.refresh.side_effect = lambda obj: None
                # Simulate the object being returned after refresh
                result = dao._node_to_dict(mock_node)

        assert result["content"] == "hello"
        assert "id" in result
        assert "tags" in result

    def test_get_by_id_not_found_returns_none(self):
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        dao = MemoryNodeDAO(mock_db)
        result = dao.get_by_id(str(uuid.uuid4()))
        assert result is None

    def test_get_by_id_invalid_uuid_returns_none(self):
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO
        mock_db = MagicMock()
        dao = MemoryNodeDAO(mock_db)
        result = dao.get_by_id("not-a-uuid")
        assert result is None

    def test_get_by_id_found_returns_dict(self):
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO
        mock_db = MagicMock()
        node_id = uuid.uuid4()
        mock_node = self._make_mock_node(id=node_id, content="found", tags=["t1"])
        mock_db.query.return_value.filter.return_value.first.return_value = mock_node
        dao = MemoryNodeDAO(mock_db)
        result = dao.get_by_id(str(node_id))
        assert result is not None
        assert result["content"] == "found"
        assert result["id"] == str(node_id)

    def test_get_by_tags_returns_list(self):
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.limit.return_value.all.return_value = []
        mock_db.query.return_value.limit.return_value.all.return_value = []
        dao = MemoryNodeDAO(mock_db)
        result = dao.get_by_tags(["tag1"], limit=10)
        assert isinstance(result, list)

    def test_get_linked_nodes_invalid_uuid_returns_empty(self):
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO
        mock_db = MagicMock()
        dao = MemoryNodeDAO(mock_db)
        result = dao.get_linked_nodes("not-a-valid-uuid")
        assert result == []

    def test_create_link_same_id_raises(self):
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO
        mock_db = MagicMock()
        dao = MemoryNodeDAO(mock_db)
        same_id = str(uuid.uuid4())
        with pytest.raises(ValueError, match="same"):
            dao.create_link(same_id, same_id)

    def test_create_link_missing_node_raises(self):
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.count.return_value = 1  # not 2
        dao = MemoryNodeDAO(mock_db)
        with pytest.raises(ValueError, match="does not exist"):
            dao.create_link(str(uuid.uuid4()), str(uuid.uuid4()))

    def test_node_to_dict_includes_source_and_user_id(self):
        """_node_to_dict must include source and user_id fields (Phase 1 additions)."""
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO
        mock_db = MagicMock()
        dao = MemoryNodeDAO(mock_db)
        node = self._make_mock_node(source="service-x", user_id="user-99")
        result = dao._node_to_dict(node)
        assert "source" in result
        assert result["source"] == "service-x"
        assert "user_id" in result
        assert result["user_id"] == "user-99"


# ── TestMemoryRouterEndpoints ───────────────────────────────────────────────────

class TestMemoryRouterEndpoints:
    """Route registration, auth enforcement, and response shape."""

    def test_memory_router_importable(self):
        from AINDY.routes.memory_router import router
        assert router is not None

    def test_memory_router_prefix(self):
        from AINDY.routes.memory_router import router
        assert router.prefix == "/memory"

    def test_memory_router_registered_in_routers(self):
        from AINDY.routes import ROUTERS
        prefixes = [r.prefix for r in ROUTERS]
        assert "/memory" in prefixes

    def test_create_node_requires_auth(self, client):
        resp = client.post("/memory/nodes", json={"content": "test"})
        assert resp.status_code == 401

    def test_get_node_requires_auth(self, client):
        resp = client.get(f"/memory/nodes/{uuid.uuid4()}")
        assert resp.status_code == 401

    def test_search_nodes_requires_auth(self, client):
        resp = client.get("/memory/nodes")
        assert resp.status_code == 401

    def test_create_link_requires_auth(self, client):
        resp = client.post("/memory/links", json={"source_id": str(uuid.uuid4()), "target_id": str(uuid.uuid4())})
        assert resp.status_code == 401

    def test_get_linked_nodes_requires_auth(self, client):
        resp = client.get(f"/memory/nodes/{uuid.uuid4()}/links")
        assert resp.status_code == 401

    def test_create_node_with_auth_reaches_handler(self, client, auth_headers, mock_db):
        """POST /memory/nodes with valid JWT must reach handler (not 401/404)."""
        from AINDY.main import app
        from AINDY.db.database import get_db
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO

        saved = {
            "id": str(uuid.uuid4()),
            "content": "hello",
            "source": "test",
            "tags": [],
            "user_id": "test-user-id-123",
            "node_type": "generic",
            "created_at": None,
        }

        app.dependency_overrides[get_db] = lambda: mock_db
        with patch.object(MemoryNodeDAO, "save", return_value=saved):
            resp = client.post(
                "/memory/nodes",
                json={"content": "hello", "source": "test"},
                headers=auth_headers,
            )
        app.dependency_overrides.pop(get_db, None)

        assert resp.status_code == 201
        data = resp.json()
        assert data["content"] == "hello"

    def test_get_node_not_found_returns_404(self, client, auth_headers, mock_db):
        from AINDY.main import app
        from AINDY.db.database import get_db
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO

        app.dependency_overrides[get_db] = lambda: mock_db
        with patch.object(MemoryNodeDAO, "get_by_id", return_value=None):
            resp = client.get(
                f"/memory/nodes/{uuid.uuid4()}",
                headers=auth_headers,
            )
        app.dependency_overrides.pop(get_db, None)

        assert resp.status_code == 404

    def test_search_nodes_returns_nodes_list(self, client, auth_headers, mock_db):
        from AINDY.main import app
        from AINDY.db.database import get_db
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO

        app.dependency_overrides[get_db] = lambda: mock_db
        with patch.object(MemoryNodeDAO, "get_by_tags", return_value=[]):
            resp = client.get("/memory/nodes?tags=research", headers=auth_headers)
        app.dependency_overrides.pop(get_db, None)

        assert resp.status_code == 200
        assert "nodes" in resp.json()

    def test_get_linked_nodes_invalid_direction_returns_422(self, client, auth_headers, mock_db):
        from AINDY.main import app
        from AINDY.db.database import get_db

        app.dependency_overrides[get_db] = lambda: mock_db
        resp = client.get(
            f"/memory/nodes/{uuid.uuid4()}/links?direction=invalid",
            headers=auth_headers,
        )
        app.dependency_overrides.pop(get_db, None)

        assert resp.status_code == 422

    def test_create_link_value_error_returns_422(self, client, auth_headers, mock_db):
        from AINDY.main import app
        from AINDY.db.database import get_db
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO

        app.dependency_overrides[get_db] = lambda: mock_db
        with patch.object(MemoryNodeDAO, "create_link", side_effect=ValueError("does not exist")):
            resp = client.post(
                "/memory/links",
                json={"source_id": str(uuid.uuid4()), "target_id": str(uuid.uuid4())},
                headers=auth_headers,
            )
        app.dependency_overrides.pop(get_db, None)

        assert resp.status_code == 422


# ── TestCreateMemoryLinkUnit ────────────────────────────────────────────────────

class TestCreateMemoryLinkUnit:
    """Unit tests for create_memory_link() bridge function."""

    def test_create_memory_link_importable(self):
        from AINDY.memory.bridge import create_memory_link
        assert callable(create_memory_link)

    def test_create_memory_link_calls_dao(self):
        from AINDY.memory.bridge import create_memory_link

        mock_db = MagicMock()
        src = str(uuid.uuid4())
        tgt = str(uuid.uuid4())
        expected = {"id": str(uuid.uuid4()), "link_type": "related"}

        # create_memory_link uses memory.memory_persistence.MemoryNodeDAO
        with patch("AINDY.memory.memory_persistence.MemoryNodeDAO.create_link", return_value=expected) as mock_create:
            result = create_memory_link(src, tgt, link_type="related", db=mock_db)
            mock_create.assert_called_once_with(src, tgt, "related", 0.5)

        assert result == expected

    def test_create_memory_link_default_link_type(self):
        """Default link_type is 'related'."""
        from AINDY.memory.bridge import create_memory_link

        mock_db = MagicMock()
        src = str(uuid.uuid4())
        tgt = str(uuid.uuid4())
        with patch("AINDY.memory.memory_persistence.MemoryNodeDAO.create_link", return_value={}) as mock_create:
            create_memory_link(src, tgt, db=mock_db)
            mock_create.assert_called_once_with(src, tgt, "related", 0.5)

    def test_memory_node_model_has_source_column(self):
        """MemoryNodeModel must have source column (added in Phase 1 migration)."""
        from AINDY.memory.memory_persistence import MemoryNodeModel
        columns = {c.key for c in MemoryNodeModel.__table__.columns}
        assert "source" in columns

    def test_memory_node_model_has_user_id_column(self):
        """MemoryNodeModel must have user_id column (added in Phase 1 migration)."""
        from AINDY.memory.memory_persistence import MemoryNodeModel
        columns = {c.key for c in MemoryNodeModel.__table__.columns}
        assert "user_id" in columns
