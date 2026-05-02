from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from AINDY.nodus.runtime.memory_bridge import AINDYMemoryBridge


@pytest.fixture
def bridge():
    return AINDYMemoryBridge(user_id="user-123")


def test_safe_node_with_full_dict():
    node = {
        "id": "n1",
        "content": "hello",
        "tags": ["auth"],
        "node_type": "outcome",
        "significance": 0.8,
        "resonance_score": 0.9,
        "created_at": "2026-05-01T00:00:00Z",
        "source": "nodus_script",
        "memory_type": "insight",
    }

    result = AINDYMemoryBridge._safe_node(node)

    assert result == {
        "id": "n1",
        "content": "hello",
        "tags": ["auth"],
        "node_type": "outcome",
        "significance": 0.8,
        "resonance_score": 0.9,
        "created_at": "2026-05-01T00:00:00Z",
        "source": "nodus_script",
        "memory_type": "insight",
    }


def test_safe_node_with_sparse_dict():
    result = AINDYMemoryBridge._safe_node({"id": "n1", "content": "hello"})

    assert result == {
        "id": "n1",
        "content": "hello",
        "tags": [],
        "node_type": None,
        "significance": None,
        "resonance_score": None,
        "created_at": None,
        "source": None,
        "memory_type": None,
    }


def test_safe_node_with_full_object():
    node = SimpleNamespace(
        id="n2",
        content="world",
        tags=["review"],
        node_type="decision",
        significance=0.4,
        resonance_score=0.7,
        created_at="2026-05-02T00:00:00Z",
        source="api",
        memory_type="outcome",
    )

    result = AINDYMemoryBridge._safe_node(node)

    assert result == {
        "id": "n2",
        "content": "world",
        "tags": ["review"],
        "node_type": "decision",
        "significance": 0.4,
        "resonance_score": 0.7,
        "created_at": "2026-05-02T00:00:00Z",
        "source": "api",
        "memory_type": "outcome",
    }


def test_safe_node_with_object_created_at_none():
    node = SimpleNamespace(id="n3", content="x", tags=None, created_at=None)

    result = AINDYMemoryBridge._safe_node(node)

    assert result["created_at"] is None
    assert result["tags"] == []


def test_recall_returns_safe_nodes_from_dicts(bridge):
    mock_session = MagicMock()
    mock_dao = MagicMock()
    mock_dao.recall.return_value = [{"id": "n1", "content": "hello", "tags": ["auth"]}]

    with (
        patch.object(AINDYMemoryBridge, "_session", return_value=mock_session),
        patch("AINDY.db.dao.memory_node_dao.MemoryNodeDAO", return_value=mock_dao),
    ):
        result = bridge.recall(query="auth", tags=["auth"], limit=3)

    assert result == [
        {
            "id": "n1",
            "content": "hello",
            "tags": ["auth"],
            "node_type": None,
            "significance": None,
            "resonance_score": None,
            "created_at": None,
            "source": None,
            "memory_type": None,
        }
    ]


def test_recall_returns_empty_list_when_dao_empty(bridge):
    mock_session = MagicMock()
    mock_dao = MagicMock()
    mock_dao.recall.return_value = []

    with (
        patch.object(AINDYMemoryBridge, "_session", return_value=mock_session),
        patch("AINDY.db.dao.memory_node_dao.MemoryNodeDAO", return_value=mock_dao),
    ):
        assert bridge.recall(query="x") == []


def test_recall_tags_none_calls_dao_with_empty_tags(bridge):
    mock_session = MagicMock()
    mock_dao = MagicMock()
    mock_dao.recall.return_value = []

    with (
        patch.object(AINDYMemoryBridge, "_session", return_value=mock_session),
        patch("AINDY.db.dao.memory_node_dao.MemoryNodeDAO", return_value=mock_dao),
    ):
        bridge.recall(query="q", tags=None, limit=3)

    mock_dao.recall.assert_called_once_with(query="q", tags=[], limit=3, user_id="user-123")


def test_recall_limit_zero_clamps_to_one(bridge):
    mock_session = MagicMock()
    mock_dao = MagicMock()
    mock_dao.recall.return_value = []

    with (
        patch.object(AINDYMemoryBridge, "_session", return_value=mock_session),
        patch("AINDY.db.dao.memory_node_dao.MemoryNodeDAO", return_value=mock_dao),
    ):
        bridge.recall(query="q", limit=0)

    mock_dao.recall.assert_called_once_with(query="q", tags=[], limit=1, user_id="user-123")


def test_recall_limit_large_clamps_to_fifty(bridge):
    mock_session = MagicMock()
    mock_dao = MagicMock()
    mock_dao.recall.return_value = []

    with (
        patch.object(AINDYMemoryBridge, "_session", return_value=mock_session),
        patch("AINDY.db.dao.memory_node_dao.MemoryNodeDAO", return_value=mock_dao),
    ):
        bridge.recall(query="q", limit=200)

    mock_dao.recall.assert_called_once_with(query="q", tags=[], limit=50, user_id="user-123")


def test_recall_dao_exception_returns_empty_and_logs_warning(bridge, caplog):
    mock_session = MagicMock()
    mock_dao = MagicMock()
    mock_dao.recall.side_effect = RuntimeError("boom")

    with (
        patch.object(AINDYMemoryBridge, "_session", return_value=mock_session),
        patch("AINDY.db.dao.memory_node_dao.MemoryNodeDAO", return_value=mock_dao),
        caplog.at_level("WARNING"),
    ):
        result = bridge.recall(query="q")

    assert result == []
    assert "[AINDYMemoryBridge.recall] failed: boom" in caplog.text


def test_recall_closes_session_on_exception(bridge):
    mock_session = MagicMock()
    mock_dao = MagicMock()
    mock_dao.recall.side_effect = RuntimeError("boom")

    with (
        patch.object(AINDYMemoryBridge, "_session", return_value=mock_session),
        patch("AINDY.db.dao.memory_node_dao.MemoryNodeDAO", return_value=mock_dao),
    ):
        bridge.recall(query="q")

    mock_session.close.assert_called_once()


def test_remember_valid_content_calls_save_and_returns_string_id(bridge):
    mock_session = MagicMock()
    mock_dao = MagicMock()
    mock_dao.save.return_value = {"id": "abc"}

    with (
        patch.object(AINDYMemoryBridge, "_session", return_value=mock_session),
        patch("AINDY.db.dao.memory_node_dao.MemoryNodeDAO", return_value=mock_dao),
    ):
        result = bridge.remember(content="test", node_type="outcome", tags=["x"])

    assert result == "abc"
    mock_dao.save.assert_called_once_with(
        content="test",
        tags=["x"],
        user_id="user-123",
        node_type="outcome",
        source="nodus_script",
        extra={},
    )


def test_remember_content_none_returns_none_without_opening_session(bridge):
    with patch.object(AINDYMemoryBridge, "_session") as mock_session:
        assert bridge.remember(content=None) is None
    mock_session.assert_not_called()


def test_remember_empty_content_returns_none_without_opening_session(bridge):
    with patch.object(AINDYMemoryBridge, "_session") as mock_session:
        assert bridge.remember(content="") is None
    mock_session.assert_not_called()


def test_remember_node_type_none_defaults_to_execution(bridge):
    mock_session = MagicMock()
    mock_dao = MagicMock()
    mock_dao.save.return_value = {"id": "abc"}

    with (
        patch.object(AINDYMemoryBridge, "_session", return_value=mock_session),
        patch("AINDY.db.dao.memory_node_dao.MemoryNodeDAO", return_value=mock_dao),
    ):
        bridge.remember(content="test", node_type=None, tags=None)

    assert mock_dao.save.call_args.kwargs["node_type"] == "execution"


def test_remember_returns_id_from_dict_result(bridge):
    mock_session = MagicMock()
    mock_dao = MagicMock()
    mock_dao.save.return_value = {"id": "abc"}

    with (
        patch.object(AINDYMemoryBridge, "_session", return_value=mock_session),
        patch("AINDY.db.dao.memory_node_dao.MemoryNodeDAO", return_value=mock_dao),
    ):
        assert bridge.remember(content="test") == "abc"


def test_remember_returns_stringified_id_from_object_result(bridge):
    mock_session = MagicMock()
    mock_dao = MagicMock()
    mock_dao.save.return_value = SimpleNamespace(id=123)

    with (
        patch.object(AINDYMemoryBridge, "_session", return_value=mock_session),
        patch("AINDY.db.dao.memory_node_dao.MemoryNodeDAO", return_value=mock_dao),
    ):
        assert bridge.remember(content="test") == "123"


def test_remember_dao_exception_returns_none_and_logs_warning(bridge, caplog):
    mock_session = MagicMock()
    mock_dao = MagicMock()
    mock_dao.save.side_effect = RuntimeError("boom")

    with (
        patch.object(AINDYMemoryBridge, "_session", return_value=mock_session),
        patch("AINDY.db.dao.memory_node_dao.MemoryNodeDAO", return_value=mock_dao),
        caplog.at_level("WARNING"),
    ):
        result = bridge.remember(content="test")

    assert result is None
    assert "[AINDYMemoryBridge.remember] failed: boom" in caplog.text


def test_get_suggestions_query_none_returns_empty_without_session(bridge):
    with patch.object(AINDYMemoryBridge, "_session") as mock_session:
        assert bridge.get_suggestions(query=None) == []
    mock_session.assert_not_called()


def test_get_suggestions_filters_node_types(bridge):
    mock_session = MagicMock()
    mock_dao = MagicMock()
    mock_dao.recall.return_value = [
        {"id": "1", "content": "a", "node_type": "outcome"},
        {"id": "2", "content": "b", "node_type": "insight"},
        {"id": "3", "content": "c", "node_type": "decision"},
        {"id": "4", "content": "d", "node_type": "execution"},
    ]

    with (
        patch.object(AINDYMemoryBridge, "_session", return_value=mock_session),
        patch("AINDY.db.dao.memory_node_dao.MemoryNodeDAO", return_value=mock_dao),
    ):
        result = bridge.get_suggestions(query="auth", limit=5)

    assert [item["id"] for item in result] == ["1", "2", "3"]


def test_get_suggestions_slices_filtered_result_to_limit(bridge):
    mock_session = MagicMock()
    mock_dao = MagicMock()
    mock_dao.recall.return_value = [
        {"id": "1", "content": "a", "node_type": "outcome"},
        {"id": "2", "content": "b", "node_type": "insight"},
        {"id": "3", "content": "c", "node_type": "decision"},
    ]

    with (
        patch.object(AINDYMemoryBridge, "_session", return_value=mock_session),
        patch("AINDY.db.dao.memory_node_dao.MemoryNodeDAO", return_value=mock_dao),
    ):
        result = bridge.get_suggestions(query="auth", limit=2)

    assert len(result) == 2
    assert [item["id"] for item in result] == ["1", "2"]


def test_record_outcome_success_uses_success_score_one(bridge):
    mock_session = MagicMock()
    mock_engine = MagicMock()

    with (
        patch.object(AINDYMemoryBridge, "_session", return_value=mock_session),
        patch("AINDY.runtime.memory.memory_feedback.MemoryFeedbackEngine", return_value=mock_engine),
    ):
        bridge.record_outcome("node-1", "success")

    mock_engine.record_usage.assert_called_once_with(memory_ids=["node-1"], success_score=1.0, db=mock_session)


def test_record_outcome_failure_uses_success_score_zero(bridge):
    mock_session = MagicMock()
    mock_engine = MagicMock()

    with (
        patch.object(AINDYMemoryBridge, "_session", return_value=mock_session),
        patch("AINDY.runtime.memory.memory_feedback.MemoryFeedbackEngine", return_value=mock_engine),
    ):
        bridge.record_outcome("node-1", "failure")

    mock_engine.record_usage.assert_called_once_with(memory_ids=["node-1"], success_score=0.0, db=mock_session)


def test_record_outcome_other_uses_success_score_zero(bridge):
    mock_session = MagicMock()
    mock_engine = MagicMock()

    with (
        patch.object(AINDYMemoryBridge, "_session", return_value=mock_session),
        patch("AINDY.runtime.memory.memory_feedback.MemoryFeedbackEngine", return_value=mock_engine),
    ):
        bridge.record_outcome("node-1", "anything_else")

    mock_engine.record_usage.assert_called_once_with(memory_ids=["node-1"], success_score=0.0, db=mock_session)


def test_record_outcome_engine_exception_logs_warning(bridge, caplog):
    mock_session = MagicMock()
    mock_engine = MagicMock()
    mock_engine.record_usage.side_effect = RuntimeError("boom")

    with (
        patch.object(AINDYMemoryBridge, "_session", return_value=mock_session),
        patch("AINDY.runtime.memory.memory_feedback.MemoryFeedbackEngine", return_value=mock_engine),
        caplog.at_level("WARNING"),
    ):
        bridge.record_outcome("node-1", "success")

    assert "[AINDYMemoryBridge.record_outcome] failed: boom" in caplog.text


def test_share_returns_true_when_share_memory_returns_node(bridge):
    mock_session = MagicMock()
    mock_dao = MagicMock()
    mock_dao.share_memory.return_value = SimpleNamespace(id="n1")

    with (
        patch.object(AINDYMemoryBridge, "_session", return_value=mock_session),
        patch("AINDY.db.dao.memory_node_dao.MemoryNodeDAO", return_value=mock_dao),
    ):
        assert bridge.share("node-1") is True


def test_share_returns_false_when_share_memory_returns_none(bridge):
    mock_session = MagicMock()
    mock_dao = MagicMock()
    mock_dao.share_memory.return_value = None

    with (
        patch.object(AINDYMemoryBridge, "_session", return_value=mock_session),
        patch("AINDY.db.dao.memory_node_dao.MemoryNodeDAO", return_value=mock_dao),
    ):
        assert bridge.share("node-1") is False


def test_share_dao_exception_returns_false_and_logs_warning(bridge, caplog):
    mock_session = MagicMock()
    mock_dao = MagicMock()
    mock_dao.share_memory.side_effect = RuntimeError("boom")

    with (
        patch.object(AINDYMemoryBridge, "_session", return_value=mock_session),
        patch("AINDY.db.dao.memory_node_dao.MemoryNodeDAO", return_value=mock_dao),
        caplog.at_level("WARNING"),
    ):
        assert bridge.share("node-1") is False

    assert "[AINDYMemoryBridge.share] failed: boom" in caplog.text


def test_recall_from_none_namespace_returns_empty_without_session(bridge):
    with patch.object(AINDYMemoryBridge, "_session") as mock_session:
        assert bridge.recall_from(None, query="q") == []
    mock_session.assert_not_called()


def test_recall_from_empty_namespace_returns_empty_without_session(bridge):
    with patch.object(AINDYMemoryBridge, "_session") as mock_session:
        assert bridge.recall_from("", query="q") == []
    mock_session.assert_not_called()


def test_recall_from_valid_namespace_adds_namespace_tag(bridge):
    mock_session = MagicMock()
    mock_dao = MagicMock()
    mock_dao.recall.return_value = []

    with (
        patch.object(AINDYMemoryBridge, "_session", return_value=mock_session),
        patch("AINDY.db.dao.memory_node_dao.MemoryNodeDAO", return_value=mock_dao),
    ):
        bridge.recall_from("arm", query="test", tags=["auth"], limit=3)

    mock_dao.recall.assert_called_once_with(
        query="test",
        tags=["_agent:arm", "auth"],
        limit=3,
        user_id="user-123",
    )


def test_recall_from_tags_none_uses_only_namespace_tag(bridge):
    mock_session = MagicMock()
    mock_dao = MagicMock()
    mock_dao.recall.return_value = []

    with (
        patch.object(AINDYMemoryBridge, "_session", return_value=mock_session),
        patch("AINDY.db.dao.memory_node_dao.MemoryNodeDAO", return_value=mock_dao),
    ):
        bridge.recall_from("arm", query="test", tags=None, limit=3)

    mock_dao.recall.assert_called_once_with(
        query="test",
        tags=["_agent:arm"],
        limit=3,
        user_id="user-123",
    )


def test_recall_all_agents_calls_dao_without_namespace_restriction(bridge):
    mock_session = MagicMock()
    mock_dao = MagicMock()
    mock_dao.recall.return_value = []

    with (
        patch.object(AINDYMemoryBridge, "_session", return_value=mock_session),
        patch("AINDY.db.dao.memory_node_dao.MemoryNodeDAO", return_value=mock_dao),
    ):
        bridge.recall_all_agents(query="test", tags=["auth"], limit=5)

    mock_dao.recall.assert_called_once_with(
        query="test",
        tags=["auth"],
        limit=5,
        user_id="user-123",
    )


def test_recall_all_agents_limit_zero_clamps_to_one(bridge):
    mock_session = MagicMock()
    mock_dao = MagicMock()
    mock_dao.recall.return_value = []

    with (
        patch.object(AINDYMemoryBridge, "_session", return_value=mock_session),
        patch("AINDY.db.dao.memory_node_dao.MemoryNodeDAO", return_value=mock_dao),
    ):
        bridge.recall_all_agents(query="test", limit=0)

    mock_dao.recall.assert_called_once_with(
        query="test",
        tags=[],
        limit=1,
        user_id="user-123",
    )
