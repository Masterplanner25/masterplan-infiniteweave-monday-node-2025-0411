"""
Unit tests for Memory Address Space (MAS) — Sprint MAS

Groups
------
A  normalize_path           (7 tests)
B  validate_tenant_path     (5 tests)
C  parse_path               (6 tests)
D  build_path               (6 tests)
E  generate_node_path       (3 tests)
F  derive_legacy_path       (4 tests)
G  parent_path_of           (4 tests)
H  wildcard classification  (6 tests)
I  path_from_write_payload  (6 tests)
J  build_tree + flatten     (5 tests)
K  MemoryNodeDAO path methods (8 tests)
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from AINDY.memory.memory_address_space import (
    MAS_ROOT,
    LEGACY_NAMESPACE,
    normalize_path,
    validate_tenant_path,
    parse_path,
    build_path,
    generate_node_path,
    derive_legacy_path,
    parent_path_of,
    is_exact,
    is_wildcard,
    is_recursive,
    wildcard_prefix,
    path_from_write_payload,
    build_tree,
    flatten_tree,
    enrich_node_with_path,
)

_UID = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"
_TENANT = "tenant-42"


# ═══════════════════════════════════════════════════════════════════════════════
# A — normalize_path
# ═══════════════════════════════════════════════════════════════════════════════

class TestNormalizePath:
    def test_valid_path_unchanged(self):
        assert normalize_path("/memory/user/tasks/pending") == "/memory/user/tasks/pending"

    def test_trailing_slash_stripped(self):
        assert normalize_path("/memory/user/tasks/") == "/memory/user/tasks"

    def test_double_slash_collapsed(self):
        assert normalize_path("/memory//user//tasks") == "/memory/user/tasks"

    def test_root_preserved(self):
        assert normalize_path("/memory") == "/memory"

    def test_wildcard_preserved(self):
        result = normalize_path("/memory/user/tasks/*")
        assert result.endswith("/*")

    def test_recursive_wildcard_preserved(self):
        result = normalize_path("/memory/user/tasks/**")
        assert result.endswith("/**")

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="must not be empty"):
            normalize_path("")

    def test_wrong_prefix_raises(self):
        with pytest.raises(ValueError, match="must start with"):
            normalize_path("/data/user/tasks")


# ═══════════════════════════════════════════════════════════════════════════════
# B — validate_tenant_path
# ═══════════════════════════════════════════════════════════════════════════════

class TestValidateTenantPath:
    def test_valid_path_passes(self):
        validate_tenant_path(f"/memory/{_TENANT}/tasks/pending/x", _TENANT)

    def test_exact_tenant_root_passes(self):
        validate_tenant_path(f"/memory/{_TENANT}", _TENANT)

    def test_cross_tenant_raises(self):
        with pytest.raises(PermissionError, match="TENANT_VIOLATION"):
            validate_tenant_path(f"/memory/other-tenant/tasks", _TENANT)

    def test_root_only_raises(self):
        with pytest.raises(PermissionError):
            validate_tenant_path("/memory", _TENANT)

    def test_empty_tenant_id_raises(self):
        with pytest.raises(PermissionError):
            validate_tenant_path(f"/memory/other/tasks", "")


# ═══════════════════════════════════════════════════════════════════════════════
# C — parse_path
# ═══════════════════════════════════════════════════════════════════════════════

class TestParsePath:
    def test_full_path_parsed(self):
        node_id = str(uuid.uuid4())
        result = parse_path(f"/memory/{_TENANT}/tasks/pending/{node_id}")
        assert result["tenant_id"] == _TENANT
        assert result["namespace"] == "tasks"
        assert result["addr_type"] == "pending"
        assert result["node_id"] == node_id

    def test_partial_path_none_fields(self):
        result = parse_path(f"/memory/{_TENANT}/tasks")
        assert result["namespace"] == "tasks"
        assert result["addr_type"] is None
        assert result["node_id"] is None

    def test_root_only_all_none(self):
        result = parse_path("/memory")
        assert result["tenant_id"] is None

    def test_wildcard_returned_as_is(self):
        result = parse_path(f"/memory/{_TENANT}/tasks/*")
        assert result["addr_type"] == "*"

    def test_recursive_wildcard_returned(self):
        result = parse_path(f"/memory/{_TENANT}/tasks/**")
        assert result["addr_type"] == "**"

    def test_tenant_id_extracted(self):
        result = parse_path(f"/memory/{_TENANT}")
        assert result["tenant_id"] == _TENANT


# ═══════════════════════════════════════════════════════════════════════════════
# D — build_path
# ═══════════════════════════════════════════════════════════════════════════════

class TestBuildPath:
    def test_tenant_only(self):
        assert build_path(_TENANT) == f"/memory/{_TENANT}"

    def test_with_namespace(self):
        assert build_path(_TENANT, "tasks") == f"/memory/{_TENANT}/tasks"

    def test_with_addr_type(self):
        result = build_path(_TENANT, "tasks", "pending")
        assert result == f"/memory/{_TENANT}/tasks/pending"

    def test_with_node_id(self):
        nid = str(uuid.uuid4())
        result = build_path(_TENANT, "tasks", "pending", nid)
        assert result == f"/memory/{_TENANT}/tasks/pending/{nid}"

    def test_addr_type_without_namespace_raises(self):
        with pytest.raises(ValueError, match="requires namespace"):
            build_path(_TENANT, None, "pending")

    def test_empty_tenant_raises(self):
        with pytest.raises(ValueError, match="tenant_id is required"):
            build_path("")


# ═══════════════════════════════════════════════════════════════════════════════
# E — generate_node_path
# ═══════════════════════════════════════════════════════════════════════════════

class TestGenerateNodePath:
    def test_returns_tuple(self):
        full_path, node_id = generate_node_path(_TENANT, "tasks", "pending")
        assert isinstance(full_path, str)
        assert isinstance(node_id, str)

    def test_path_contains_node_id(self):
        full_path, node_id = generate_node_path(_TENANT, "tasks", "pending")
        assert node_id in full_path

    def test_node_id_is_uuid(self):
        _, node_id = generate_node_path(_TENANT, "tasks", "pending")
        uuid.UUID(node_id)  # must not raise


# ═══════════════════════════════════════════════════════════════════════════════
# F — derive_legacy_path
# ═══════════════════════════════════════════════════════════════════════════════

class TestDeriveLegacyPath:
    def test_uses_user_id(self):
        path = derive_legacy_path({"user_id": "u1", "memory_type": "insight", "id": "abc"})
        assert "/u1/" in path

    def test_uses_legacy_namespace(self):
        path = derive_legacy_path({"user_id": "u1", "memory_type": "insight", "id": "abc"})
        assert f"/{LEGACY_NAMESPACE}/" in path

    def test_uses_memory_type(self):
        path = derive_legacy_path({"user_id": "u1", "memory_type": "decision", "id": "abc"})
        assert "/decision/" in path

    def test_falls_back_to_node_type(self):
        path = derive_legacy_path({"user_id": "u1", "node_type": "outcome", "id": "abc"})
        assert "/outcome/" in path


# ═══════════════════════════════════════════════════════════════════════════════
# G — parent_path_of
# ═══════════════════════════════════════════════════════════════════════════════

class TestParentPathOf:
    def test_leaf_returns_type(self):
        result = parent_path_of(f"/memory/{_TENANT}/tasks/pending/abc")
        assert result == f"/memory/{_TENANT}/tasks/pending"

    def test_type_returns_namespace(self):
        result = parent_path_of(f"/memory/{_TENANT}/tasks/pending")
        assert result == f"/memory/{_TENANT}/tasks"

    def test_namespace_returns_tenant(self):
        result = parent_path_of(f"/memory/{_TENANT}/tasks")
        assert result == f"/memory/{_TENANT}"

    def test_tenant_returns_root(self):
        result = parent_path_of(f"/memory/{_TENANT}")
        assert result == MAS_ROOT


# ═══════════════════════════════════════════════════════════════════════════════
# H — wildcard classification
# ═══════════════════════════════════════════════════════════════════════════════

class TestWildcardClassification:
    def test_is_exact_true(self):
        assert is_exact("/memory/user/tasks/pending/abc")

    def test_is_exact_false_for_wildcard(self):
        assert not is_exact("/memory/user/tasks/*")

    def test_is_wildcard_true(self):
        assert is_wildcard("/memory/user/tasks/*")

    def test_is_wildcard_false_for_recursive(self):
        assert not is_wildcard("/memory/user/tasks/**")

    def test_is_recursive_true(self):
        assert is_recursive("/memory/user/tasks/**")

    def test_wildcard_prefix_extracts_correctly(self):
        assert wildcard_prefix("/memory/user/tasks/*") == "/memory/user/tasks"
        assert wildcard_prefix("/memory/user/tasks/**") == "/memory/user/tasks"


# ═══════════════════════════════════════════════════════════════════════════════
# I — path_from_write_payload
# ═══════════════════════════════════════════════════════════════════════════════

class TestPathFromWritePayload:
    def test_generates_path_from_namespace_and_type(self):
        full_path, ns, at = path_from_write_payload(
            {"namespace": "tasks", "addr_type": "pending", "node_type": "insight"},
            tenant_id=_TENANT,
        )
        assert f"/{_TENANT}/tasks/pending/" in full_path
        assert ns == "tasks"
        assert at == "pending"

    def test_defaults_to_general_when_no_ns(self):
        full_path, ns, at = path_from_write_payload({"node_type": "insight"}, tenant_id=_TENANT)
        assert ns == "general"

    def test_uses_provided_path_with_node_id(self):
        nid = str(uuid.uuid4())
        p = f"/memory/{_TENANT}/tasks/pending/{nid}"
        full_path, ns, at = path_from_write_payload({"path": p}, tenant_id=_TENANT)
        assert full_path == p
        assert ns == "tasks"
        assert at == "pending"

    def test_cross_tenant_path_raises(self):
        p = f"/memory/other-tenant/tasks/pending/abc"
        with pytest.raises(PermissionError):
            path_from_write_payload({"path": p}, tenant_id=_TENANT)

    def test_path_without_node_id_generates_leaf(self):
        p = f"/memory/{_TENANT}/tasks/pending"
        full_path, ns, at = path_from_write_payload({"path": p}, tenant_id=_TENANT)
        # Should append a generated UUID leaf
        assert full_path != p
        assert full_path.startswith(p + "/")

    def test_addr_type_defaults_to_node_type(self):
        _, _, at = path_from_write_payload(
            {"namespace": "goals", "node_type": "decision"},
            tenant_id=_TENANT,
        )
        assert at == "decision"


# ═══════════════════════════════════════════════════════════════════════════════
# J — build_tree + flatten_tree
# ═══════════════════════════════════════════════════════════════════════════════

class TestBuildTree:
    def _make_node(self, path: str) -> dict:
        return {"id": str(uuid.uuid4()), "content": "test", "path": path}

    def test_single_node_tree(self):
        node = self._make_node(f"/memory/{_TENANT}/tasks/pending/abc")
        tree = build_tree([node])
        assert f"/memory/{_TENANT}/tasks/pending/abc" in tree

    def test_parent_child_wired(self):
        parent_path = f"/memory/{_TENANT}/tasks/pending"
        child_path = f"/memory/{_TENANT}/tasks/pending/abc"
        parent = self._make_node(parent_path)
        child = self._make_node(child_path)
        tree = build_tree([parent, child])
        assert child_path in tree[parent_path]["children"]

    def test_empty_list_returns_empty(self):
        assert build_tree([]) == {}

    def test_flatten_returns_list(self):
        node = self._make_node(f"/memory/{_TENANT}/tasks/pending/abc")
        tree = build_tree([node])
        result = flatten_tree(tree)
        assert len(result) == 1

    def test_enrich_node_adds_path(self):
        node = {"id": "x", "user_id": "u1", "memory_type": "insight"}
        enriched = enrich_node_with_path(node)
        assert enriched.get("path") is not None


# ═══════════════════════════════════════════════════════════════════════════════
# K — MemoryNodeDAO path methods (unit — mock DB)
# ═══════════════════════════════════════════════════════════════════════════════

class TestMemoryNodeDAOPathMethods:
    """Smoke tests for DAO path methods using a mocked SQLAlchemy session."""

    def _mock_db(self, row=None):
        db = MagicMock()
        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = row
        mock_q.limit.return_value = mock_q
        mock_q.all.return_value = [row] if row else []
        db.query.return_value = mock_q
        return db

    def _make_model(self, path: str = None, user_id: str = None):
        node = MagicMock()
        node.id = uuid.uuid4()
        node.content = "test content"
        node.tags = []
        node.node_type = "insight"
        node.source = None
        node.source_agent = None
        node.is_shared = False
        node.visibility = "private"
        node.user_id = uuid.UUID(_UID) if user_id is None else uuid.UUID(user_id)
        node.source_event_id = None
        node.root_event_id = None
        node.causal_depth = 0
        node.impact_score = 0.0
        node.memory_type = "insight"
        node.embedding_status = "pending"
        node.extra = {}
        node.created_at = None
        node.updated_at = None
        node.path = path or f"/memory/{_UID}/tasks/pending/{uuid.uuid4()}"
        node.namespace = "tasks"
        node.addr_type = "pending"
        node.parent_path = f"/memory/{_UID}/tasks/pending"
        return node

    def test_get_by_path_returns_dict(self):
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO
        model = self._make_model()
        dao = MemoryNodeDAO(self._mock_db(model))
        result = dao.get_by_path(model.path, user_id=_UID)
        assert result is not None
        assert result["path"] == model.path

    def test_get_by_path_not_found_returns_none(self):
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO
        dao = MemoryNodeDAO(self._mock_db(None))
        result = dao.get_by_path("/memory/u/ns/type/missing", user_id=_UID)
        assert result is None

    def test_list_path_returns_list(self):
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO
        model = self._make_model()
        dao = MemoryNodeDAO(self._mock_db(model))
        result = dao.list_path(f"/memory/{_UID}/tasks/pending", user_id=_UID)
        assert isinstance(result, list)
        assert len(result) == 1

    def test_walk_path_returns_list(self):
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO
        model = self._make_model()
        dao = MemoryNodeDAO(self._mock_db(model))
        result = dao.walk_path(f"/memory/{_UID}/tasks", user_id=_UID)
        assert isinstance(result, list)

    def test_query_path_exact_delegates_to_get_by_path(self):
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO
        model = self._make_model()
        dao = MemoryNodeDAO(self._mock_db(model))
        nodes = dao.query_path(path_expr=model.path, user_id=_UID)
        assert len(nodes) == 1

    def test_query_path_with_tag_filter(self):
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO
        model = self._make_model()
        dao = MemoryNodeDAO(self._mock_db(model))
        # tags filter on empty tags should return nothing
        nodes = dao.query_path(path_expr=model.path, tags=["nonexistent"], user_id=_UID)
        assert nodes == []

    def test_causal_trace_no_origin_returns_empty(self):
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO
        dao = MemoryNodeDAO(self._mock_db(None))
        result = dao.causal_trace("/memory/u/ns/type/missing", user_id=_UID)
        assert result == []

    def test_causal_trace_origin_only_returns_one(self):
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO
        model = self._make_model()
        # No source_event_id → chain stops after origin
        dao = MemoryNodeDAO(self._mock_db(model))
        result = dao.causal_trace(model.path, depth=5, user_id=_UID)
        assert len(result) == 1
        assert result[0]["path"] == model.path
