import pathlib
import uuid
from unittest.mock import MagicMock, patch

import pytest


class TestInfinityLoopModels:

    def test_loop_adjustment_model_exists(self):
        from db.models.infinity_loop import LoopAdjustment

        assert LoopAdjustment.__tablename__ == "loop_adjustments"

    def test_user_feedback_model_exists(self):
        from db.models.infinity_loop import UserFeedback

        assert UserFeedback.__tablename__ == "user_feedback"

    def test_loop_adjustment_columns_present(self):
        from db.models.infinity_loop import LoopAdjustment

        cols = {c.name for c in LoopAdjustment.__table__.columns}
        for required in [
            "id",
            "user_id",
            "trigger_event",
            "score_snapshot",
            "decision_type",
            "adjustment_payload",
            "applied_at",
            "evaluated_at",
            "created_at",
        ]:
            assert required in cols

    def test_user_feedback_columns_present(self):
        from db.models.infinity_loop import UserFeedback

        cols = {c.name for c in UserFeedback.__table__.columns}
        for required in [
            "id",
            "user_id",
            "source_type",
            "source_id",
            "feedback_value",
            "feedback_text",
            "loop_adjustment_id",
            "created_at",
        ]:
            assert required in cols

    def test_models_exported_from_db_package(self):
        from db.models import LoopAdjustment, UserFeedback

        assert LoopAdjustment.__tablename__ == "loop_adjustments"
        assert UserFeedback.__tablename__ == "user_feedback"


class TestInfinityLoopMigration:

    def _src(self):
        path = pathlib.Path("alembic/versions/f1e2d3c4b5a6_infinity_loop_feedback_tables.py")
        assert path.exists()
        return path.read_text(encoding="utf-8")

    def test_migration_file_exists(self):
        path = pathlib.Path("alembic/versions/f1e2d3c4b5a6_infinity_loop_feedback_tables.py")
        assert path.exists()

    def test_migration_chains_from_n10(self):
        src = self._src()
        assert 'down_revision = "e1f2a3b4c5d6"' in src

    def test_migration_has_both_tables(self):
        src = self._src()
        assert "user_feedback" in src
        assert "loop_adjustments" in src

    def test_migration_is_additive(self):
        src = self._src()
        assert "create_table" in src
        assert "drop_table" in src


class TestInfinityLoopHelpers:

    def test_normalize_trigger_event_task_completion(self):
        from services.infinity_loop import _normalize_trigger_event

        assert _normalize_trigger_event("task_completion") == "task_completed"

    def test_normalize_trigger_event_arm_analysis(self):
        from services.infinity_loop import _normalize_trigger_event

        assert _normalize_trigger_event("arm_analysis") == "arm_analyzed"

    def test_normalize_trigger_event_passthrough(self):
        from services.infinity_loop import _normalize_trigger_event

        assert _normalize_trigger_event("scheduled") == "scheduled"

    def test_serialize_adjustment_none(self):
        from services.infinity_loop import serialize_adjustment

        assert serialize_adjustment(None) is None

    def test_serialize_adjustment_shape(self):
        from datetime import datetime, timezone

        from services.infinity_loop import serialize_adjustment

        adjustment = MagicMock()
        adjustment.id = uuid.uuid4()
        adjustment.decision_type = "suggestion_refresh"
        adjustment.applied_at = datetime.now(timezone.utc)
        adjustment.adjustment_payload = {"suggestions": []}

        result = serialize_adjustment(adjustment)
        assert "id" in result
        assert result["decision_type"] == "suggestion_refresh"
        assert result["adjustment_payload"] == {"suggestions": []}

    def test_latest_adjustment_payload_helper_returns_none_without_adjustment(self):
        from routes.score_router import _latest_adjustment_payload

        with patch("services.infinity_loop.get_latest_adjustment", return_value=None):
            assert _latest_adjustment_payload("u1", MagicMock()) is None

    def test_latest_adjustment_payload_helper_strips_id(self):
        from routes.score_router import _latest_adjustment_payload

        with patch("services.infinity_loop.get_latest_adjustment", return_value=MagicMock()), \
             patch("services.infinity_loop.serialize_adjustment", return_value={
                 "id": "adj-1",
                 "decision_type": "continue_highest_priority_task",
                 "applied_at": "2026-01-01T00:00:00+00:00",
                 "adjustment_payload": {"reason": "kpis_stable", "next_action": {"type": "continue_highest_priority_task"}},
             }):
            result = _latest_adjustment_payload("u1", MagicMock())

        assert result == {
            "decision_type": "continue_highest_priority_task",
            "applied_at": "2026-01-01T00:00:00+00:00",
            "adjustment_payload": {"reason": "kpis_stable", "next_action": {"type": "continue_highest_priority_task"}},
        }


class TestInfinityLoopDecisions:

    def test_decide_task_reprioritization_for_low_execution_speed(self):
        from services.infinity_loop import _decide

        decision, payload = _decide({
            "execution_speed": 30.0,
            "decision_efficiency": 55.0,
            "focus_quality": 70.0,
            "ai_productivity_boost": 70.0,
        })
        assert decision == "reprioritize_tasks"
        assert payload["reason"] == "execution_or_decision_below_threshold"

    def test_decide_task_reprioritization_for_low_decision_efficiency(self):
        from services.infinity_loop import _decide

        decision, _ = _decide({
            "execution_speed": 55.0,
            "decision_efficiency": 35.0,
            "focus_quality": 70.0,
            "ai_productivity_boost": 70.0,
        })
        assert decision == "reprioritize_tasks"

    def test_decide_review_plan_for_low_focus(self):
        from services.infinity_loop import _decide

        decision, payload = _decide({
            "execution_speed": 55.0,
            "decision_efficiency": 55.0,
            "focus_quality": 20.0,
            "ai_productivity_boost": 70.0,
        })
        assert decision == "review_plan"
        assert payload["reason"] == "focus_below_threshold"
        assert payload["suggestions"][0]["tool"] == "memory.recall"

    def test_decide_review_plan_for_low_ai_boost(self):
        from services.infinity_loop import _decide

        decision, payload = _decide({
            "execution_speed": 55.0,
            "decision_efficiency": 55.0,
            "focus_quality": 60.0,
            "ai_productivity_boost": 25.0,
        })
        assert decision == "review_plan"
        assert payload["reason"] == "ai_productivity_below_threshold"
        assert payload["suggestions"][0]["tool"] == "arm.analyze"

    def test_decide_continue_highest_priority_task_for_neutral_scores(self):
        from services.infinity_loop import _decide

        decision, payload = _decide({
            "execution_speed": 55.0,
            "decision_efficiency": 55.0,
            "focus_quality": 60.0,
            "ai_productivity_boost": 60.0,
        })
        assert decision == "continue_highest_priority_task"
        assert payload["reason"] == "kpis_stable"

    def test_decide_review_plan_for_missing_snapshot(self):
        from services.infinity_loop import _decide

        decision, payload = _decide(None)
        assert decision == "review_plan"
        assert payload["reason"] == "insufficient_data"


class TestTaskReprioritization:

    def test_reprioritize_tasks_updates_top_tasks_to_high(self):
        from services.infinity_loop import _reprioritize_tasks

        db = MagicMock()
        task1 = MagicMock(id=1, name="A", priority="low")
        task2 = MagicMock(id=2, name="B", priority="medium")
        query = db.query.return_value
        query.filter.return_value = query
        query.order_by.return_value = query
        query.limit.return_value = query
        query.all.return_value = [task1, task2]

        payload = _reprioritize_tasks(
            user_id="00000000-0000-0000-0000-000000000001",
            db=db,
        )

        assert task1.priority == "high"
        assert task2.priority == "high"
        assert payload["task_ids"] == [1, 2]
        db.commit.assert_called_once()

    def test_reprioritize_tasks_handles_invalid_user_id(self):
        from services.infinity_loop import _reprioritize_tasks

        db = MagicMock()
        payload = _reprioritize_tasks(user_id="not-a-uuid", db=db)
        assert payload["reason"] == "invalid_user_id"
        assert payload["task_ids"] == []

    def test_reprioritize_tasks_returns_no_tasks_reason(self):
        from services.infinity_loop import _reprioritize_tasks

        db = MagicMock()
        query = db.query.return_value
        query.filter.return_value = query
        query.order_by.return_value = query
        query.limit.return_value = query
        query.all.return_value = []

        payload = _reprioritize_tasks(
            user_id="00000000-0000-0000-0000-000000000001",
            db=db,
        )
        assert payload["reason"] == "no_incomplete_tasks"


class TestRunLoop:

    def test_run_loop_persists_adjustment_with_next_action(self, monkeypatch):
        from services.infinity_loop import run_loop

        db = MagicMock()
        db.refresh.return_value = None

        monkeypatch.setattr(
            "services.infinity_service.get_user_kpi_snapshot",
            lambda user_id, db: {
                "execution_speed": 55.0,
                "decision_efficiency": 55.0,
                "focus_quality": 60.0,
                "ai_productivity_boost": 60.0,
            },
        )
        monkeypatch.setattr(
            "services.infinity_loop.get_latest_adjustment",
            lambda user_id, db: None,
        )

        adjustment = run_loop("u1", "manual", db)
        assert adjustment is not None
        db.add.assert_called_once()
        db.commit.assert_called_once()

    def test_run_loop_uses_thrash_guard(self, monkeypatch):
        from datetime import datetime, timezone

        from services.infinity_loop import run_loop

        existing = MagicMock()
        existing.decision_type = "review_plan"
        existing.applied_at = datetime.now(timezone.utc)

        db = MagicMock()
        monkeypatch.setattr(
            "services.infinity_service.get_user_kpi_snapshot",
            lambda user_id, db: {
                "execution_speed": 55.0,
                "decision_efficiency": 55.0,
                "focus_quality": 20.0,
                "ai_productivity_boost": 60.0,
            },
        )
        monkeypatch.setattr(
            "services.infinity_loop.get_latest_adjustment",
            lambda user_id, db: existing,
        )

        result = run_loop("u1", "manual", db)
        assert result is existing
        db.add.assert_not_called()

    def test_run_loop_reprioritize_tasks_calls_helper(self, monkeypatch):
        from services.infinity_loop import run_loop

        db = MagicMock()
        monkeypatch.setattr(
            "services.infinity_service.get_user_kpi_snapshot",
            lambda user_id, db: {
                "execution_speed": 30.0,
                "decision_efficiency": 55.0,
                "focus_quality": 70.0,
                "ai_productivity_boost": 70.0,
            },
        )
        monkeypatch.setattr(
            "services.infinity_loop.get_latest_adjustment",
            lambda user_id, db: None,
        )
        called = {}

        def fake_reprio(user_id, db):
            called["user_id"] = user_id
            return {"task_ids": [1, 2, 3]}

        monkeypatch.setattr("services.infinity_loop._reprioritize_tasks", fake_reprio)
        adjustment = run_loop("u1", "task_completed", db)
        assert adjustment is not None
        assert called["user_id"] == "u1"

    def test_run_loop_never_raises(self, monkeypatch):
        from services.infinity_loop import run_loop

        db = MagicMock()
        monkeypatch.setattr(
            "services.infinity_service.get_user_kpi_snapshot",
            lambda user_id, db: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        assert run_loop("u1", "manual", db) is None

    def test_run_loop_normalizes_trigger_event_before_persist(self, monkeypatch):
        from services.infinity_loop import run_loop

        db = MagicMock()
        captured = {}

        def capture_add(obj):
            captured["trigger_event"] = obj.trigger_event

        db.add.side_effect = capture_add
        monkeypatch.setattr(
            "services.infinity_service.get_user_kpi_snapshot",
            lambda user_id, db: None,
        )
        monkeypatch.setattr(
            "services.infinity_loop.get_latest_adjustment",
            lambda user_id, db: None,
        )

        run_loop("u1", "arm_analysis", db)
        assert captured["trigger_event"] == "arm_analyzed"

    def test_run_loop_never_returns_empty_next_action(self, monkeypatch):
        from services.infinity_loop import run_loop

        db = MagicMock()
        db.refresh.return_value = None
        monkeypatch.setattr(
            "services.infinity_loop._decide",
            lambda score_snapshot, feedback_context=None: ("review_plan", {"reason": "x"}),
        )
        monkeypatch.setattr(
            "services.infinity_loop.get_latest_adjustment",
            lambda user_id, db: None,
        )

        assert run_loop("u1", "manual", db) is None


class TestPersistedSuggestions:

    def test_suggest_tools_uses_latest_loop_adjustment_when_present(self):
        from services.agent_tools import suggest_tools

        db = MagicMock()
        latest = MagicMock()
        latest.adjustment_payload = {
            "suggestions": [
                {"tool": "memory.recall", "reason": "x", "suggested_goal": "y"}
            ]
        }

        with patch("services.infinity_loop.get_latest_adjustment", return_value=latest):
            result = suggest_tools({}, user_id="u1", db=db)

        assert result[0]["tool"] == "memory.recall"

    def test_suggest_tools_falls_back_to_transient_rules_without_payload(self):
        from services.agent_tools import suggest_tools

        db = MagicMock()
        latest = MagicMock()
        latest.adjustment_payload = {"task_ids": [1, 2]}

        with patch("services.infinity_loop.get_latest_adjustment", return_value=latest):
            result = suggest_tools(
                {
                    "focus_quality": 20.0,
                    "execution_speed": 70.0,
                    "ai_productivity_boost": 70.0,
                    "master_score": 30.0,
                },
                user_id="u1",
                db=db,
            )

        assert result[0]["tool"] == "memory.recall"


class TestScoreRouterLoopSurface:

    def test_get_score_includes_latest_adjustment_when_score_exists(self, client, auth_headers, mock_db):
        score = MagicMock()
        score.master_score = 70.0
        score.execution_speed_score = 60.0
        score.decision_efficiency_score = 60.0
        score.ai_productivity_boost_score = 60.0
        score.focus_quality_score = 60.0
        score.masterplan_progress_score = 60.0
        score.confidence = "medium"
        score.data_points_used = 12
        score.trigger_event = "manual"
        score.calculated_at = None
        mock_db.query.return_value.filter.return_value.first.return_value = score

        with patch("routes.score_router._latest_adjustment_payload", return_value={
            "decision_type": "suggestion_refresh",
            "applied_at": "2026-01-01T00:00:00+00:00",
            "adjustment_payload": {"suggestions": []},
        }):
            response = client.get("/scores/me", headers=auth_headers)

        assert response.status_code == 200
        assert response.json()["latest_adjustment"]["decision_type"] == "suggestion_refresh"

    def test_recalculate_calls_orchestrator(self, client, auth_headers, mock_db, mocker):
        orchestrator_mock = mocker.patch(
            "services.infinity_orchestrator.execute",
            return_value={
                "score": {
                    "user_id": "u1",
                    "master_score": 55.0,
                    "kpis": {},
                    "weights": {},
                    "metadata": {},
                },
                "adjustment": {
                    "decision_type": "review_plan",
                    "adjustment_payload": {"next_action": {"type": "review_plan"}},
                },
                "next_action": {"type": "review_plan"},
            },
        )
        mocker.patch("routes.score_router._latest_adjustment_payload", return_value=None)

        response = client.post("/scores/me/recalculate", headers=auth_headers)
        assert response.status_code == 200
        orchestrator_mock.assert_called_once()

    def test_feedback_post_requires_auth(self, client):
        response = client.post("/scores/feedback", json={
            "source_type": "arm",
            "source_id": "analysis-1",
            "feedback_value": 1,
        })
        assert response.status_code == 401

    def test_feedback_get_requires_auth(self, client):
        response = client.get("/scores/feedback")
        assert response.status_code == 401

    def test_feedback_post_writes_row(self, client, auth_headers, mock_db):
        feedback = MagicMock()
        feedback.id = uuid.uuid4()
        feedback.user_id = "00000000-0000-0000-0000-000000000001"
        feedback.source_type = "arm"
        feedback.source_id = "analysis-1"
        feedback.feedback_value = 1
        feedback.feedback_text = None
        feedback.loop_adjustment_id = None
        feedback.created_at = None

        def fake_refresh(obj):
            obj.id = feedback.id
            obj.user_id = feedback.user_id
            obj.source_type = feedback.source_type
            obj.source_id = feedback.source_id
            obj.feedback_value = feedback.feedback_value
            obj.feedback_text = feedback.feedback_text
            obj.loop_adjustment_id = feedback.loop_adjustment_id
            obj.created_at = feedback.created_at

        mock_db.refresh.side_effect = fake_refresh

        response = client.post(
            "/scores/feedback",
            headers=auth_headers,
            json={
                "source_type": "arm",
                "source_id": "analysis-1",
                "feedback_value": 1,
            },
        )
        assert response.status_code == 200
        mock_db.add.assert_called()
        mock_db.commit.assert_called_once()

    def test_feedback_get_returns_history(self, client, auth_headers, mock_db):
        item = MagicMock()
        item.id = uuid.uuid4()
        item.source_type = "agent"
        item.source_id = "run-1"
        item.feedback_value = -1
        item.feedback_text = "bad"
        item.loop_adjustment_id = None
        item.created_at = None

        mock_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [item]

        response = client.get("/scores/feedback", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["count"] == 1

    def test_feedback_post_marks_adjustment_evaluated(self, client, auth_headers, mock_db):
        adjustment = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = adjustment

        response = client.post(
            "/scores/feedback",
            headers=auth_headers,
            json={
                "source_type": "manual",
                "feedback_value": 1,
                "loop_adjustment_id": str(uuid.uuid4()),
            },
        )
        assert response.status_code == 200
        assert adjustment.evaluated_at is not None

    def test_feedback_post_rejects_invalid_value(self, client, auth_headers):
        response = client.post(
            "/scores/feedback",
            headers=auth_headers,
            json={
                "source_type": "arm",
                "source_id": "analysis-1",
                "feedback_value": 2,
            },
        )
        assert response.status_code == 422


class TestLoopTriggerWiring:

    def test_scheduler_calls_orchestrator(self):
        src = pathlib.Path("services/scheduler_service.py").read_text(encoding="utf-8")
        assert "infinity_orchestrator" in src

    def test_watcher_calls_orchestrator(self):
        src = pathlib.Path("routes/watcher_router.py").read_text(encoding="utf-8")
        assert "infinity_orchestrator" in src

    def test_task_services_calls_orchestrator(self):
        src = pathlib.Path("services/task_services.py").read_text(encoding="utf-8")
        assert "infinity_orchestrator" in src

    def test_arm_analyzer_calls_orchestrator(self):
        src = pathlib.Path("modules/deepseek/deepseek_code_analyzer.py").read_text(encoding="utf-8")
        assert "infinity_orchestrator" in src

    def test_score_router_manual_recalc_calls_orchestrator(self):
        src = pathlib.Path("routes/score_router.py").read_text(encoding="utf-8")
        assert "infinity_orchestrator" in src

    def test_nodus_adapter_calls_orchestrator(self):
        src = pathlib.Path("services/nodus_adapter.py").read_text(encoding="utf-8")
        assert "infinity_orchestrator" in src

    def test_agent_runtime_calls_orchestrator(self):
        src = pathlib.Path("services/agent_runtime.py").read_text(encoding="utf-8")
        assert "infinity_orchestrator" in src


class TestInfinityOrchestrator:

    def test_execute_returns_score_adjustment_and_next_action(self, monkeypatch):
        from services.infinity_orchestrator import execute

        monkeypatch.setattr(
            "services.infinity_orchestrator.calculate_infinity_score",
            lambda user_id, db, trigger_event: {
                "user_id": user_id,
                "master_score": 60.0,
                "kpis": {
                    "execution_speed": 60.0,
                    "decision_efficiency": 60.0,
                    "ai_productivity_boost": 60.0,
                    "focus_quality": 60.0,
                    "masterplan_progress": 60.0,
                },
                "weights": {},
                "metadata": {"confidence": "medium"},
            },
        )
        fake_adjustment = MagicMock()
        monkeypatch.setattr(
            "services.infinity_orchestrator.run_loop",
            lambda user_id, trigger_event, db, score_snapshot=None: fake_adjustment,
        )
        monkeypatch.setattr(
            "services.infinity_orchestrator.serialize_adjustment",
            lambda adjustment: {
                "id": "adj-1",
                "decision_type": "continue_highest_priority_task",
                "applied_at": "2026-01-01T00:00:00+00:00",
                "adjustment_payload": {"next_action": {"type": "continue_highest_priority_task"}},
            },
        )

        result = execute("u1", "manual", MagicMock())
        assert "score" in result
        assert "adjustment" in result
        assert result["next_action"]["type"] == "continue_highest_priority_task"

    def test_execute_raises_when_adjustment_has_no_next_action(self, monkeypatch):
        from services.infinity_orchestrator import execute

        monkeypatch.setattr(
            "services.infinity_orchestrator.calculate_infinity_score",
            lambda user_id, db, trigger_event: {
                "user_id": user_id,
                "master_score": 60.0,
                "kpis": {
                    "execution_speed": 60.0,
                    "decision_efficiency": 60.0,
                    "ai_productivity_boost": 60.0,
                    "focus_quality": 60.0,
                    "masterplan_progress": 60.0,
                },
                "weights": {},
                "metadata": {"confidence": "medium"},
            },
        )
        monkeypatch.setattr(
            "services.infinity_orchestrator.run_loop",
            lambda user_id, trigger_event, db, score_snapshot=None: MagicMock(),
        )
        monkeypatch.setattr(
            "services.infinity_orchestrator.serialize_adjustment",
            lambda adjustment: {
                "id": "adj-1",
                "decision_type": "review_plan",
                "applied_at": "2026-01-01T00:00:00+00:00",
                "adjustment_payload": {},
            },
        )

        with pytest.raises(RuntimeError):
            execute("u1", "manual", MagicMock())


class TestFrontendLoopSurfaces:

    def test_api_js_exports_feedback_functions(self):
        src = pathlib.Path("client/src/api.js").read_text(encoding="utf-8")
        assert "postScoreFeedback" in src
        assert "getScoreFeedback" in src
        assert "/scores/feedback" in src

    def test_arm_analyze_posts_feedback(self):
        src = pathlib.Path("client/src/components/ARMAnalyze.jsx").read_text(encoding="utf-8")
        assert "postScoreFeedback" in src
        assert 'source_type: "arm"' in src

    def test_agent_console_posts_agent_feedback(self):
        src = pathlib.Path("client/src/components/AgentConsole.jsx").read_text(encoding="utf-8")
        assert "postScoreFeedback" in src
        assert 'source_type: "agent"' in src

    def test_agent_console_still_loads_suggestions(self):
        src = pathlib.Path("client/src/components/AgentConsole.jsx").read_text(encoding="utf-8")
        assert "getAgentSuggestions" in src

    def test_arm_analyze_feedback_buttons_present(self):
        src = pathlib.Path("client/src/components/ARMAnalyze.jsx").read_text(encoding="utf-8")
        assert "Thumb Up" in src
        assert "Thumb Down" in src

    def test_agent_console_feedback_labels_present(self):
        src = pathlib.Path("client/src/components/AgentConsole.jsx").read_text(encoding="utf-8")
        assert "Helpful" in src
        assert "Not Helpful" in src
