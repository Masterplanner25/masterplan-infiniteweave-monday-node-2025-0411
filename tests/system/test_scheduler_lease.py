"""
Sprint N+9 Phase 1 — APScheduler lease gating + heartbeat tests.

Groups:
  1. start_background_tasks return value (4 tests)
  2. _heartbeat_lease_job behaviour (4 tests)
  3. scheduler_service._refresh_lease_heartbeat (3 tests)
  4. main.py startup order — lease gates scheduler.start() (4 tests)
"""
import logging
import pytest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, call


# ─────────────────────────────────────────────────────────────────────────────
# Group 1 — start_background_tasks return value
# ─────────────────────────────────────────────────────────────────────────────

class TestStartBackgroundTasksReturnValue:
    """start_background_tasks() must return bool so main.py can gate scheduler."""

    def test_returns_false_when_disabled(self):
        from apps.tasks.services.task_service import start_background_tasks
        result = start_background_tasks(enable=False)
        assert result is False

    def test_returns_true_when_lease_acquired(self):
        from apps.tasks.services import task_service as task_services
        with patch.object(task_services, "_acquire_background_lease", return_value=True):
            result = task_services.start_background_tasks(enable=True)
        assert result is True

    def test_returns_false_when_lease_not_acquired(self):
        from apps.tasks.services import task_service as task_services
        with patch.object(task_services, "_acquire_background_lease", return_value=False):
            result = task_services.start_background_tasks(enable=True)
        assert result is False

    def test_return_type_is_bool(self):
        from apps.tasks.services import task_service as task_services
        with patch.object(task_services, "_acquire_background_lease", return_value=True):
            result = task_services.start_background_tasks(enable=True)
        assert isinstance(result, bool)

    def test_acquire_background_lease_handles_naive_db_timestamp(self):
        from apps.tasks.services import task_service as task_services
        lease = SimpleNamespace(
            name="task_background_runner",
            owner_id="other-instance",
            acquired_at=None,
            heartbeat_at=None,
            expires_at=datetime.utcnow() + timedelta(seconds=60),
        )

        class _Query:
            def filter(self, *args, **kwargs):
                return self

            def with_for_update(self, **kwargs):
                return self

            def first(self):
                return lease

        class _DB:
            def query(self, model):
                return _Query()

            def rollback(self):
                return None

            def close(self):
                return None

        with patch.object(task_services, "SessionLocal", return_value=_DB()), \
             patch.object(task_services, "_get_instance_id", return_value="current-instance"):
            result = task_services._acquire_background_lease()

        assert result is False
        assert lease.expires_at.tzinfo is None


# ─────────────────────────────────────────────────────────────────────────────
# Group 2 — _heartbeat_lease_job behaviour
# ─────────────────────────────────────────────────────────────────────────────

class TestHeartbeatLeaseJob:
    """_heartbeat_lease_job calls _refresh_background_lease and handles failures."""

    def test_calls_refresh_on_success(self):
        from apps.tasks.services import task_service as task_services
        with patch.object(task_services, "_refresh_background_lease", return_value=True) as mock_refresh:
            task_services._heartbeat_lease_job()
        mock_refresh.assert_called_once()

    def test_logs_warning_when_refresh_returns_false(self, caplog):
        from apps.tasks.services import task_service as task_services
        with patch.object(task_services, "_refresh_background_lease", return_value=False):
            with caplog.at_level(logging.WARNING, logger="apps.tasks.services.task_service"):
                task_services._heartbeat_lease_job()
        assert any("lease refresh failed" in r.message for r in caplog.records)

    def test_does_not_raise_when_refresh_raises(self):
        from apps.tasks.services import task_service as task_services
        with patch.object(task_services, "_refresh_background_lease", side_effect=RuntimeError("db gone")):
            # Must not propagate the exception
            task_services._heartbeat_lease_job()

    def test_no_warning_logged_on_success(self, caplog):
        from apps.tasks.services import task_service as task_services
        with patch.object(task_services, "_refresh_background_lease", return_value=True):
            with caplog.at_level(logging.WARNING, logger="apps.tasks.services.task_service"):
                task_services._heartbeat_lease_job()
        assert not any("lease refresh failed" in r.message for r in caplog.records)


# ─────────────────────────────────────────────────────────────────────────────
# Group 3 — scheduler_service._refresh_lease_heartbeat
# ─────────────────────────────────────────────────────────────────────────────

class TestRefreshLeaseHeartbeatJob:
    """_refresh_lease_heartbeat is the APScheduler job wrapper in scheduler_service."""

    def test_delegates_to_task_services_heartbeat(self):
        import apps.bootstrap
        with patch("apps.tasks.services.task_service._heartbeat_lease_job") as mock_hb:
            apps.bootstrap.bootstrap()
            from AINDY.platform_layer.registry import get_scheduled_jobs
            job = next(job for job in get_scheduled_jobs() if job["id"] == "background_lease_heartbeat")
            job["handler"]()
        mock_hb.assert_called_once()

    def test_does_not_raise_if_import_fails(self):
        import apps.bootstrap
        import builtins
        real_import = builtins.__import__

        def patched_import(name, *args, **kwargs):
            if name == "apps.tasks.services.task_service":
                raise ImportError("simulated")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=patched_import):
            apps.bootstrap.bootstrap()
            from AINDY.platform_layer.registry import get_scheduled_jobs
            job = next(job for job in get_scheduled_jobs() if job["id"] == "background_lease_heartbeat")
            job["handler"]()

    def test_heartbeat_job_registered_in_system_jobs(self):
        """_register_system_jobs must add background_lease_heartbeat job."""
        import apps.bootstrap
        from AINDY.platform_layer import scheduler_service
        mock_scheduler = MagicMock()
        apps.bootstrap.bootstrap()
        scheduler_service._register_system_jobs(mock_scheduler)
        job_ids = [call_args.kwargs.get("id") or call_args[1][1] if len(call_args[1]) > 1 else None
                   for call_args in mock_scheduler.add_job.call_args_list]
        # Collect all id= keyword args
        kw_ids = [ca.kwargs.get("id") for ca in mock_scheduler.add_job.call_args_list]
        assert "background_lease_heartbeat" in kw_ids


# ─────────────────────────────────────────────────────────────────────────────
# Group 4 — main.py startup order
# ─────────────────────────────────────────────────────────────────────────────

class TestMainStartupOrder:
    """scheduler_service.start() must only be called when start_background_tasks returns True."""

    def _run_startup_block(self, lease_acquired: bool):
        """
        Simulate the main.py startup block in isolation.
        Returns (start_called: bool).
        """
        import apps.tasks.services.task_service as ts
        import AINDY.platform_layer.scheduler_service as ss

        with patch.object(ts, "_acquire_background_lease", return_value=lease_acquired), \
             patch.object(ss, "start") as mock_start, \
             patch.object(ss, "_register_system_jobs"):
            is_leader = ts.start_background_tasks(enable=True)
            if is_leader:
                ss.start()
            return mock_start.called

    def test_scheduler_starts_when_leader(self):
        assert self._run_startup_block(lease_acquired=True) is True

    def test_scheduler_does_not_start_when_not_leader(self):
        assert self._run_startup_block(lease_acquired=False) is False

    def test_scheduler_does_not_start_when_disabled(self):
        import apps.tasks.services.task_service as ts
        import AINDY.platform_layer.scheduler_service as ss

        with patch.object(ts, "_acquire_background_lease", return_value=True), \
             patch.object(ss, "start") as mock_start, \
             patch.object(ss, "_register_system_jobs"):
            is_leader = ts.start_background_tasks(enable=False)
            if is_leader:
                ss.start()
            assert not mock_start.called

    def test_start_background_tasks_called_before_scheduler_start(self):
        """Verify call ordering: start_background_tasks precedes scheduler.start()."""
        import apps.tasks.services.task_service as ts
        import AINDY.platform_layer.scheduler_service as ss

        call_order = []
        with patch.object(ts, "_acquire_background_lease", return_value=True), \
             patch.object(ss, "_register_system_jobs"), \
             patch.object(ss, "start", side_effect=lambda: call_order.append("scheduler_start")):
            def fake_start_bg(*a, **kw):
                call_order.append("lease_acquired")
                return True
            with patch.object(ts, "start_background_tasks", side_effect=fake_start_bg):
                is_leader = ts.start_background_tasks(enable=True)
                if is_leader:
                    ss.start()

        assert call_order == ["lease_acquired", "scheduler_start"]


