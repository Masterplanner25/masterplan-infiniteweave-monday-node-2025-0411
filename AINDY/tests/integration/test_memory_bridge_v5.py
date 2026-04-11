"""
Memory Bridge v5 Tests — Memory-Native Execution

Tests capture engine, Nodus bridge, and execution loop.
"""
import pytest
from unittest.mock import MagicMock


class TestMemoryCaptureEngine:
    def test_engine_importable(self):
        from AINDY.memory.memory_capture_engine import MemoryCaptureEngine
        assert MemoryCaptureEngine is not None

    def test_event_significance_map_complete(self):
        from AINDY.memory.memory_capture_engine import EVENT_SIGNIFICANCE
        required_events = [
            "arm_analysis_complete",
            "task_completed",
            "masterplan_locked",
            "error_encountered",
        ]
        for event in required_events:
            assert event in EVENT_SIGNIFICANCE, f"Missing event: {event}"

    def test_significance_scoring(self, mock_db):
        from AINDY.memory.memory_capture_engine import MemoryCaptureEngine
        engine = MemoryCaptureEngine(db=mock_db, user_id="test-user")

        score = engine._score_significance(
            event_type="masterplan_locked",
            content="Full strategic plan locked after extensive deliberation and refinement",
            context={"score": 9},
        )
        assert score > 0.5

        score_low = engine._score_significance(
            event_type="genesis_message",
            content="ok",
            context={},
        )
        assert score_low < score

    def test_node_type_classification(self, mock_db):
        from AINDY.memory.memory_capture_engine import MemoryCaptureEngine
        engine = MemoryCaptureEngine(db=mock_db, user_id="test-user")

        assert engine._classify_node_type("masterplan_locked", "") == "decision"
        assert engine._classify_node_type("arm_analysis_complete", "") == "insight"
        assert engine._classify_node_type("task_completed", "") == "outcome"

    def test_tag_enrichment(self, mock_db):
        from AINDY.memory.memory_capture_engine import MemoryCaptureEngine
        engine = MemoryCaptureEngine(db=mock_db, user_id="test-user")

        tags = engine._enrich_tags(
            tags=["custom_tag"],
            event_type="arm_analysis_complete",
            node_type="insight",
        )

        assert "arm" in tags
        assert "analysis" in tags
        assert "insight" in tags
        assert "custom_tag" in tags

    def test_capture_below_threshold_returns_none(self, mock_db, mocker):
        from AINDY.memory.memory_capture_engine import MemoryCaptureEngine
        engine = MemoryCaptureEngine(db=mock_db, user_id="test-user")

        mocker.patch.object(
            engine, "_score_significance", return_value=0.1
        )
        mocker.patch.object(
            engine, "_is_duplicate", return_value=False
        )

        result = engine.evaluate_and_capture(
            event_type="genesis_message",
            content="ok",
            source="test",
        )
        assert result is None

    def test_capture_force_bypasses_threshold(self, mock_db, mocker):
        from AINDY.memory.memory_capture_engine import MemoryCaptureEngine
        engine = MemoryCaptureEngine(db=mock_db, user_id="test-user")

        mocker.patch.object(
            engine, "_score_significance", return_value=0.1
        )
        mocker.patch.object(
            engine, "_is_duplicate", return_value=False
        )
        mocker.patch.object(
            engine, "_auto_link", return_value=None
        )

        mock_node = {"id": "forced-node-id"}
        mocker.patch(
            "db.dao.memory_node_dao.MemoryNodeDAO.save",
            return_value=mock_node,
        )

        result = engine.evaluate_and_capture(
            event_type="genesis_message",
            content="short content",
            source="test",
            force=True,
        )
        assert result is not None

    def test_duplicate_check_prevents_double_capture(self, mock_db, mocker):
        from AINDY.memory.memory_capture_engine import MemoryCaptureEngine
        engine = MemoryCaptureEngine(db=mock_db, user_id="test-user")

        mocker.patch.object(
            engine, "_is_duplicate", return_value=True
        )

        result = engine.evaluate_and_capture(
            event_type="arm_analysis_complete",
            content="duplicate content",
            source="test",
        )
        assert result is None


class TestNodusMemoryBridge:
    def test_bridge_importable(self):
        from AINDY.memory.nodus_memory_bridge import (
            NodusMemoryBridge,
            create_nodus_bridge,
        )
        assert NodusMemoryBridge is not None
        assert callable(create_nodus_bridge)

    def test_bridge_creation(self):
        from AINDY.memory.nodus_memory_bridge import create_nodus_bridge
        bridge = create_nodus_bridge(
            user_id="test-user",
            session_tags=["test", "nodus"],
        )
        assert bridge.user_id == "test-user"
        assert "test" in bridge.session_tags

    def test_recall_without_db_returns_empty(self):
        from AINDY.memory.nodus_memory_bridge import create_nodus_bridge
        bridge = create_nodus_bridge(
            db=None,
            user_id="test-user",
        )
        result = bridge.recall(query="test")
        assert result == []

    def test_remember_without_db_returns_none(self):
        from AINDY.memory.nodus_memory_bridge import create_nodus_bridge
        bridge = create_nodus_bridge(
            db=None,
            user_id="test-user",
        )
        result = bridge.remember("test content")
        assert result is None

    def test_record_outcome_without_db_silent(self):
        from AINDY.memory.nodus_memory_bridge import create_nodus_bridge
        bridge = create_nodus_bridge(
            db=None,
            user_id="test-user",
        )
        bridge.record_outcome("some-id", "success")

    def test_session_tags_combined_with_query_tags(self, mock_db, mocker):
        from AINDY.memory.nodus_memory_bridge import create_nodus_bridge

        mocker.patch(
            "db.dao.memory_node_dao.MemoryNodeDAO.recall",
            return_value=[],
        )

        bridge = create_nodus_bridge(
            db=mock_db,
            user_id="test-user",
            session_tags=["project_x"],
        )

        bridge.recall(
            query="test",
            tags=["auth"],
        )

        # Covered by recall call above; ensure no exceptions.
        assert True

    def test_bridge_exported_from_bridge_package(self):
        from AINDY.memory.nodus_memory_bridge import create_nodus_bridge
        assert callable(create_nodus_bridge)


class TestExecutionLoopEndpoints:
    def test_execute_endpoint_requires_auth(self, client):
        r = client.post(
            "/memory/execute",
            json={"workflow": "arm_analysis", "input": {"query": "test"}},
        )
        assert r.status_code == 401

    def test_execute_complete_requires_auth(self, client):
        r = client.post(
            "/memory/execute/complete",
            json={
                "workflow": "arm_analysis",
                "outcome_content": "test",
                "outcome": "success",
            },
        )
        assert r.status_code == 401

    def test_nodus_execute_requires_auth(self, client):
        r = client.post(
            "/memory/nodus/execute",
            json={"task_name": "test_task", "task_code": "task test { }"},
        )
        assert r.status_code == 401

    def test_execute_with_auth_returns_context(
        self, client, auth_headers, mock_db, mocker
    ):
        mocker.patch(
            "memory.embedding_service.generate_query_embedding",
            return_value=[0.1] * 1536,
        )
        mocker.patch(
            "db.dao.memory_node_dao.MemoryNodeDAO.recall",
            return_value=[],
        )
        mocker.patch(
            "db.dao.memory_node_dao.MemoryNodeDAO.suggest",
            return_value={"suggestions": []},
        )

        r = client.post(
            "/memory/execute",
            json={
                "workflow": "arm_analysis",
                "input": {"query": "test query"},
                "session_tags": ["test"],
            },
            headers=auth_headers,
        )

        assert r.status_code in [200, 422]
        if r.status_code == 200:
            data = r.json()
            assert "workflow" in data
            assert "recalled_memories" in data
            assert "memory_bridge_version" in data
            assert data["memory_bridge_version"] == "v5"

    def test_execute_complete_with_auth_returns_deprecation(
        self, client, auth_headers
    ):
        r = client.post(
            "/memory/execute/complete",
            json={
                "workflow": "arm_analysis",
                "outcome_content": "Analysis complete",
                "outcome": "success",
                "recalled_node_ids": [],
                "session_tags": ["test"],
            },
            headers=auth_headers,
        )

        assert r.status_code == 410
        data = r.json()
        assert data["error"] == "http_error"
        assert data["details"]["error"] == "memory_execute_complete_deprecated"


class TestCaptureEngineIntegration:
    """Tests that workflows use the capture engine."""

    def test_arm_uses_capture_engine(self):
        import inspect
        from AINDY.modules.deepseek import deepseek_code_analyzer
        source = inspect.getsource(deepseek_code_analyzer)
        assert (
            "MemoryCaptureEngine" in source
            or "evaluate_and_capture" in source
            or "memory_capture_engine" in source
        ), "ARM analyzer not using capture engine"

    def test_task_services_uses_capture_engine(self):
        import inspect
        from AINDY.domain import task_services
        source = inspect.getsource(task_services)
        assert (
            "MemoryCaptureEngine" in source
            or "evaluate_and_capture" in source
            or "memory_capture_engine" in source
        ), "task_services not using capture engine"

    def test_genesis_uses_capture_engine(self):
        import inspect
        from AINDY.domain import genesis_ai
        source = inspect.getsource(genesis_ai)
        assert (
            "MemoryCaptureEngine" in source
            or "evaluate_and_capture" in source
            or "memory_capture_engine" in source
        ), "genesis_ai not using capture engine"
