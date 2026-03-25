"""
Score-Aware Agent Tests — Sprint N+5 Phase 1 + Phase 2

Phase 1: WatcherSignal user_id gap fix
  - WatcherSignal model has user_id column
  - Migration file exists and chains correctly
  - SignalPayload accepts optional user_id
  - calculate_focus_quality() filters by user_id (per-user, not system-wide)
  - focus_quality returns neutral when no user-specific signals exist

Phase 2: KPI context injection into planner
  - get_user_kpi_snapshot() returns correct shape from UserScore
  - get_user_kpi_snapshot() returns None when no score row exists
  - _build_kpi_context_block() returns KPI block when scores present
  - _build_kpi_context_block() returns empty string when no scores
  - _build_kpi_context_block() includes guidance lines for low KPIs
  - generate_plan() embeds KPI block in system prompt
  - generate_plan() succeeds (returns plan) when KPI snapshot is None
"""
import sys
import os
from unittest.mock import MagicMock, patch

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# Phase 1 — WatcherSignal model
# ─────────────────────────────────────────────────────────────────────────────

class TestWatcherSignalUserIdColumn:

    def test_user_id_column_exists(self):
        from db.models.watcher_signal import WatcherSignal
        cols = {c.name for c in WatcherSignal.__table__.columns}
        assert "user_id" in cols, "WatcherSignal must have a user_id column"

    def test_user_id_column_is_nullable(self):
        from db.models.watcher_signal import WatcherSignal
        col = WatcherSignal.__table__.columns["user_id"]
        assert col.nullable is True, "user_id should be nullable (watcher uses API-key auth)"

    def test_user_id_column_is_indexed(self):
        from db.models.watcher_signal import WatcherSignal
        indexed_cols = {
            col.name
            for idx in WatcherSignal.__table__.indexes
            for col in idx.columns
        }
        assert "user_id" in indexed_cols, "user_id should be indexed for query performance"

    def test_signal_type_column_still_exists(self):
        """Regression: other columns not removed."""
        from db.models.watcher_signal import WatcherSignal
        cols = {c.name for c in WatcherSignal.__table__.columns}
        for required in ["id", "signal_type", "session_id", "app_name", "activity_type", "signal_timestamp"]:
            assert required in cols


class TestWatcherSignalMigration:

    def test_migration_file_exists(self):
        import pathlib
        versions_dir = pathlib.Path("alembic/versions")
        migration = versions_dir / "b1c2d3e4f5a6_watcher_signal_user_id.py"
        assert migration.exists(), f"Migration file not found: {migration}"

    def _read_migration(self):
        import pathlib
        path = pathlib.Path("alembic/versions/b1c2d3e4f5a6_watcher_signal_user_id.py")
        return path.read_text(encoding="utf-8")

    def test_migration_revision_id(self):
        src = self._read_migration()
        assert 'revision: str = "b1c2d3e4f5a6"' in src or "revision = 'b1c2d3e4f5a6'" in src or 'revision = "b1c2d3e4f5a6"' in src

    def test_migration_chains_off_agentics(self):
        src = self._read_migration()
        assert "a1b2c3d4e5f6" in src, "Migration must reference agentics revision a1b2c3d4e5f6 as down_revision"
        assert "down_revision" in src

    def test_migration_has_upgrade_and_downgrade(self):
        src = self._read_migration()
        assert "def upgrade" in src
        assert "def downgrade" in src


class TestSignalPayloadUserIdField:

    def test_signal_payload_accepts_user_id(self):
        from routes.watcher_router import SignalPayload
        sig = SignalPayload(
            signal_type="session_started",
            session_id="test-session-123",
            timestamp="2026-03-24T10:00:00Z",
            app_name="cursor.exe",
            activity_type="work",
            user_id="user-abc",
        )
        assert sig.user_id == "user-abc"

    def test_signal_payload_user_id_optional(self):
        from routes.watcher_router import SignalPayload
        sig = SignalPayload(
            signal_type="session_started",
            session_id="test-session-456",
            timestamp="2026-03-24T10:00:00Z",
            app_name="cursor.exe",
            activity_type="work",
        )
        assert sig.user_id is None

    def test_signal_payload_user_id_in_fields(self):
        from routes.watcher_router import SignalPayload
        fields = SignalPayload.model_fields
        assert "user_id" in fields


class TestFocusQualityPerUser:

    def _make_mock_db(self, sessions=None, distractions=0, focus_achieved=0):
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query

        if sessions is None:
            # No sessions for this user
            mock_query.all.return_value = []
            mock_query.count.return_value = 0
        else:
            mock_query.all.return_value = sessions
            # first call to count = distractions, second = focus_achieved
            mock_query.count.side_effect = [distractions, focus_achieved]

        return mock_db

    def test_returns_neutral_when_no_user_sessions(self):
        from services.infinity_service import calculate_focus_quality
        mock_db = self._make_mock_db(sessions=[])
        score, count = calculate_focus_quality("user-xyz", mock_db)
        assert score == 50.0
        assert count == 0

    def test_returns_score_when_user_sessions_exist(self):
        from services.infinity_service import calculate_focus_quality
        mock_session = MagicMock()
        mock_session.duration_seconds = 1800.0  # 30 minutes
        mock_db = self._make_mock_db(sessions=[mock_session], distractions=2, focus_achieved=1)
        score, count = calculate_focus_quality("user-abc", mock_db)
        assert 0.0 <= score <= 100.0
        assert count == 1

    def test_query_filters_by_user_id(self):
        """Verify user_id filter is applied in the focus_quality query chain."""
        from db.models.watcher_signal import WatcherSignal
        import inspect
        from services.infinity_service import calculate_focus_quality
        source = inspect.getsource(calculate_focus_quality)
        assert "user_id" in source, "calculate_focus_quality must filter by user_id"

    def test_distraction_and_focus_queries_use_user_id(self):
        """All three WatcherSignal queries in focus_quality must include user_id filter."""
        import inspect
        from services.infinity_service import calculate_focus_quality
        source = inspect.getsource(calculate_focus_quality)
        # Count occurrences of user_id == user_id filter in the source
        occurrences = source.count("WatcherSignal.user_id == user_id")
        assert occurrences >= 3, (
            f"Expected 3 user_id filters (sessions, distractions, focus_achieved), found {occurrences}"
        )

    def test_no_neutral_return_comment_in_source(self):
        """The old 'return neutral' short-circuit comment should be gone."""
        import inspect
        from services.infinity_service import calculate_focus_quality
        source = inspect.getsource(calculate_focus_quality)
        assert "Until per-user association is added, return neutral" not in source


# ─────────────────────────────────────────────────────────────────────────────
# Phase 2 — KPI context injection
# ─────────────────────────────────────────────────────────────────────────────

class TestGetUserKpiSnapshot:

    def test_returns_none_when_no_score_row(self):
        from services.infinity_service import get_user_kpi_snapshot
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        result = get_user_kpi_snapshot("user-123", mock_db)
        assert result is None

    def test_returns_dict_with_all_kpi_keys(self):
        from services.infinity_service import get_user_kpi_snapshot
        mock_score = MagicMock()
        mock_score.master_score = 72.5
        mock_score.execution_speed_score = 80.0
        mock_score.decision_efficiency_score = 65.0
        mock_score.ai_productivity_boost_score = 55.0
        mock_score.focus_quality_score = 70.0
        mock_score.masterplan_progress_score = 60.0
        mock_score.confidence = "high"

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_score

        result = get_user_kpi_snapshot("user-123", mock_db)
        assert result is not None
        required_keys = [
            "master_score", "execution_speed", "decision_efficiency",
            "ai_productivity_boost", "focus_quality", "masterplan_progress", "confidence",
        ]
        for key in required_keys:
            assert key in result, f"Missing key: {key}"

    def test_returns_correct_values(self):
        from services.infinity_service import get_user_kpi_snapshot
        mock_score = MagicMock()
        mock_score.master_score = 55.0
        mock_score.execution_speed_score = 40.0
        mock_score.decision_efficiency_score = 60.0
        mock_score.ai_productivity_boost_score = 50.0
        mock_score.focus_quality_score = 35.0
        mock_score.masterplan_progress_score = 70.0
        mock_score.confidence = "medium"

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_score

        result = get_user_kpi_snapshot("user-abc", mock_db)
        assert result["master_score"] == 55.0
        assert result["focus_quality"] == 35.0
        assert result["confidence"] == "medium"

    def test_never_raises_on_db_error(self):
        from services.infinity_service import get_user_kpi_snapshot
        mock_db = MagicMock()
        mock_db.query.side_effect = RuntimeError("DB unavailable")
        result = get_user_kpi_snapshot("user-xyz", mock_db)
        assert result is None


class TestBuildKpiContextBlock:

    def _snapshot(self, master=70.0, exec_speed=70.0, decision=70.0,
                  ai_boost=70.0, focus=70.0, progress=70.0, confidence="high"):
        return {
            "master_score": master,
            "execution_speed": exec_speed,
            "decision_efficiency": decision,
            "ai_productivity_boost": ai_boost,
            "focus_quality": focus,
            "masterplan_progress": progress,
            "confidence": confidence,
        }

    def test_returns_empty_when_no_snapshot(self):
        from services.agent_runtime import _build_kpi_context_block
        mock_db = MagicMock()
        with patch("services.infinity_service.get_user_kpi_snapshot", return_value=None):
            result = _build_kpi_context_block("user-123", mock_db)
        assert result == ""

    def test_returns_block_when_snapshot_exists(self):
        from services.agent_runtime import _build_kpi_context_block
        mock_db = MagicMock()
        snap = self._snapshot()
        with patch("services.infinity_service.get_user_kpi_snapshot", return_value=snap):
            result = _build_kpi_context_block("user-123", mock_db)
        assert "Infinity Score" in result
        assert "70.0" in result

    def test_includes_low_focus_guidance(self):
        from services.agent_runtime import _build_kpi_context_block
        mock_db = MagicMock()
        snap = self._snapshot(focus=25.0)
        with patch("services.infinity_service.get_user_kpi_snapshot", return_value=snap):
            result = _build_kpi_context_block("user-123", mock_db)
        assert "memory.recall" in result or "focus" in result.lower()

    def test_includes_low_execution_speed_guidance(self):
        from services.agent_runtime import _build_kpi_context_block
        mock_db = MagicMock()
        snap = self._snapshot(exec_speed=30.0)
        with patch("services.infinity_service.get_user_kpi_snapshot", return_value=snap):
            result = _build_kpi_context_block("user-123", mock_db)
        assert "task.create" in result or "momentum" in result.lower()

    def test_includes_low_arm_usage_guidance(self):
        from services.agent_runtime import _build_kpi_context_block
        mock_db = MagicMock()
        snap = self._snapshot(ai_boost=20.0)
        with patch("services.infinity_service.get_user_kpi_snapshot", return_value=snap):
            result = _build_kpi_context_block("user-123", mock_db)
        assert "arm.analyze" in result

    def test_includes_high_score_guidance(self):
        from services.agent_runtime import _build_kpi_context_block
        mock_db = MagicMock()
        snap = self._snapshot(master=85.0)
        with patch("services.infinity_service.get_user_kpi_snapshot", return_value=snap):
            result = _build_kpi_context_block("user-123", mock_db)
        assert "medium-risk" in result or "strong performance" in result.lower()

    def test_no_guidance_lines_for_healthy_kpis(self):
        """Healthy scores → guidance section present but no low-KPI warnings."""
        from services.agent_runtime import _build_kpi_context_block
        mock_db = MagicMock()
        snap = self._snapshot()  # all 70.0, master 70.0
        with patch("services.infinity_service.get_user_kpi_snapshot", return_value=snap):
            result = _build_kpi_context_block("user-123", mock_db)
        assert "Focus quality is low" not in result
        assert "Execution speed is low" not in result

    def test_never_raises_on_import_error(self):
        from services.agent_runtime import _build_kpi_context_block
        mock_db = MagicMock()
        with patch("services.agent_runtime._build_kpi_context_block", wraps=_build_kpi_context_block):
            with patch("services.infinity_service.get_user_kpi_snapshot", side_effect=RuntimeError("fail")):
                result = _build_kpi_context_block("user-123", mock_db)
        assert result == ""


class TestGeneratePlanKpiInjection:

    def _make_mock_plan_response(self):
        mock_choice = MagicMock()
        mock_choice.message.content = (
            '{"executive_summary": "Test plan", '
            '"steps": [{"tool": "task.create", "args": {"name": "test"}, '
            '"risk_level": "low", "description": "Create a task"}], '
            '"overall_risk": "low"}'
        )
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        return mock_response

    def test_kpi_block_injected_into_system_prompt(self):
        """When snapshot exists, system_prompt passed to OpenAI includes KPI block."""
        from services.agent_runtime import generate_plan

        mock_db = MagicMock()
        mock_response = self._make_mock_plan_response()

        captured_messages = []

        def capture_create(**kwargs):
            captured_messages.extend(kwargs.get("messages", []))
            return mock_response

        with patch("services.agent_runtime._get_client") as mock_client, \
             patch("services.agent_runtime._build_kpi_context_block",
                   return_value="\n## User Performance Context\nmaster: 75.0"):
            mock_client.return_value.chat.completions.create.side_effect = capture_create
            result = generate_plan("write a test task", "user-123", mock_db)

        assert result is not None
        system_msg = next((m for m in captured_messages if m["role"] == "system"), None)
        assert system_msg is not None
        assert "User Performance Context" in system_msg["content"]

    def test_plan_generated_without_kpi_block(self):
        """When snapshot is None, plan still generates successfully."""
        from services.agent_runtime import generate_plan

        mock_db = MagicMock()
        mock_response = self._make_mock_plan_response()

        with patch("services.agent_runtime._get_client") as mock_client, \
             patch("services.agent_runtime._build_kpi_context_block", return_value=""):
            mock_client.return_value.chat.completions.create.return_value = mock_response
            result = generate_plan("create a task", "user-abc", mock_db)

        assert result is not None
        assert result["overall_risk"] == "low"

    def test_plan_structure_unchanged(self):
        """KPI injection does not break plan schema."""
        from services.agent_runtime import generate_plan

        mock_db = MagicMock()
        mock_response = self._make_mock_plan_response()

        with patch("services.agent_runtime._get_client") as mock_client, \
             patch("services.agent_runtime._build_kpi_context_block", return_value="## KPI\nfocus: 30.0"):
            mock_client.return_value.chat.completions.create.return_value = mock_response
            result = generate_plan("run analysis", "user-xyz", mock_db)

        assert "executive_summary" in result
        assert "steps" in result
        assert "overall_risk" in result

    def test_generate_plan_returns_none_on_openai_failure(self):
        """OpenAI failure still returns None gracefully."""
        from services.agent_runtime import generate_plan

        mock_db = MagicMock()
        with patch("services.agent_runtime._get_client") as mock_client, \
             patch("services.agent_runtime._build_kpi_context_block", return_value=""):
            mock_client.return_value.chat.completions.create.side_effect = RuntimeError("API error")
            result = generate_plan("some goal", "user-123", mock_db)

        assert result is None

    def test_kpi_block_builder_called_with_user_id_and_db(self):
        """_build_kpi_context_block receives the correct user_id and db."""
        from services.agent_runtime import generate_plan

        mock_db = MagicMock()
        mock_response = self._make_mock_plan_response()
        captured_args = {}

        def capture_block(user_id, db):
            captured_args["user_id"] = user_id
            captured_args["db"] = db
            return ""

        with patch("services.agent_runtime._get_client") as mock_client, \
             patch("services.agent_runtime._build_kpi_context_block", side_effect=capture_block):
            mock_client.return_value.chat.completions.create.return_value = mock_response
            generate_plan("test goal", "user-target", mock_db)

        assert captured_args.get("user_id") == "user-target"
        assert captured_args.get("db") is mock_db
