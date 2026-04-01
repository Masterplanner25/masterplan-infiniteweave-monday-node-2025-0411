"""
test_nodus_memory_builtins.py
─────────────────────────────
Unit tests for services/nodus_builtins.py — NodusMemoryBuiltins.

Coverage
--------
NodusMemoryBuiltins construction   instantiation, _writes starts empty
_safe_node                         dict path, ORM-object path, missing fields
recall()                           success path, str tag coercion, limit clamping,
                                   empty result, DAO raises → []
write()                            success path, str tag coercion, significance clamping,
                                   empty content guard, DAO raises → {},
                                   _writes accumulation, multiple writes
search()                           success path, empty query guard, limit clamping,
                                   DAO raises → []
NodusRuntimeAdapter injection      memory global present in initial_globals,
                                   _writes merged into collected_memory_writes
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch, call
import pytest


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_builtins(dao_return_recall=None, dao_raise=None, dao_save_return=None):
    """Return a NodusMemoryBuiltins with a mocked DAO injected via instance override."""
    from services.nodus_builtins import NodusMemoryBuiltins

    db = MagicMock()
    user_id = "user-abc"
    builtins = NodusMemoryBuiltins(db=db, user_id=user_id)

    mock_dao = MagicMock()
    if dao_raise:
        mock_dao.recall.side_effect = dao_raise
        mock_dao.save.side_effect = dao_raise
    else:
        mock_dao.recall.return_value = dao_return_recall or []
        mock_dao.save.return_value = dao_save_return or {
            "id": "node-1",
            "content": "test",
            "tags": [],
            "node_type": "execution",
            "source": "nodus_script",
            "memory_type": None,
            "resonance_score": None,
            "significance": 0.5,
            "created_at": "2026-03-31T00:00:00",
        }

    # Replace instance method so _dao() returns the mock without DB access
    builtins._dao = lambda: mock_dao
    return builtins, mock_dao


def _node_dict(**overrides):
    base = {
        "id": "node-x",
        "content": "sample content",
        "tags": ["a", "b"],
        "node_type": "outcome",
        "significance": 0.7,
        "resonance_score": 0.85,
        "created_at": "2026-03-31T12:00:00",
        "source": "nodus_script",
        "memory_type": "episodic",
    }
    base.update(overrides)
    return base


# ── Construction ───────────────────────────────────────────────────────────────

class TestConstruction:
    def test_stores_user_id(self):
        from services.nodus_builtins import NodusMemoryBuiltins
        b = NodusMemoryBuiltins(db=MagicMock(), user_id="u1")
        assert b._user_id == "u1"

    def test_writes_starts_empty(self):
        from services.nodus_builtins import NodusMemoryBuiltins
        b = NodusMemoryBuiltins(db=MagicMock(), user_id="u1")
        assert b._writes == []

    def test_separate_instances_dont_share_writes(self):
        from services.nodus_builtins import NodusMemoryBuiltins
        b1 = NodusMemoryBuiltins(db=MagicMock(), user_id="u1")
        b2 = NodusMemoryBuiltins(db=MagicMock(), user_id="u2")
        b1._writes.append({"x": 1})
        assert b2._writes == []


# ── _safe_node ─────────────────────────────────────────────────────────────────

class TestSafeNode:
    def _safe(self, node):
        from services.nodus_builtins import NodusMemoryBuiltins
        return NodusMemoryBuiltins._safe_node(node)

    def test_dict_all_fields_extracted(self):
        node = _node_dict()
        result = self._safe(node)
        assert result["id"] == "node-x"
        assert result["content"] == "sample content"
        assert result["tags"] == ["a", "b"]
        assert result["node_type"] == "outcome"
        assert result["significance"] == 0.7
        assert result["resonance_score"] == 0.85
        assert result["created_at"] == "2026-03-31T12:00:00"
        assert result["source"] == "nodus_script"
        assert result["memory_type"] == "episodic"

    def test_dict_missing_fields_return_none(self):
        result = self._safe({"id": "x", "content": "c"})
        assert result["tags"] == []
        assert result["node_type"] is None
        assert result["resonance_score"] is None
        assert result["created_at"] is None

    def test_dict_id_coerced_to_str(self):
        import uuid
        node = _node_dict(id=uuid.UUID("12345678-1234-5678-1234-567812345678"))
        result = self._safe(node)
        assert result["id"] == "12345678-1234-5678-1234-567812345678"

    def test_dict_none_id_becomes_empty_str(self):
        result = self._safe({"id": None, "content": "x"})
        assert result["id"] == ""

    def test_orm_object_path(self):
        orm = MagicMock()
        orm.id = "orm-id"
        orm.content = "orm content"
        orm.tags = ["t1"]
        orm.node_type = "plan"
        orm.significance = 0.3
        orm.resonance_score = 0.6
        orm.created_at = "2026-01-01"
        orm.source = "agent"
        orm.memory_type = "semantic"
        result = self._safe(orm)
        assert result["id"] == "orm-id"
        assert result["content"] == "orm content"
        assert result["tags"] == ["t1"]
        assert result["source"] == "agent"

    def test_orm_object_none_created_at(self):
        orm = MagicMock()
        orm.id = "x"
        orm.created_at = None
        result = self._safe(orm)
        assert result["created_at"] is None

    def test_raw_embedding_not_in_output(self):
        node = _node_dict(embedding=[0.1, 0.2], user_id="private")
        result = self._safe(node)
        assert "embedding" not in result
        assert "user_id" not in result


# ── recall() ──────────────────────────────────────────────────────────────────

class TestRecall:
    def test_returns_list_of_safe_dicts(self):
        nodes = [_node_dict(id="n1"), _node_dict(id="n2")]
        b, dao = _make_builtins(dao_return_recall=nodes)
        result = b.recall(["task"], 2)
        assert len(result) == 2
        assert result[0]["id"] == "n1"
        assert "embedding" not in result[0]

    def test_string_tag_coerced_to_list(self):
        b, dao = _make_builtins(dao_return_recall=[])
        b.recall("goal", 3)
        dao.recall.assert_called_once_with(
            tags=["goal"], limit=3, user_id="user-abc"
        )

    def test_list_of_tags_passed_through(self):
        b, dao = _make_builtins(dao_return_recall=[])
        b.recall(["task", "plan"], 5)
        dao.recall.assert_called_once_with(
            tags=["task", "plan"], limit=5, user_id="user-abc"
        )

    def test_limit_clamped_to_max(self):
        b, dao = _make_builtins(dao_return_recall=[])
        b.recall(["x"], 999)
        dao.recall.assert_called_once_with(tags=["x"], limit=50, user_id="user-abc")

    def test_limit_clamped_to_min(self):
        b, dao = _make_builtins(dao_return_recall=[])
        b.recall(["x"], 0)
        dao.recall.assert_called_once_with(tags=["x"], limit=1, user_id="user-abc")

    def test_dao_raises_returns_empty_list(self):
        b, _ = _make_builtins(dao_raise=RuntimeError("db down"))
        result = b.recall(["tag"])
        assert result == []

    def test_empty_dao_result_returns_empty_list(self):
        b, _ = _make_builtins(dao_return_recall=[])
        assert b.recall(["x"]) == []

    def test_none_dao_result_returns_empty_list(self):
        b, dao = _make_builtins()
        dao.recall.return_value = None
        assert b.recall(["x"]) == []

    def test_does_not_accumulate_writes(self):
        b, _ = _make_builtins(dao_return_recall=[_node_dict()])
        b.recall(["tag"])
        assert b._writes == []


# ── write() ───────────────────────────────────────────────────────────────────

class TestWrite:
    def test_returns_safe_dict_on_success(self):
        saved = _node_dict(id="new-1", content="hello")
        b, _ = _make_builtins(dao_save_return=saved)
        result = b.write("hello", ["tag1"])
        assert result["id"] == "new-1"
        assert result["content"] == "hello"

    def test_string_tag_coerced_to_list(self):
        b, dao = _make_builtins()
        b.write("content", "single-tag")
        _, kwargs = dao.save.call_args
        assert kwargs["tags"] == ["single-tag"]

    def test_none_tags_defaults_to_empty(self):
        b, dao = _make_builtins()
        b.write("content")
        _, kwargs = dao.save.call_args
        assert kwargs["tags"] == []

    def test_significance_clamped_above_1(self):
        b, dao = _make_builtins()
        b.write("content", significance=5.0)
        _, kwargs = dao.save.call_args
        assert kwargs["extra"]["significance"] == 1.0

    def test_significance_clamped_below_0(self):
        b, dao = _make_builtins()
        b.write("content", significance=-1.0)
        _, kwargs = dao.save.call_args
        assert kwargs["extra"]["significance"] == 0.0

    def test_source_always_nodus_script(self):
        b, dao = _make_builtins()
        b.write("content")
        _, kwargs = dao.save.call_args
        assert kwargs["source"] == "nodus_script"

    def test_user_id_scoped(self):
        b, dao = _make_builtins()
        b.write("content")
        _, kwargs = dao.save.call_args
        assert kwargs["user_id"] == "user-abc"

    def test_empty_string_returns_empty_dict(self):
        b, _ = _make_builtins()
        assert b.write("") == {}

    def test_none_content_returns_empty_dict(self):
        b, _ = _make_builtins()
        assert b.write(None) == {}  # type: ignore[arg-type]

    def test_dao_raises_returns_empty_dict(self):
        b, _ = _make_builtins(dao_raise=RuntimeError("db error"))
        assert b.write("hello") == {}

    def test_dao_raises_does_not_append_to_writes(self):
        b, _ = _make_builtins(dao_raise=RuntimeError("db error"))
        b.write("hello")
        assert b._writes == []

    def test_success_appends_to_writes(self):
        saved = _node_dict(id="n1", content="hello")
        b, _ = _make_builtins(dao_save_return=saved)
        b.write("hello", ["t1"])
        assert len(b._writes) == 1
        write = b._writes[0]
        assert write["content"] == "hello"
        assert write["tags"] == ["t1"]
        assert write["user_id"] == "user-abc"
        assert write["result"]["id"] == "n1"

    def test_multiple_writes_all_recorded(self):
        b, dao = _make_builtins()
        dao.save.side_effect = [
            _node_dict(id="n1", content="first"),
            _node_dict(id="n2", content="second"),
        ]
        b.write("first", ["a"])
        b.write("second", ["b"])
        assert len(b._writes) == 2
        assert b._writes[0]["result"]["id"] == "n1"
        assert b._writes[1]["result"]["id"] == "n2"

    def test_node_type_passed_to_dao(self):
        b, dao = _make_builtins()
        b.write("content", node_type="plan")
        _, kwargs = dao.save.call_args
        assert kwargs["node_type"] == "plan"

    def test_default_node_type_is_execution(self):
        b, dao = _make_builtins()
        b.write("content")
        _, kwargs = dao.save.call_args
        assert kwargs["node_type"] == "execution"


# ── search() ──────────────────────────────────────────────────────────────────

class TestSearch:
    def test_returns_list_of_safe_dicts(self):
        nodes = [_node_dict(id="s1"), _node_dict(id="s2")]
        b, dao = _make_builtins()
        dao.recall.return_value = nodes
        result = b.search("goal strategy", 2)
        assert len(result) == 2
        assert result[0]["id"] == "s1"

    def test_passes_query_to_dao_recall(self):
        b, dao = _make_builtins(dao_return_recall=[])
        b.search("prioritize tasks")
        dao.recall.assert_called_once_with(
            query="prioritize tasks", limit=5, user_id="user-abc"
        )

    def test_limit_clamped_to_max(self):
        b, dao = _make_builtins(dao_return_recall=[])
        b.search("x", 200)
        dao.recall.assert_called_once_with(query="x", limit=50, user_id="user-abc")

    def test_empty_query_returns_empty_without_dao_call(self):
        b, dao = _make_builtins()
        result = b.search("")
        assert result == []
        dao.recall.assert_not_called()

    def test_none_query_returns_empty_without_dao_call(self):
        b, dao = _make_builtins()
        result = b.search(None)  # type: ignore[arg-type]
        assert result == []
        dao.recall.assert_not_called()

    def test_dao_raises_returns_empty_list(self):
        b, _ = _make_builtins(dao_raise=RuntimeError("embedding service down"))
        assert b.search("query") == []

    def test_none_dao_result_returns_empty_list(self):
        b, dao = _make_builtins()
        dao.recall.return_value = None
        assert b.search("query") == []

    def test_does_not_accumulate_writes(self):
        b, dao = _make_builtins()
        dao.recall.return_value = [_node_dict()]
        b.search("query")
        assert b._writes == []


# ── NodusRuntimeAdapter integration ───────────────────────────────────────────

class TestAdapterIntegration:
    """
    Verify that NodusRuntimeAdapter._execute() injects the memory global and
    merges memory.write() captures into NodusExecutionResult.memory_writes.

    Uses the same no-DB mock pattern as test_nodus_runtime_adapter.py —
    NodusRuntime and NodusMemoryBridge are patched so no real VM or DB is needed.
    """

    def _run(self, memory_builtins_writes: list[dict] | None = None):
        """
        Run NodusRuntimeAdapter._execute() with all external dependencies mocked.
        Returns (result, captured_initial_globals).
        """
        from services.nodus_runtime_adapter import (
            NodusRuntimeAdapter,
            NodusExecutionContext,
        )

        captured: dict = {}

        mock_runtime = MagicMock()

        def fake_run_source(script, *, filename, initial_globals, host_globals):
            captured.update(initial_globals)
            # Simulate memory.write() side-effect if requested
            if memory_builtins_writes:
                initial_globals["memory"]._writes.extend(memory_builtins_writes)
            return {"ok": True, "error": None}

        mock_runtime.run_source.side_effect = fake_run_source

        mock_bridge = MagicMock()
        mock_builtins = MagicMock()
        mock_builtins._writes = list(memory_builtins_writes or [])

        db = MagicMock()
        ctx = NodusExecutionContext(
            user_id="u-test",
            execution_unit_id="eu-test",
            memory_context={"k": "v"},
            input_payload={"goal": "test"},
        )

        # All three are lazy imports inside _execute() — patch at source module
        with patch("nodus.runtime.embedding.NodusRuntime", return_value=mock_runtime), \
             patch("bridge.nodus_memory_bridge.create_nodus_bridge", return_value=mock_bridge), \
             patch("services.nodus_builtins.NodusMemoryBuiltins", return_value=mock_builtins):
            adapter = NodusRuntimeAdapter(db=db)
            result = adapter._execute("let x = 1", "<test>", ctx)

        return result, captured, mock_builtins

    def test_memory_global_injected(self):
        result, captured, mock_builtins = self._run()
        assert "memory" in captured
        assert captured["memory"] is mock_builtins

    def test_memory_context_still_injected(self):
        result, captured, _ = self._run()
        assert captured["memory_context"] == {"k": "v"}

    def test_input_payload_still_injected(self):
        result, captured, _ = self._run()
        assert captured["input_payload"] == {"goal": "test"}

    def test_user_id_still_injected(self):
        result, captured, _ = self._run()
        assert captured["user_id"] == "u-test"

    def test_memory_writes_merged_into_result(self):
        write_record = {
            "user_id": "u-test",
            "content": "Written from script",
            "tags": ["tag"],
            "node_type": "execution",
            "result": {"id": "n99"},
        }
        result, _, _ = self._run(memory_builtins_writes=[write_record])
        assert any(
            w.get("content") == "Written from script"
            for w in result.memory_writes
        )

    def test_no_memory_writes_gives_empty_list(self):
        result, _, _ = self._run(memory_builtins_writes=[])
        assert result.memory_writes == []

    def test_builtins_constructed_with_correct_user_id(self):
        from services.nodus_runtime_adapter import (
            NodusRuntimeAdapter,
            NodusExecutionContext,
        )
        db = MagicMock()
        ctx = NodusExecutionContext(user_id="specific-user", execution_unit_id="eu-1")

        with patch("nodus.runtime.embedding.NodusRuntime") as MockRuntime, \
             patch("bridge.nodus_memory_bridge.create_nodus_bridge"), \
             patch("services.nodus_builtins.NodusMemoryBuiltins") as MockBuiltins:
            MockRuntime.return_value.run_source.return_value = {"ok": True, "error": None}
            mock_instance = MagicMock()
            mock_instance._writes = []
            MockBuiltins.return_value = mock_instance

            adapter = NodusRuntimeAdapter(db=db)
            adapter._execute("let x = 1", "<t>", ctx)

            MockBuiltins.assert_called_once_with(db=db, user_id="specific-user")
