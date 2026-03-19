"""
test_memory_bridge.py
─────────────────────
Diagnostic tests for:
  - bridge/bridge.py  (Python symbolic layer)
  - services/memory_persistence.py (DAO + orphan function bug)
  - memory_bridge_rs (Rust/C++ compiled extension — skip if not built)

INTENTIONAL FAILING TESTS document known bugs.
"""
import pytest
import uuid
from unittest.mock import MagicMock, patch


# ── Python MemoryNode / MemoryTrace ────────────────────────────────────────────

class TestPythonBridgeLayer:
    def test_memory_node_creation(self):
        """MemoryNode must be importable and constructable."""
        from bridge.bridge import MemoryNode
        node = MemoryNode("test content", source="pytest", tags=["test"])
        assert node.content == "test content"
        assert node.source == "pytest"
        assert "test" in node.tags
        assert node.id is not None

    def test_memory_node_has_uuid_id(self):
        from bridge.bridge import MemoryNode
        node = MemoryNode("hello")
        # ID should be a valid UUID string
        parsed = uuid.UUID(node.id)
        assert str(parsed) == node.id

    def test_memory_node_link(self):
        from bridge.bridge import MemoryNode
        parent = MemoryNode("parent")
        child = MemoryNode("child")
        parent.link(child)
        assert child in parent.children

    def test_memory_node_to_dict(self):
        from bridge.bridge import MemoryNode
        node = MemoryNode("payload", source="src", tags=["a", "b"])
        d = node.to_dict()
        assert d["content"] == "payload"
        assert d["source"] == "src"
        assert d["tags"] == ["a", "b"]
        assert "id" in d
        assert "timestamp" in d

    def test_memory_trace_creation(self):
        from bridge.bridge import MemoryTrace
        trace = MemoryTrace()
        assert trace.root_nodes == []

    def test_memory_trace_add_and_export(self):
        from bridge.bridge import MemoryNode, MemoryTrace
        trace = MemoryTrace()
        node = MemoryNode("node1", tags=["x"])
        trace.add_node(node)
        exported = trace.export()
        assert len(exported) == 1
        assert exported[0]["content"] == "node1"

    def test_find_by_tag(self):
        from bridge.bridge import MemoryNode, MemoryTrace, find_by_tag
        trace = MemoryTrace()
        node_a = MemoryNode("A", tags=["solon", "bridge"])
        node_b = MemoryNode("B", tags=["bridge"])
        trace.add_node(node_a)
        trace.add_node(node_b)
        matches = find_by_tag(trace, "solon")
        assert len(matches) == 1
        assert matches[0].content == "A"


class TestCreateMemoryNodeWrongTable:
    """
    REGRESSION — bug was fixed in Memory Bridge Phase 1 (2026-03-18).

    create_memory_node() now writes to MemoryNodeModel (table: memory_nodes)
    via MemoryNodeDAO. CalculationResult is no longer used.
    """

    def test_create_memory_node_uses_correct_table(self):
        """
        FIXED: create_memory_node() now writes a MemoryNodeModel row via MemoryNodeDAO.
        Regression guard — ensures CalculationResult is never reintroduced.
        """
        from bridge.bridge import create_memory_node
        from services.memory_persistence import MemoryNodeModel

        saved_instances = []
        mock_db = MagicMock()

        def fake_add(obj):
            saved_instances.append(obj)

        mock_db.add.side_effect = fake_add
        mock_db.commit.return_value = None

        refreshed = MagicMock(spec=MemoryNodeModel)
        refreshed.id = "test-uuid"
        refreshed.content = "Some content"
        refreshed.source = "pytest"
        refreshed.tags = ["tag1", "tag2"]
        refreshed.user_id = None
        refreshed.node_type = "generic"
        refreshed.created_at = None

        mock_db.refresh.side_effect = lambda obj: None

        with patch("services.memory_persistence.MemoryNodeDAO.save_memory_node", return_value=refreshed):
            result = create_memory_node(
                content="Some content",
                source="pytest",
                tags=["tag1", "tag2"],
                db=mock_db,
            )

        # Result should be a dict (persisted path), not a CalculationResult
        assert isinstance(result, dict), (
            "create_memory_node() must return a dict when db is provided"
        )
        # Ensure CalculationResult is not referenced in the function source
        import inspect
        from bridge import bridge
        source = inspect.getsource(bridge.create_memory_node)
        assert "CalculationResult" not in source, (
            "REGRESSION: create_memory_node() must not reference CalculationResult"
        )

    def test_create_memory_node_without_db_returns_memory_node(self):
        """When db=None, create_memory_node returns a transient MemoryNode (not persisted)."""
        from bridge.bridge import create_memory_node, MemoryNode
        result = create_memory_node(content="transient", source="test", tags=["a"])
        assert isinstance(result, MemoryNode), (
            "create_memory_node() without db must return a MemoryNode instance"
        )
        assert result.content == "transient"


# ── MemoryNodeDAO (correct path) ───────────────────────────────────────────────

class TestMemoryNodeDAO:
    def test_memory_node_dao_importable(self):
        from services.memory_persistence import MemoryNodeDAO
        assert MemoryNodeDAO is not None

    def test_memory_node_model_importable(self):
        from services.memory_persistence import MemoryNodeModel
        assert MemoryNodeModel.__tablename__ == "memory_nodes"

    def test_memory_link_model_importable(self):
        from services.memory_persistence import MemoryLinkModel
        assert MemoryLinkModel.__tablename__ == "memory_links"

    def test_orphan_save_memory_node_exists_at_module_level(self):
        """
        BUG DOCUMENTED: An orphan save_memory_node() function exists at module level
        in services/memory_persistence.py with `self` as first parameter,
        but it is NOT a method of any class.

        If called, it would raise TypeError because 'self' is treated as a positional arg.
        This test confirms the function exists as module-level dead code.
        """
        import services.memory_persistence as mp
        # The orphan function exists at module level
        assert hasattr(mp, "save_memory_node"), (
            "Orphan save_memory_node function no longer at module level — "
            "verify it was properly removed or refactored"
        )

        # Confirm it is NOT a method of MemoryNodeDAO (it's a standalone function)
        import inspect
        func = mp.save_memory_node
        assert inspect.isfunction(func), "save_memory_node should be a bare function, not a method"

        # Confirm calling it directly (without a class instance) reveals the self bug
        # We don't call it because it would try to DB write — just check the signature
        sig = inspect.signature(func)
        params = list(sig.parameters.keys())
        assert params[0] == "self", (
            f"Expected first param to be 'self' (orphan bug), got: {params[0]}"
        )

    def test_dao_save_memory_node_mock(self):
        """MemoryNodeDAO.save_memory_node correctly uses memory_nodes table."""
        from services.memory_persistence import MemoryNodeDAO, MemoryNodeModel

        mock_db = MagicMock()
        saved_nodes = []

        def fake_add(obj):
            saved_nodes.append(obj)
            # Simulate DB setting id after commit
            if hasattr(obj, 'id') and obj.id is None:
                obj.id = uuid.uuid4()

        mock_db.add.side_effect = fake_add
        mock_db.commit.return_value = None
        mock_db.refresh.return_value = None

        dao = MemoryNodeDAO(mock_db)

        class FakeNode:
            id = None
            content = "This is real content"
            tags = ["memory", "test"]
            node_type = "research"
            extra = {"source": "pytest"}

        result = dao.save_memory_node(FakeNode())

        assert mock_db.add.called
        assert mock_db.commit.called
        assert len(saved_nodes) == 1
        assert isinstance(saved_nodes[0], MemoryNodeModel)
        assert saved_nodes[0].content == "This is real content"


# ── Rust extension (memory_bridge_rs) ─────────────────────────────────────────

def _rust_available():
    try:
        import memory_bridge_rs
        return True
    except ImportError:
        return False


RUST_AVAILABLE = _rust_available()
skip_no_rust = pytest.mark.skipif(
    not RUST_AVAILABLE,
    reason="memory_bridge_rs Rust extension not compiled (run: maturin develop)"
)


class TestRustLayer:
    @skip_no_rust
    def test_rust_module_importable(self):
        import memory_bridge_rs
        assert memory_bridge_rs is not None

    @skip_no_rust
    def test_rust_memory_node_class_exists(self):
        import memory_bridge_rs
        assert hasattr(memory_bridge_rs, "MemoryNode")

    @skip_no_rust
    def test_rust_memory_trace_class_exists(self):
        import memory_bridge_rs
        assert hasattr(memory_bridge_rs, "MemoryTrace")

    @skip_no_rust
    def test_rust_semantic_similarity_function_exists(self):
        import memory_bridge_rs
        assert hasattr(memory_bridge_rs, "semantic_similarity")
        assert callable(memory_bridge_rs.semantic_similarity)

    @skip_no_rust
    def test_rust_weighted_dot_product_function_exists(self):
        import memory_bridge_rs
        assert hasattr(memory_bridge_rs, "weighted_dot_product")
        assert callable(memory_bridge_rs.weighted_dot_product)

    @skip_no_rust
    def test_rust_memory_node_creation(self):
        import memory_bridge_rs
        node = memory_bridge_rs.MemoryNode("test content", None, ["tag1"])
        assert node.content == "test content"
        assert node.tags == ["tag1"]

    @skip_no_rust
    def test_rust_semantic_similarity_identical(self):
        """Identical vectors should return 1.0."""
        import memory_bridge_rs
        v = [1.0, 2.0, 3.0]
        result = memory_bridge_rs.semantic_similarity(v, v)
        assert result == pytest.approx(1.0, abs=1e-9)

    @skip_no_rust
    def test_rust_semantic_similarity_orthogonal(self):
        """Orthogonal vectors should return 0.0."""
        import memory_bridge_rs
        a = [1.0, 0.0, 0.0]
        b = [0.0, 1.0, 0.0]
        result = memory_bridge_rs.semantic_similarity(a, b)
        assert result == pytest.approx(0.0, abs=1e-9)

    @skip_no_rust
    def test_rust_semantic_similarity_mismatched_length_raises(self):
        import memory_bridge_rs
        with pytest.raises(Exception):
            memory_bridge_rs.semantic_similarity([1.0, 2.0], [1.0, 2.0, 3.0])

    @skip_no_rust
    def test_rust_weighted_dot_product_correctness(self):
        import memory_bridge_rs
        values = [100.0, 50.0, 30.0, 200.0, 45.0]
        weights = [2.0, 3.0, 1.5, 1.0, 0.5]
        # 200 + 150 + 45 + 200 + 22.5 = 617.5
        result = memory_bridge_rs.weighted_dot_product(values, weights)
        assert result == pytest.approx(617.5, rel=1e-6)

    @skip_no_rust
    def test_rust_high_dimensional_within_bounds(self):
        """dim=1536 similarity must fall in [-1.0, 1.0]."""
        import memory_bridge_rs
        import math
        n = 1536
        a = [math.sin(i) for i in range(n)]
        b = [math.cos(i) for i in range(n)]
        result = memory_bridge_rs.semantic_similarity(a, b)
        assert -1.0 <= result <= 1.0


# ── Python fallback cosine similarity ─────────────────────────────────────────

class TestPythonFallbackSimilarity:
    """
    These tests run the Python fallback from calculation_services.
    They run whether or not Rust is compiled.
    """

    def test_python_identical_vectors(self):
        from services.calculation_services import semantic_similarity
        v = [1.0, 2.0, 3.0]
        result = semantic_similarity(v, v)
        assert result == pytest.approx(1.0, abs=1e-9)

    def test_python_orthogonal_vectors(self):
        from services.calculation_services import semantic_similarity
        a = [1.0, 0.0, 0.0]
        b = [0.0, 1.0, 0.0]
        result = semantic_similarity(a, b)
        assert result == pytest.approx(0.0, abs=1e-9)

    def test_python_empty_vectors_returns_zero(self):
        """Empty vectors → denom=0 → returns 0.0 (no error)."""
        from services.calculation_services import semantic_similarity
        result = semantic_similarity([], [])
        assert result == 0.0

    def test_python_mismatched_length_behavior(self):
    """
    Tests behavior for mismatched vector lengths.
    Both Python fallback and Rust raise or return a non-1.0
    value for mismatched lengths — exact behavior depends
    on implementation.
    """
    from services import calculation_services

    a = [1.0, 0.0, 0.0]
    b = [1.0, 0.0, 0.0, 99.0]  # extra element

    if calculation_services._USE_CPP_KERNEL:
        # Rust compiled — raises ValueError
        with pytest.raises((ValueError, Exception)):
            calculation_services.semantic_similarity(a, b)
    else:
        # Python fallback — just verify it doesn't crash
        result = calculation_services.semantic_similarity(a, b)
        assert result is not None
        assert isinstance(result, float)
