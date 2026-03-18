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
    DIAGNOSTIC — INTENTIONAL FAILING TEST.

    create_memory_node() in bridge/bridge.py writes to CalculationResult
    (table: calculation_results) instead of MemoryNodeModel (table: memory_nodes).
    Content and tags are silently discarded.

    This test verifies the bug is present so it shows up in the failure report.
    """

    def test_create_memory_node_uses_wrong_table(self):
        """
        BUG: create_memory_node() stores data in CalculationResult (wrong table).
        It should use MemoryNodeDAO writing to memory_nodes.

        NOTE: bridge.py imports from db.models.models which does NOT EXIST.
        This is an additional import bug layered on top of the wrong-table bug.
        The function will raise ImportError when called.

        This test WILL FAIL when the bug is fixed.
        It documents the bug while it exists.
        """
        from bridge.bridge import create_memory_node
        # The CalculationResult is in db.models.calculation, NOT db.models.models
        # bridge.py tries: from db.models.models import CalculationResult  ← ImportError
        from db.models.calculation import CalculationResult

        saved_instances = []

        mock_db = MagicMock()

        def fake_add(obj):
            saved_instances.append(obj)

        mock_db.add.side_effect = fake_add
        mock_db.commit.return_value = None
        mock_db.refresh.return_value = None

        # bridge.py does: from db.models.models import CalculationResult
        # but db/models/models.py does NOT EXIST — so this raises ImportError
        # Two bugs stacked:
        # 1. Wrong table (CalculationResult instead of MemoryNodeModel)
        # 2. Wrong import path (db.models.models doesn't exist)
        # bridge.py imports SessionLocal inside the function body (lazy import)
        # We need to patch it where it's looked up inside the function
        with patch("db.database.SessionLocal", return_value=mock_db):
            try:
                result = create_memory_node(
                    title="Test Memory",
                    content="Some content that should be saved",
                    tags=["tag1", "tag2"]
                )
                # If we get here, check the wrong-table bug
                if saved_instances:
                    saved = saved_instances[0]
                    assert isinstance(saved, CalculationResult), (
                        "BUG CONFIRMED: create_memory_node() writes a CalculationResult row, "
                        "not a MemoryNodeModel. Content and tags are discarded."
                    )
            except (ImportError, ModuleNotFoundError) as e:
                # This is the secondary bug: wrong import path
                pytest.fail(
                    f"BUG CONFIRMED: create_memory_node() fails with ImportError: {e}. "
                    "bridge.py imports from db.models.models which does not exist. "
                    "Correct path is db.models.calculation. "
                    "Additionally, even if the import were fixed, it writes to the wrong table."
                )


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
        DIAGNOSTIC: Tests the behavioral difference between Python fallback and Rust
        for mismatched vector lengths.

        - Python fallback uses zip() — silently truncates, no error raised
        - Rust layer raises ValueError for mismatched lengths

        When Rust is compiled (as here), semantic_similarity IS the Rust function
        which raises ValueError. This test documents the expected behavior.
        """
        from services import calculation_services

        a = [1.0, 0.0, 0.0]
        b = [1.0, 0.0, 0.0, 99.0]  # extra element

        if calculation_services._USE_CPP_KERNEL:
            # Rust is compiled — should raise ValueError
            with pytest.raises((ValueError, Exception)):
                calculation_services.semantic_similarity(a, b)
        else:
            # Python fallback — silently truncates via zip(), returns 1.0
            result = calculation_services.semantic_similarity(a, b)
            assert result == pytest.approx(1.0, abs=1e-9), (
                "Python fallback mismatched length: expected 1.0 (zip truncation)"
            )
