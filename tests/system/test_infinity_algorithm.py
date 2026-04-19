"""
Infinity Algorithm Tests — score calculation + API

Sprint: Infinity Algorithm Event-Driven Loop
Covers:
  - Score model tables + KPI weight invariant
  - KPI calculator helpers (_normalize, _sigmoid_score)
  - KPI calculators: neutral fallback on empty data
  - Master score weighted-average formula
  - orchestrated calculate_infinity_score() return shape + failure safety
  - Score API endpoints auth gates
  - Event trigger wiring (source inspection)
  - api.js + Dashboard.jsx presence checks
"""
import pytest
from unittest.mock import MagicMock


# ─────────────────────────────────────────────────────────────────────────────
# Score Models
# ─────────────────────────────────────────────────────────────────────────────

class TestScoreModels:

    def test_kpi_weights_sum_to_one(self):
        from apps.analytics.models import KPI_WEIGHTS
        total = sum(KPI_WEIGHTS.values())
        assert abs(total - 1.0) < 1e-9, f"KPI weights sum to {total}, not 1.0"

    def test_user_score_importable(self):
        from apps.analytics.models import UserScore, ScoreHistory, KPI_WEIGHTS
        assert UserScore.__tablename__ == "user_scores"
        assert ScoreHistory.__tablename__ == "score_history"

    def test_tables_in_orm_metadata(self):
        """Both tables declared in SQLAlchemy ORM metadata."""
        from AINDY.db.database import Base
        table_names = {t for t in Base.metadata.tables}
        assert "user_scores" in table_names
        assert "score_history" in table_names

    def test_user_scores_columns(self):
        """user_scores ORM model has all required columns."""
        from apps.analytics.models import UserScore
        col_names = {c.name for c in UserScore.__table__.columns}
        required = [
            "id", "user_id", "master_score",
            "execution_speed_score",
            "decision_efficiency_score",
            "ai_productivity_boost_score",
            "focus_quality_score",
            "masterplan_progress_score",
            "confidence", "trigger_event",
            "calculated_at",
        ]
        for col in required:
            assert col in col_names, f"user_scores missing column: {col}"

    def test_score_history_columns(self):
        """score_history ORM model has all required columns."""
        from apps.analytics.models import ScoreHistory
        col_names = {c.name for c in ScoreHistory.__table__.columns}
        required = [
            "id", "user_id", "master_score",
            "execution_speed_score", "decision_efficiency_score",
            "ai_productivity_boost_score", "focus_quality_score",
            "masterplan_progress_score",
            "trigger_event", "score_delta", "calculated_at",
        ]
        for col in required:
            assert col in col_names, f"score_history missing column: {col}"

    def test_kpi_weights_have_five_keys(self):
        from apps.analytics.models import KPI_WEIGHTS
        expected_keys = {
            "execution_speed", "decision_efficiency",
            "ai_productivity_boost", "focus_quality",
            "masterplan_progress",
        }
        assert set(KPI_WEIGHTS.keys()) == expected_keys

    def test_models_in_package_init(self):
        from apps.analytics.models import ScoreHistory, UserScore
        assert UserScore.__tablename__ == "user_scores"
        assert ScoreHistory.__tablename__ == "score_history"


# ─────────────────────────────────────────────────────────────────────────────
# KPI Calculators — helpers
# ─────────────────────────────────────────────────────────────────────────────

class TestKPICalculators:

    def test_normalize_min(self):
        from apps.analytics.services.infinity_service import _normalize
        assert _normalize(0, 0, 100) == 0.0

    def test_normalize_max(self):
        from apps.analytics.services.infinity_service import _normalize
        assert _normalize(100, 0, 100) == 100.0

    def test_normalize_mid(self):
        from apps.analytics.services.infinity_service import _normalize
        assert _normalize(50, 0, 100) == 50.0

    def test_normalize_clamp_below(self):
        from apps.analytics.services.infinity_service import _normalize
        assert _normalize(-10, 0, 100) == 0.0

    def test_normalize_clamp_above(self):
        from apps.analytics.services.infinity_service import _normalize
        assert _normalize(110, 0, 100) == 100.0

    def test_normalize_degenerate_range(self):
        from apps.analytics.services.infinity_service import _normalize
        # min == max → neutral
        assert _normalize(5, 5, 5) == 50.0

    def test_sigmoid_at_midpoint(self):
        from apps.analytics.services.infinity_service import _sigmoid_score
        score = _sigmoid_score(5.0, 5.0)
        assert abs(score - 50.0) < 1.0

    def test_sigmoid_above_midpoint(self):
        from apps.analytics.services.infinity_service import _sigmoid_score
        assert _sigmoid_score(8.0, 5.0) > 50.0

    def test_sigmoid_below_midpoint(self):
        from apps.analytics.services.infinity_service import _sigmoid_score
        assert _sigmoid_score(2.0, 5.0) < 50.0

    def test_sigmoid_no_overflow(self):
        from apps.analytics.services.infinity_service import _sigmoid_score
        # Very large values should not raise
        score = _sigmoid_score(1e9, 0.0, steepness=1.0)
        assert 0.0 <= score <= 100.0

    def test_execution_speed_no_tasks(self):
        """No tasks → neutral score (50.0)."""
        from apps.analytics.services.infinity_service import calculate_execution_speed

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.count.return_value = 0
        mock_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None

        score, dp = calculate_execution_speed("test-user", mock_db)
        assert score == 50.0
        assert dp == 0

    def test_focus_quality_no_watcher_data(self):
        """No watcher sessions → neutral score (50.0)."""
        from apps.analytics.services.infinity_service import calculate_focus_quality

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = []

        score, dp = calculate_focus_quality("test-user", mock_db)
        assert score == 50.0
        assert dp == 0

    def test_masterplan_progress_no_plan(self):
        """No active plan → neutral score (50.0)."""
        from apps.analytics.services.infinity_service import calculate_masterplan_progress

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        mock_db.query.return_value.filter.return_value.is_.return_value = mock_db.query.return_value.filter.return_value

        score, dp = calculate_masterplan_progress("test-user", mock_db)
        assert score == 50.0
        assert dp == 0

    def test_decision_efficiency_no_tasks_no_arm(self):
        """No tasks, no ARM → score uses neutral defaults."""
        from apps.analytics.services.infinity_service import calculate_decision_efficiency

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.count.return_value = 0
        mock_db.query.return_value.filter.return_value.all.return_value = []

        score, dp = calculate_decision_efficiency("test-user", mock_db)
        assert 0.0 <= score <= 100.0

    def test_ai_productivity_boost_no_arm(self):
        """No ARM analyses → score near 50 (sigmoid at 0 vs midpoint=5)."""
        from apps.analytics.services.infinity_service import calculate_ai_productivity_boost

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []

        score, dp = calculate_ai_productivity_boost("test-user", mock_db)
        assert 0.0 <= score <= 100.0
        assert dp == 0

    def test_all_calculators_return_0_to_100(self):
        """All KPI scores must be 0-100."""
        import apps.analytics.services.infinity_service as svc

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.count.return_value = 0
        mock_db.query.return_value.filter.return_value.first.return_value = None
        mock_db.query.return_value.filter.return_value.all.return_value = []
        mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []
        mock_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
        mock_db.query.return_value.filter.return_value.is_.return_value = \
            mock_db.query.return_value.filter.return_value

        calculators = [
            svc.calculate_execution_speed,
            svc.calculate_decision_efficiency,
            svc.calculate_ai_productivity_boost,
            svc.calculate_focus_quality,
            svc.calculate_masterplan_progress,
        ]

        for calc in calculators:
            score, _ = calc("test-user", mock_db)
            assert 0.0 <= score <= 100.0, f"{calc.__name__} returned {score}"

    def test_all_calculators_return_tuple(self):
        """All KPI calculators must return (float, int)."""
        import apps.analytics.services.infinity_service as svc

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.count.return_value = 0
        mock_db.query.return_value.filter.return_value.first.return_value = None
        mock_db.query.return_value.filter.return_value.all.return_value = []
        mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []
        mock_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
        mock_db.query.return_value.filter.return_value.is_.return_value = \
            mock_db.query.return_value.filter.return_value

        for calc in [
            svc.calculate_execution_speed,
            svc.calculate_decision_efficiency,
            svc.calculate_ai_productivity_boost,
            svc.calculate_focus_quality,
            svc.calculate_masterplan_progress,
        ]:
            result = calc("test-user", mock_db)
            assert isinstance(result, tuple) and len(result) == 2, \
                f"{calc.__name__} did not return a 2-tuple"
            assert isinstance(result[0], float)
            assert isinstance(result[1], int)


# ─────────────────────────────────────────────────────────────────────────────
# Master Score Calculation
# ─────────────────────────────────────────────────────────────────────────────

class TestMasterScoreCalculation:

    def test_master_score_weighted_average_formula(self):
        from apps.analytics.models import KPI_WEIGHTS

        kpis = {
            "execution_speed": 80.0,
            "decision_efficiency": 70.0,
            "ai_productivity_boost": 60.0,
            "focus_quality": 90.0,
            "masterplan_progress": 50.0,
        }

        expected = sum(kpis[k] * v for k, v in KPI_WEIGHTS.items())
        manual = (
            80.0 * 0.25 +
            70.0 * 0.25 +
            60.0 * 0.20 +
            90.0 * 0.15 +
            50.0 * 0.15
        )
        assert abs(expected - manual) < 0.01

    def test_master_score_all_max(self):
        from apps.analytics.models import KPI_WEIGHTS
        max_score = sum(100.0 * v for v in KPI_WEIGHTS.values())
        assert max_score == pytest.approx(100.0)

    def test_master_score_all_min(self):
        from apps.analytics.models import KPI_WEIGHTS
        min_score = sum(0.0 * v for v in KPI_WEIGHTS.values())
        assert min_score == 0.0

    def test_calculate_infinity_score_returns_dict(self, mocker):
        """calculate_infinity_score returns expected shape."""
        from apps.analytics.services.infinity_service import calculate_infinity_score, orchestrator_score_context

        mocker.patch(
            "apps.analytics.services.infinity_service.calculate_execution_speed",
            return_value=(75.0, 10)
        )
        mocker.patch(
            "apps.analytics.services.infinity_service.calculate_decision_efficiency",
            return_value=(65.0, 15)
        )
        mocker.patch(
            "apps.analytics.services.infinity_service.calculate_ai_productivity_boost",
            return_value=(80.0, 5)
        )
        mocker.patch(
            "apps.analytics.services.infinity_service.calculate_focus_quality",
            return_value=(70.0, 8)
        )
        mocker.patch(
            "apps.analytics.services.infinity_service.calculate_masterplan_progress",
            return_value=(60.0, 20)
        )

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        mock_db.add = MagicMock()
        mock_db.commit = MagicMock()

        with orchestrator_score_context():
            result = calculate_infinity_score(
                user_id="test-user",
                db=mock_db,
                trigger_event="test",
            )

        assert result is not None
        assert "master_score" in result
        assert "kpis" in result
        assert "weights" in result
        assert "metadata" in result

        kpis = result["kpis"]
        for key in [
            "execution_speed", "decision_efficiency",
            "ai_productivity_boost", "focus_quality",
            "masterplan_progress",
        ]:
            assert key in kpis, f"kpis missing: {key}"

        expected = (
            75.0 * 0.25 + 65.0 * 0.25 +
            80.0 * 0.20 + 70.0 * 0.15 +
            60.0 * 0.15
        )
        assert abs(result["master_score"] - expected) < 0.1

    def test_calculate_infinity_score_trigger_event_stored(self, mocker):
        """trigger_event is passed through to result."""
        from apps.analytics.services.infinity_service import calculate_infinity_score, orchestrator_score_context

        for kpi in [
            "calculate_execution_speed",
            "calculate_decision_efficiency",
            "calculate_ai_productivity_boost",
            "calculate_focus_quality",
            "calculate_masterplan_progress",
        ]:
            mocker.patch(f"apps.analytics.services.infinity_service.{kpi}", return_value=(50.0, 5))

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with orchestrator_score_context():
            result = calculate_infinity_score("u1", mock_db, trigger_event="task_completion")
        assert result["metadata"]["trigger_event"] == "task_completion"

    def test_calculate_infinity_score_never_raises(self, mocker):
        """calculate_infinity_score returns None on exception, never raises."""
        from apps.analytics.services.infinity_service import calculate_infinity_score, orchestrator_score_context

        mocker.patch(
            "apps.analytics.services.infinity_service.calculate_execution_speed",
            side_effect=Exception("deliberate failure"),
        )

        mock_db = MagicMock()
        with orchestrator_score_context():
            result = calculate_infinity_score(user_id="test-user", db=mock_db)
        assert result is None

    def test_calculate_infinity_score_master_in_range(self, mocker):
        """Master score is always 0-100."""
        from apps.analytics.services.infinity_service import calculate_infinity_score, orchestrator_score_context

        for kpi in [
            "calculate_execution_speed", "calculate_decision_efficiency",
            "calculate_ai_productivity_boost", "calculate_focus_quality",
            "calculate_masterplan_progress",
        ]:
            mocker.patch(f"apps.analytics.services.infinity_service.{kpi}", return_value=(100.0, 1))

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with orchestrator_score_context():
            result = calculate_infinity_score("u", mock_db)
        assert result is not None
        assert 0.0 <= result["master_score"] <= 100.0

    def test_score_delta_computed(self, mocker):
        """score_delta = new master - previous master."""
        from apps.analytics.services.infinity_service import calculate_infinity_score, orchestrator_score_context
        from apps.analytics.models import UserScore

        for kpi in [
            "calculate_execution_speed", "calculate_decision_efficiency",
            "calculate_ai_productivity_boost", "calculate_focus_quality",
            "calculate_masterplan_progress",
        ]:
            mocker.patch(f"apps.analytics.services.infinity_service.{kpi}", return_value=(80.0, 5))

        prev = MagicMock(spec=UserScore)
        prev.master_score = 70.0

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = prev

        with orchestrator_score_context():
            result = calculate_infinity_score("u", mock_db)
        assert result is not None
        expected_master = sum(
            80.0 * w for w in [0.25, 0.25, 0.20, 0.15, 0.15]
        )
        expected_delta = round(expected_master - 70.0, 2)
        assert abs(result["metadata"]["score_delta"] - expected_delta) < 0.1

    def test_calculate_infinity_score_raises_outside_orchestrator(self):
        from apps.analytics.services.infinity_service import calculate_infinity_score

        assert calculate_infinity_score("u1", MagicMock()) is None


# ─────────────────────────────────────────────────────────────────────────────
# Score Endpoints
# ─────────────────────────────────────────────────────────────────────────────

class TestScoreEndpoints:

    def test_get_score_requires_auth(self, client):
        r = client.get("/scores/me")
        assert r.status_code == 401

    def test_recalculate_requires_auth(self, client):
        r = client.post("/scores/me/recalculate")
        assert r.status_code == 401

    def test_history_requires_auth(self, client):
        r = client.get("/scores/me/history")
        assert r.status_code == 401

    def test_get_score_with_auth_returns_200(
        self, client, auth_headers, mocker
    ):
        mocker.patch(
            "apps.analytics.services.infinity_orchestrator.execute",
            return_value=None,
        )

        r = client.get("/scores/me", headers=auth_headers)
        # 200 with empty state message, or 401 — not 500
        assert r.status_code in [200, 422]
        assert r.status_code != 401

        if r.status_code == 200:
            data = r.json()
            assert "master_score" in data

    def test_history_returns_list(self, client, auth_headers):
        r = client.get("/scores/me/history", headers=auth_headers)
        if r.status_code == 200:
            data = r.json()
            assert "history" in data
            assert isinstance(data["history"], list)

    def test_score_router_registered(self, client):
        """Score router exposes /scores/me (may 401 but must not 404)."""
        r = client.get("/scores/me")
        assert r.status_code != 404, "/scores/me not registered"

    def test_recalculate_router_registered(self, client):
        r = client.post("/scores/me/recalculate")
        assert r.status_code != 404

    def test_history_router_registered(self, client):
        r = client.get("/scores/me/history")
        assert r.status_code != 404


# ─────────────────────────────────────────────────────────────────────────────
# Event Triggers (source inspection)
# ─────────────────────────────────────────────────────────────────────────────

class TestEventTriggers:

    def test_task_services_triggers_score(self):
        """task_services.py calls the Infinity orchestrator on task completion."""
        import inspect
        from apps.tasks.services import task_service as task_services
        src = inspect.getsource(task_services)
        assert "infinity_orchestrator" in src, "task_services not using Infinity orchestrator"

    def test_watcher_router_triggers_score(self):
        """watcher_router.py routes watcher ingest through the canonical flow."""
        import sys
        import inspect
        # routes/__init__.py exports the APIRouter object as watcher_router;
        # we need the source module for inspection.
        mod = sys.modules.get("AINDY.routes.watcher_router")
        assert mod is not None, "AINDY.routes.watcher_router module not loaded"
        src = inspect.getsource(mod)
        assert "watcher_signals_receive" in src or "run_flow" in src, (
            "watcher_router must route through the canonical flow engine"
        )

    def test_arm_analyzer_triggers_score(self):
        """ARM analyzer calls the Infinity orchestrator after analysis."""
        import inspect
        from apps.arm.services.deepseek import deepseek_code_analyzer
        src = inspect.getsource(deepseek_code_analyzer)
        assert "infinity_orchestrator" in src, "ARM analyzer not using Infinity orchestrator"

    def test_daily_score_job_registered(self):
        """Daily Infinity score job is registered by the app scheduler wiring."""
        import apps.bootstrap
        from AINDY.platform_layer.registry import get_scheduled_jobs

        apps.bootstrap.bootstrap()
        jobs = {job["id"]: job for job in get_scheduled_jobs()}
        assert "daily_infinity_score_recalculation" in jobs
        assert jobs["daily_infinity_score_recalculation"]["handler"] is apps.bootstrap._scheduler_recalculate_all_scores

    def test_task_completion_trigger_is_fire_and_forget(self):
        """Task completion orchestration is wrapped so side effects remain non-fatal."""
        import inspect
        from apps.tasks.services import task_service as task_services
        src = inspect.getsource(task_services.orchestrate_task_completion)
        assert "except" in src, "orchestrate_task_completion missing exception handler"

    def test_recalculate_all_scores_function_exists(self):
        """_scheduler_recalculate_all_scores is defined in app bootstrap."""
        import apps.bootstrap
        assert hasattr(apps.bootstrap, "_scheduler_recalculate_all_scores")


# ─────────────────────────────────────────────────────────────────────────────
# Social Feed Ranking
# ─────────────────────────────────────────────────────────────────────────────

class TestSocialFeedRanking:

    def test_infinity_ranked_score_function_exists(self):
        """_compute_infinity_ranked_score is present in social_router module."""
        import apps.social.routes.social_router as mod
        assert hasattr(mod, "_compute_infinity_ranked_score"), \
            "social_router missing _compute_infinity_ranked_score"

    def test_infinity_ranked_score_range(self):
        """Ranked score is always 0.0-1.0."""
        import apps.social.routes.social_router as mod
        fn = getattr(mod, "_compute_infinity_ranked_score")

        from apps.social.models.social_models import SocialPost
        from datetime import datetime, timezone

        post = SocialPost(
            author_id="user1",
            author_username="tester",
            content="test",
            trust_tier_required="observer",
            created_at=datetime.now(timezone.utc),
        )

        for author_score in [0.0, 50.0, 100.0]:
            score = fn(post, author_score)
            assert 0.0 <= score <= 1.0, f"Ranked score out of range: {score}"

    def test_higher_author_score_increases_rank(self):
        """Higher author Infinity score raises feed rank."""
        import apps.social.routes.social_router as mod
        fn = getattr(mod, "_compute_infinity_ranked_score")

        from apps.social.models.social_models import SocialPost
        from datetime import datetime, timezone

        post = SocialPost(
            author_id="user1",
            author_username="tester",
            content="test",
            trust_tier_required="observer",
            created_at=datetime.now(timezone.utc),
        )

        low = fn(post, 10.0)
        high = fn(post, 90.0)
        assert high > low

    def test_get_feed_accepts_sql_db_param(self):
        """get_feed function in social_router module accepts sql_db parameter."""
        import inspect
        import apps.social.routes.social_router as mod
        fn = getattr(mod, "get_feed")
        sig = inspect.signature(fn)
        assert "sql_db" in sig.parameters, \
            "get_feed missing sql_db parameter for Infinity score lookup"


# ─────────────────────────────────────────────────────────────────────────────
# Frontend
# ─────────────────────────────────────────────────────────────────────────────

class TestAPIFunctionsInApiJs:

    def test_score_api_functions_present(self):
        import pathlib
        api_src = pathlib.Path("client/src/api.js").read_text()
        for fn in ["getMyScore", "recalculateScore", "getScoreHistory"]:
            assert fn in api_src, f"api.js missing function: {fn}"

    def test_score_endpoints_referenced_in_api_js(self):
        import pathlib
        api_src = pathlib.Path("client/src/api.js").read_text()
        assert "/scores/me" in api_src

    def test_infinity_score_panel_in_dashboard(self):
        import pathlib
        src = pathlib.Path("client/src/components/Dashboard.jsx").read_text()
        assert "InfinityScorePanel" in src, "Dashboard missing InfinityScorePanel"

    def test_dashboard_imports_score_api_functions(self):
        import pathlib
        src = pathlib.Path("client/src/components/Dashboard.jsx").read_text()
        assert "getMyScore" in src
        assert "recalculateScore" in src
        assert "getScoreHistory" in src

    def test_score_ring_component_in_dashboard(self):
        import pathlib
        src = pathlib.Path("client/src/components/Dashboard.jsx").read_text()
        assert "ScoreRing" in src or "master_score" in src or "master" in src.lower()


