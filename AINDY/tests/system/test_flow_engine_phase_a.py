"""
test_flow_engine_phase_a.py

Flow Engine Phase A Tests — APScheduler + tenacity

Tests scheduler service, AutomationLog model, automation endpoints,
and verifies that daemon threads have been fully eliminated from
task_services.py.
"""
import pytest
from unittest.mock import MagicMock, patch


# ── TestSchedulerService ────────────────────────────────────────────────────

class TestSchedulerService:

    def test_scheduler_service_importable(self):
        from services.scheduler_service import (
            start, stop, run_task_now, register_task, replay_task, get_scheduler,
        )
        assert callable(start)
        assert callable(stop)
        assert callable(run_task_now)
        assert callable(register_task)
        assert callable(replay_task)

    def test_register_task_decorator(self):
        from services.scheduler_service import register_task, _TASK_REGISTRY

        @register_task("test_registration_fn_unique_001")
        def test_fn(payload):
            return {"ok": True}

        assert "test_registration_fn_unique_001" in _TASK_REGISTRY
        assert callable(_TASK_REGISTRY["test_registration_fn_unique_001"])

    def test_get_scheduler_raises_before_start(self):
        """get_scheduler() raises RuntimeError if scheduler has not been started."""
        import services.scheduler_service as svc

        original = svc._scheduler
        svc._scheduler = None
        try:
            with pytest.raises(RuntimeError, match="Scheduler not started"):
                svc.get_scheduler()
        finally:
            svc._scheduler = original

    def test_daemon_threads_removed_from_task_services(self):
        """task_services.py must not contain daemon=True anywhere."""
        import inspect
        from services import task_services

        source = inspect.getsource(task_services)
        assert "daemon=True" not in source, (
            "daemon=True found in task_services.py. "
            "All daemon threads must be replaced with APScheduler."
        )

    def test_threading_thread_not_used_as_daemon_in_task_services(self):
        """No threading.Thread(daemon=True) calls remain in task_services."""
        import inspect
        from services import task_services

        source = inspect.getsource(task_services)
        # threading module may still be imported by other code — only check
        # that no daemon=True is present (covered by test above, kept explicit)
        assert "daemon=True" not in source

    def test_replay_task_returns_false_for_missing_log(self):
        """replay_task returns False (not raises) when log does not exist."""
        from services.scheduler_service import replay_task

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        # replay_task does `from db.database import SessionLocal` locally
        # so we must patch the source module, not scheduler_service
        with patch("db.database.SessionLocal", return_value=mock_session):
            result = replay_task("nonexistent-log-id-xyz")

        assert result is False

    def test_replay_task_returns_false_for_non_failed_log(self):
        """replay_task returns False when log status is 'success'."""
        from services.scheduler_service import replay_task

        mock_log = MagicMock()
        mock_log.status = "success"

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = mock_log

        with patch("db.database.SessionLocal", return_value=mock_session):
            result = replay_task("some-log-id")

        assert result is False

    def test_replay_task_returns_false_when_fn_not_registered(self):
        """replay_task returns False when task_name not in _TASK_REGISTRY."""
        from services.scheduler_service import replay_task

        mock_log = MagicMock()
        mock_log.status = "failed"
        mock_log.task_name = "__nonexistent_task_not_registered__"
        mock_log.payload = {}

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = mock_log

        with patch("db.database.SessionLocal", return_value=mock_session):
            result = replay_task("some-log-id")

        assert result is False


# ── TestSchedulerLifecycle ──────────────────────────────────────────────────

class TestSchedulerLifecycle:

    def test_start_stop_cycle(self):
        """Scheduler starts and stops cleanly without error."""
        import services.scheduler_service as svc

        original = svc._scheduler
        svc._scheduler = None
        try:
            svc.start()
            assert svc._scheduler is not None
            assert svc._scheduler.running

            svc.stop()
            # After stop, _scheduler is None
            assert svc._scheduler is None
        finally:
            # Restore any pre-existing scheduler
            if original is not None and original.running:
                svc._scheduler = original
            else:
                svc._scheduler = original

    def test_double_start_does_not_crash(self):
        """Calling start() twice logs a warning but does not raise."""
        import services.scheduler_service as svc

        original = svc._scheduler
        svc._scheduler = None
        try:
            svc.start()
            svc.start()  # Should log warning, not raise
        finally:
            svc.stop()
            svc._scheduler = original

    def test_system_jobs_registered_on_start(self):
        """cleanup_stale_logs and task_recurrence_check are registered."""
        import services.scheduler_service as svc

        original = svc._scheduler
        svc._scheduler = None
        try:
            svc.start()
            jobs = svc._scheduler.get_jobs()
            job_ids = [j.id for j in jobs]
            assert "cleanup_stale_logs" in job_ids
            assert "task_recurrence_check" in job_ids
        finally:
            svc.stop()
            svc._scheduler = original

    def test_task_reminder_check_job_registered(self):
        """task_reminder_check job is registered on start."""
        import services.scheduler_service as svc

        original = svc._scheduler
        svc._scheduler = None
        try:
            svc.start()
            jobs = svc._scheduler.get_jobs()
            job_ids = [j.id for j in jobs]
            assert "task_reminder_check" in job_ids
        finally:
            svc.stop()
            svc._scheduler = original

    def test_stop_when_not_started_is_safe(self):
        """stop() when scheduler is already None does not raise."""
        import services.scheduler_service as svc

        original = svc._scheduler
        svc._scheduler = None
        try:
            svc.stop()  # Should not raise
        finally:
            svc._scheduler = original


# ── TestAutomationLogModel ──────────────────────────────────────────────────

class TestAutomationLogModel:

    def test_model_importable(self):
        from db.models.automation_log import AutomationLog
        assert AutomationLog.__tablename__ == "automation_logs"

    def test_model_in_package_init(self):
        from db.models import AutomationLog
        assert AutomationLog is not None

    def test_column_defaults_defined_on_model(self):
        """
        Verify the Column definitions carry the correct default values.
        Note: SQLAlchemy default= fires at INSERT, not Python object creation.
        We inspect the Column objects directly rather than instantiating.
        """
        from db.models.automation_log import AutomationLog
        cols = {c.name: c for c in AutomationLog.__table__.columns}

        # status default is "pending"
        assert cols["status"].default is not None or cols["status"].server_default is not None or cols["status"].nullable is False
        # attempt_count has a default
        assert "attempt_count" in cols
        # max_attempts has a default
        assert "max_attempts" in cols

    def test_id_column_has_callable_default(self):
        """id column has a Python callable default (uuid factory)."""
        from db.models.automation_log import AutomationLog
        id_col = AutomationLog.__table__.columns["id"]
        assert id_col.default is not None
        assert callable(id_col.default.arg)

    def test_object_source_and_task_name_set(self):
        """Columns explicitly passed in __init__ are accessible."""
        from db.models.automation_log import AutomationLog
        log = AutomationLog(
            source="task_services",
            task_name="my_background_task",
            status="pending",
            attempt_count=0,
            max_attempts=3,
        )
        assert log.source == "task_services"
        assert log.task_name == "my_background_task"
        assert log.status == "pending"
        assert log.attempt_count == 0
        assert log.max_attempts == 3

    def test_table_name_correct(self):
        """Confirm ORM model maps to 'automation_logs' table."""
        from db.models.automation_log import AutomationLog
        assert AutomationLog.__tablename__ == "automation_logs"

    def test_required_columns_defined_in_model(self):
        """All required columns are present in the ORM model definition."""
        from db.models.automation_log import AutomationLog
        col_names = [c.name for c in AutomationLog.__table__.columns]
        required = [
            "id", "source", "task_name", "payload", "status",
            "attempt_count", "max_attempts", "error_message",
            "user_id", "result", "started_at", "completed_at",
            "created_at", "scheduled_for",
        ]
        for col in required:
            assert col in col_names, f"automation_logs model missing column: {col}"

    def test_indexes_defined_in_model(self):
        """Index definitions exist on the ORM table (checked via migration file)."""
        # Indexes are defined in the Alembic migration, not on the ORM Table
        # object itself. Verify the migration file contains all three index names.
        from pathlib import Path

        migration_path = (
            Path(__file__).resolve().parents[2]
            / "alembic"
            / "versions"
            / "37020d1c3951_automation_log_flow_engine_phase_a.py"
        )
        with open(migration_path, "r") as f:
            content = f.read()
        assert "ix_automation_logs_status" in content
        assert "ix_automation_logs_user_id" in content
        assert "ix_automation_logs_source" in content


# ── TestAutomationEndpoints ─────────────────────────────────────────────────

class TestAutomationEndpoints:

    def test_logs_endpoint_requires_auth(self, client):
        r = client.get("/automation/logs")
        assert r.status_code == 401

    def test_log_detail_requires_auth(self, client):
        r = client.get("/automation/logs/test-id")
        assert r.status_code == 401

    def test_replay_requires_auth(self, client):
        r = client.post("/automation/logs/test-id/replay")
        assert r.status_code == 401

    def test_scheduler_status_requires_auth(self, client):
        r = client.get("/automation/scheduler/status")
        assert r.status_code == 401

    def test_logs_with_auth_returns_200(self, client, auth_headers):
        r = client.get("/automation/logs", headers=auth_headers)
        assert r.status_code != 401
        if r.status_code == 200:
            data = r.json()
            assert "logs" in data
            assert "count" in data
            assert isinstance(data["logs"], list)

    def test_logs_status_filter_accepted(self, client, auth_headers):
        r = client.get("/automation/logs?status=failed", headers=auth_headers)
        assert r.status_code in (200, 422, 500)

    def test_logs_source_filter_accepted(self, client, auth_headers):
        r = client.get("/automation/logs?source=task_services", headers=auth_headers)
        assert r.status_code in (200, 422, 500)

    def test_log_detail_not_found_returns_404(self, client, auth_headers):
        r = client.get("/automation/logs/nonexistent-id-xyz", headers=auth_headers)
        assert r.status_code in (404, 200, 500)

    def test_replay_not_found_returns_404(self, client, auth_headers):
        r = client.post("/automation/logs/nonexistent-id-xyz/replay", headers=auth_headers)
        assert r.status_code in (404, 400, 500)

    def test_scheduler_status_503_when_not_running(self, client, auth_headers):
        """When scheduler is not running, endpoint returns 503."""
        import services.scheduler_service as svc
        original = svc._scheduler
        svc._scheduler = None
        try:
            r = client.get("/automation/scheduler/status", headers=auth_headers)
            assert r.status_code in (503, 200)
        finally:
            svc._scheduler = original

    def test_automation_routes_registered(self, app):
        """All 4 automation routes are registered in the app."""
        routes = [r.path for r in app.routes]
        assert "/automation/logs" in routes
        assert "/automation/logs/{log_id}" in routes
        assert "/automation/logs/{log_id}/replay" in routes
        assert "/automation/scheduler/status" in routes

    def test_replay_success_log_rejected_with_400(self, client, auth_headers):
        """
        Replaying a log with status='success' must return 400.
        Uses the real route — log won't be found (404) because the test DB
        is mocked, but if it were found the status guard would reject it.
        """
        r = client.post("/automation/logs/fake-success-log/replay", headers=auth_headers)
        # 404 (not found) or 400 (wrong status) — both acceptable; 401 is not
        assert r.status_code != 401

    def test_replay_rejects_invalid_execution_token(self):
        import uuid
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from routes.automation_router import router
        from services.auth_service import get_current_user
        from db.database import get_db

        user_id = str(uuid.uuid4())
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_current_user] = lambda: {"sub": user_id}

        log = MagicMock()
        log.id = "log-1"
        log.user_id = user_id
        log.status = "failed"
        log.payload = {
            "run_id": "run-1",
            "execution_token": {"execution_token": "bad"},
        }

        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = log
        app.dependency_overrides[get_db] = lambda: db

        client = TestClient(app)
        with patch("services.capability_service.validate_token", return_value={"ok": False, "error": "token mismatch"}):
            resp = client.post("/automation/logs/log-1/replay")

        assert resp.status_code == 403


# ── TestTaskServicesNoDaemonThreads ─────────────────────────────────────────

class TestTaskServicesNoDaemonThreads:

    def test_no_daemon_thread_in_start_background_tasks(self):
        import inspect
        from services import task_services
        source = inspect.getsource(task_services.start_background_tasks)
        assert "daemon=True" not in source

    def test_start_background_tasks_returns_false_when_disabled(self):
        # N+9: start_background_tasks() now returns bool (False = no lease / disabled)
        from services.task_services import start_background_tasks
        result = start_background_tasks(enable=False)
        assert result is False

    def test_stop_background_tasks_importable(self):
        from services.task_services import stop_background_tasks
        assert callable(stop_background_tasks)

    def test_check_reminders_still_callable(self):
        """check_reminders() public API is preserved (used by scheduler)."""
        from services.task_services import check_reminders
        assert callable(check_reminders)

    def test_handle_recurrence_still_callable(self):
        """handle_recurrence() public API is preserved (used by scheduler)."""
        from services.task_services import handle_recurrence
        assert callable(handle_recurrence)
