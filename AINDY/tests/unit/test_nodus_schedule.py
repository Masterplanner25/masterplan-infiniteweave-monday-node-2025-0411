"""
tests/unit/test_nodus_schedule.py

Unit tests for services/nodus_schedule_service.py — Nodus Scheduler Sprint.

Patch paths (all lazy imports — must patch at source module):
  NodusScheduledJob   → db.models.nodus_scheduled_job.NodusScheduledJob
  AutomationLog       → db.models.automation_log.AutomationLog
  SessionLocal        → db.database.SessionLocal
  normalize_uuid      → utils.uuid_utils.normalize_uuid
  is_background_leader → domain.task_services.is_background_leader
  PersistentFlowRunner → runtime.flow_engine.PersistentFlowRunner
  register_flow       → runtime.flow_engine.register_flow
  FLOW_REGISTRY       → runtime.flow_engine.FLOW_REGISTRY

Coverage groups
===============
A. _parse_cron() — cron validation helper
B. create_nodus_scheduled_job() — happy path + validation errors
C. list_nodus_scheduled_jobs()
D. delete_nodus_scheduled_job()
E. restore_nodus_scheduled_jobs() — startup restoration
F. _run_scheduled_nodus_job() — the APScheduler callback
G. _serialize_job() helper
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

# Pre-import source modules so patching works
import AINDY.db.models.nodus_scheduled_job  # noqa: F401
import AINDY.db.models.automation_log       # noqa: F401
import AINDY.db.database                    # noqa: F401
import AINDY.utils.uuid_utils               # noqa: F401
import AINDY.runtime.nodus_schedule_service  # noqa: F401


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_job_row(**kwargs) -> MagicMock:
    row = MagicMock()
    row.id = kwargs.get("id", uuid.uuid4())
    row.user_id = kwargs.get("user_id", uuid.UUID("00000000-0000-0000-0000-000000000001"))
    row.job_name = kwargs.get("job_name", "test_job")
    row.script = kwargs.get("script", "set_state('ok', True)")
    row.script_name = kwargs.get("script_name", None)
    row.cron_expression = kwargs.get("cron_expression", "0 10 * * *")
    row.input_payload = kwargs.get("input_payload", {})
    row.error_policy = kwargs.get("error_policy", "fail")
    row.max_retries = kwargs.get("max_retries", 3)
    row.is_active = kwargs.get("is_active", True)
    row.last_run_at = kwargs.get("last_run_at", None)
    row.last_run_status = kwargs.get("last_run_status", None)
    row.last_run_log_id = kwargs.get("last_run_log_id", None)
    row.created_at = kwargs.get("created_at", datetime.now(timezone.utc))
    row.updated_at = kwargs.get("updated_at", datetime.now(timezone.utc))
    return row


def _make_db_with_result(result=None):
    """Mock Session: .query().filter().first() → result; .query().filter().all() → [result]."""
    db = MagicMock()
    q = MagicMock()
    db.query.return_value = q
    q.filter.return_value = q
    q.first.return_value = result
    q.order_by.return_value = q
    q.all.return_value = [result] if result is not None else []
    return db


# ---------------------------------------------------------------------------
# A. _parse_cron()
# ---------------------------------------------------------------------------

class TestParseCron:
    def test_valid_expression_returns_trigger(self):
        from AINDY.runtime.nodus_schedule_service import _parse_cron
        from AINDY.apscheduler.triggers.cron import CronTrigger
        assert isinstance(_parse_cron("0 10 * * *"), CronTrigger)

    def test_every_minute(self):
        from AINDY.runtime.nodus_schedule_service import _parse_cron
        from AINDY.apscheduler.triggers.cron import CronTrigger
        assert isinstance(_parse_cron("* * * * *"), CronTrigger)

    def test_invalid_expression_raises(self):
        from AINDY.runtime.nodus_schedule_service import _parse_cron
        with pytest.raises(ValueError, match="Invalid cron"):
            _parse_cron("not_a_cron")

    def test_six_fields_raises(self):
        from AINDY.runtime.nodus_schedule_service import _parse_cron
        with pytest.raises(ValueError):
            _parse_cron("0 10 * * * *")

    def test_apscheduler_missing_raises(self):
        from AINDY.runtime.nodus_schedule_service import _parse_cron
        with patch.dict("sys.modules", {
            "apscheduler": None,
            "apscheduler.triggers": None,
            "apscheduler.triggers.cron": None,
            "AINDY.apscheduler": None,
            "AINDY.apscheduler.triggers": None,
            "AINDY.apscheduler.triggers.cron": None,
        }):
            with pytest.raises(ValueError, match="not installed"):
                _parse_cron("0 10 * * *")

    def test_weekday_range_valid(self):
        from AINDY.runtime.nodus_schedule_service import _parse_cron
        from AINDY.apscheduler.triggers.cron import CronTrigger
        assert isinstance(_parse_cron("0 9 * * 1-5"), CronTrigger)


# ---------------------------------------------------------------------------
# B. create_nodus_scheduled_job()
# ---------------------------------------------------------------------------

class TestCreateNodusScheduledJob:
    """Patch _parse_cron/_register_with_scheduler so we don't need APScheduler running."""

    _PATCHES = [
        "AINDY.runtime.nodus_schedule_service._register_with_scheduler",
        "AINDY.runtime.nodus_schedule_service._next_run",
    ]

    def _call(self, **kwargs):
        from AINDY.runtime.nodus_schedule_service import create_nodus_scheduled_job

        job_row = kwargs.pop("job_row", _make_job_row())
        db = MagicMock()
        db.refresh.side_effect = lambda r: None

        with patch("AINDY.db.models.nodus_scheduled_job.NodusScheduledJob", return_value=job_row), \
             patch("AINDY.utils.uuid_utils.normalize_uuid", return_value="uid-norm"), \
             patch("AINDY.runtime.nodus_schedule_service._register_with_scheduler"), \
             patch("AINDY.runtime.nodus_schedule_service._next_run", return_value="2026-04-02T10:00:00+00:00"):
            return create_nodus_scheduled_job(
                db=db,
                script=kwargs.get("script", "set_state('x', 1)"),
                cron_expression=kwargs.get("cron", "0 10 * * *"),
                user_id=kwargs.get("user_id", "user-abc"),
                job_name=kwargs.get("job_name", "my_job"),
                error_policy=kwargs.get("error_policy", "fail"),
                max_retries=kwargs.get("max_retries", 3),
            ), db, job_row

    def test_returns_serialized_dict(self):
        result, _, _ = self._call()
        assert isinstance(result, dict)
        assert "id" in result

    def test_cron_expression_in_response(self):
        result, _, _ = self._call(cron="0 10 * * *")
        assert result.get("cron_expression") == "0 10 * * *"

    def test_next_run_at_in_response(self):
        result, _, _ = self._call()
        assert result.get("next_run_at") == "2026-04-02T10:00:00+00:00"

    def test_db_add_and_commit_called(self):
        _, db, _ = self._call()
        db.add.assert_called_once()
        db.commit.assert_called()

    def test_register_with_scheduler_called(self):
        from AINDY.runtime.nodus_schedule_service import create_nodus_scheduled_job
        job_row = _make_job_row()
        db = MagicMock()
        db.refresh.side_effect = lambda r: None

        with patch("AINDY.db.models.nodus_scheduled_job.NodusScheduledJob", return_value=job_row), \
             patch("AINDY.utils.uuid_utils.normalize_uuid", return_value="uid"), \
             patch("AINDY.runtime.nodus_schedule_service._register_with_scheduler") as mock_reg, \
             patch("AINDY.runtime.nodus_schedule_service._next_run", return_value=None):
            create_nodus_scheduled_job(
                db=db, script="x", cron_expression="0 10 * * *", user_id="u"
            )

        mock_reg.assert_called_once()

    def test_invalid_cron_raises_before_db_write(self):
        from AINDY.runtime.nodus_schedule_service import create_nodus_scheduled_job
        db = MagicMock()
        with pytest.raises(ValueError, match="Invalid cron"):
            create_nodus_scheduled_job(
                db=db, script="x", cron_expression="not_valid", user_id="u"
            )
        db.add.assert_not_called()


# ---------------------------------------------------------------------------
# C. list_nodus_scheduled_jobs()
# ---------------------------------------------------------------------------

class TestListNodusScheduledJobs:
    def test_returns_list_of_dicts(self):
        from AINDY.runtime.nodus_schedule_service import list_nodus_scheduled_jobs

        job = _make_job_row()
        db = _make_db_with_result(job)

        with patch("AINDY.db.models.nodus_scheduled_job.NodusScheduledJob"), \
             patch("AINDY.utils.uuid_utils.normalize_uuid", return_value="uid-norm"):
            result = list_nodus_scheduled_jobs(db=db, user_id="user-abc")

        assert isinstance(result, list)
        assert len(result) == 1
        assert "id" in result[0]

    def test_empty_when_no_jobs(self):
        from AINDY.runtime.nodus_schedule_service import list_nodus_scheduled_jobs

        db = _make_db_with_result(None)

        with patch("AINDY.db.models.nodus_scheduled_job.NodusScheduledJob"), \
             patch("AINDY.utils.uuid_utils.normalize_uuid", return_value="uid-norm"):
            result = list_nodus_scheduled_jobs(db=db, user_id="user-abc")

        assert result == []

    def test_multiple_jobs(self):
        from AINDY.runtime.nodus_schedule_service import list_nodus_scheduled_jobs

        jobs = [_make_job_row(job_name=f"job_{i}") for i in range(3)]
        db = MagicMock()
        q = MagicMock()
        db.query.return_value = q
        q.filter.return_value = q
        q.order_by.return_value = q
        q.all.return_value = jobs

        with patch("AINDY.db.models.nodus_scheduled_job.NodusScheduledJob"), \
             patch("AINDY.utils.uuid_utils.normalize_uuid", return_value="uid-norm"):
            result = list_nodus_scheduled_jobs(db=db, user_id="user-abc")

        assert len(result) == 3


# ---------------------------------------------------------------------------
# D. delete_nodus_scheduled_job()
# ---------------------------------------------------------------------------

class TestDeleteNodusScheduledJob:
    _VALID_JOB_ID = str(uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))

    def test_returns_true_on_success(self):
        from AINDY.runtime.nodus_schedule_service import delete_nodus_scheduled_job

        job = _make_job_row(id=uuid.UUID(self._VALID_JOB_ID))
        db = _make_db_with_result(job)

        with patch("AINDY.db.models.nodus_scheduled_job.NodusScheduledJob"), \
             patch("AINDY.utils.uuid_utils.normalize_uuid", return_value="uid-norm"), \
             patch("AINDY.runtime.nodus_schedule_service._remove_from_scheduler"):
            result = delete_nodus_scheduled_job(db=db, job_id=self._VALID_JOB_ID, user_id="u")

        assert result is True

    def test_sets_is_active_false(self):
        from AINDY.runtime.nodus_schedule_service import delete_nodus_scheduled_job

        job = _make_job_row(id=uuid.UUID(self._VALID_JOB_ID))
        db = _make_db_with_result(job)

        with patch("AINDY.db.models.nodus_scheduled_job.NodusScheduledJob"), \
             patch("AINDY.utils.uuid_utils.normalize_uuid", return_value="uid-norm"), \
             patch("AINDY.runtime.nodus_schedule_service._remove_from_scheduler"):
            delete_nodus_scheduled_job(db=db, job_id=self._VALID_JOB_ID, user_id="u")

        assert job.is_active is False
        db.commit.assert_called()

    def test_calls_remove_from_scheduler(self):
        from AINDY.runtime.nodus_schedule_service import delete_nodus_scheduled_job

        job = _make_job_row(id=uuid.UUID(self._VALID_JOB_ID))
        db = _make_db_with_result(job)

        with patch("AINDY.db.models.nodus_scheduled_job.NodusScheduledJob"), \
             patch("AINDY.utils.uuid_utils.normalize_uuid", return_value="uid-norm"), \
             patch("AINDY.runtime.nodus_schedule_service._remove_from_scheduler") as mock_rm:
            delete_nodus_scheduled_job(db=db, job_id=self._VALID_JOB_ID, user_id="u")

        mock_rm.assert_called_once_with(self._VALID_JOB_ID)

    def test_returns_false_when_not_found(self):
        from AINDY.runtime.nodus_schedule_service import delete_nodus_scheduled_job

        db = _make_db_with_result(None)
        with patch("AINDY.db.models.nodus_scheduled_job.NodusScheduledJob"), \
             patch("AINDY.utils.uuid_utils.normalize_uuid", return_value="uid-norm"):
            result = delete_nodus_scheduled_job(
                db=db, job_id=self._VALID_JOB_ID, user_id="u"
            )
        assert result is False

    def test_returns_false_for_invalid_uuid(self):
        from AINDY.runtime.nodus_schedule_service import delete_nodus_scheduled_job

        db = MagicMock()
        with patch("AINDY.utils.uuid_utils.normalize_uuid", return_value="uid"):
            result = delete_nodus_scheduled_job(db=db, job_id="not-a-uuid", user_id="u")
        assert result is False
        db.add.assert_not_called()


# ---------------------------------------------------------------------------
# E. restore_nodus_scheduled_jobs()
# ---------------------------------------------------------------------------

class TestRestoreNodusScheduledJobs:
    def test_restores_active_jobs(self):
        from AINDY.runtime.nodus_schedule_service import restore_nodus_scheduled_jobs

        jobs = [_make_job_row(), _make_job_row()]
        mock_db = MagicMock()
        q = MagicMock()
        mock_db.query.return_value = q
        q.filter.return_value = q
        q.all.return_value = jobs

        with patch("AINDY.db.database.SessionLocal", return_value=mock_db), \
             patch("AINDY.db.models.nodus_scheduled_job.NodusScheduledJob"), \
             patch("AINDY.runtime.nodus_schedule_service._parse_cron", return_value=MagicMock()), \
             patch("AINDY.runtime.nodus_schedule_service._register_with_scheduler") as mock_reg:
            count = restore_nodus_scheduled_jobs()

        assert count == 2
        assert mock_reg.call_count == 2

    def test_returns_zero_when_no_jobs(self):
        from AINDY.runtime.nodus_schedule_service import restore_nodus_scheduled_jobs

        mock_db = MagicMock()
        q = MagicMock()
        mock_db.query.return_value = q
        q.filter.return_value = q
        q.all.return_value = []

        with patch("AINDY.db.database.SessionLocal", return_value=mock_db), \
             patch("AINDY.db.models.nodus_scheduled_job.NodusScheduledJob"):
            count = restore_nodus_scheduled_jobs()

        assert count == 0

    def test_skips_job_with_bad_cron_continues_next(self):
        from AINDY.runtime.nodus_schedule_service import restore_nodus_scheduled_jobs

        jobs = [_make_job_row(), _make_job_row()]
        mock_db = MagicMock()
        q = MagicMock()
        mock_db.query.return_value = q
        q.filter.return_value = q
        q.all.return_value = jobs

        with patch("AINDY.db.database.SessionLocal", return_value=mock_db), \
             patch("AINDY.db.models.nodus_scheduled_job.NodusScheduledJob"), \
             patch("AINDY.runtime.nodus_schedule_service._parse_cron",
                   side_effect=[ValueError("bad"), MagicMock()]), \
             patch("AINDY.runtime.nodus_schedule_service._register_with_scheduler") as mock_reg:
            count = restore_nodus_scheduled_jobs()

        assert count == 1
        assert mock_reg.call_count == 1

    def test_db_session_closed_even_on_scan_error(self):
        from AINDY.runtime.nodus_schedule_service import restore_nodus_scheduled_jobs

        mock_db = MagicMock()
        mock_db.query.side_effect = RuntimeError("db down")

        with patch("AINDY.db.database.SessionLocal", return_value=mock_db), \
             patch("AINDY.db.models.nodus_scheduled_job.NodusScheduledJob"):
            restore_nodus_scheduled_jobs()  # must not raise

        mock_db.close.assert_called_once()


# ---------------------------------------------------------------------------
# F. _run_scheduled_nodus_job() — APScheduler callback
# ---------------------------------------------------------------------------

class TestRunScheduledNodusJob:
    def _job_id(self):
        return str(uuid.uuid4())

    def test_skips_when_not_leader(self):
        from AINDY.runtime.nodus_schedule_service import _run_scheduled_nodus_job

        with patch("AINDY.domain.task_services.is_background_leader", return_value=False), \
             patch("AINDY.db.database.SessionLocal") as mock_session:
            _run_scheduled_nodus_job(self._job_id())

        mock_session.assert_not_called()

    def test_skips_when_job_not_found(self):
        from AINDY.runtime.nodus_schedule_service import _run_scheduled_nodus_job

        mock_db = _make_db_with_result(None)

        with patch("AINDY.domain.task_services.is_background_leader", return_value=True), \
             patch("AINDY.db.database.SessionLocal", return_value=mock_db), \
             patch("AINDY.db.models.nodus_scheduled_job.NodusScheduledJob"):
            _run_scheduled_nodus_job(self._job_id())

        mock_db.add.assert_not_called()

    def test_skips_when_job_inactive(self):
        from AINDY.runtime.nodus_schedule_service import _run_scheduled_nodus_job

        job = _make_job_row(is_active=False)
        mock_db = _make_db_with_result(job)

        with patch("AINDY.domain.task_services.is_background_leader", return_value=True), \
             patch("AINDY.db.database.SessionLocal", return_value=mock_db), \
             patch("AINDY.db.models.nodus_scheduled_job.NodusScheduledJob"):
            _run_scheduled_nodus_job(self._job_id())

        mock_db.add.assert_not_called()

    def _run_with_result(self, flow_result, job=None):
        """Helper to run _run_scheduled_nodus_job with a mock flow result."""
        from AINDY.runtime.nodus_schedule_service import _run_scheduled_nodus_job

        _job = job or _make_job_row()
        mock_db = _make_db_with_result(_job)
        mock_log = MagicMock()

        with patch("AINDY.domain.task_services.is_background_leader", return_value=True), \
             patch("AINDY.db.database.SessionLocal", return_value=mock_db), \
             patch("AINDY.db.models.nodus_scheduled_job.NodusScheduledJob"), \
             patch("AINDY.db.models.automation_log.AutomationLog", return_value=mock_log), \
             patch("AINDY.runtime.nodus_execution_service.run_nodus_script_via_flow", return_value=flow_result), \
             patch("AINDY.runtime.nodus_execution_service.format_nodus_flow_result", return_value={
                 "status": flow_result.get("status"),
                 "trace_id": flow_result.get("trace_id"),
                 "run_id": flow_result.get("run_id"),
                 "nodus_status": (flow_result.get("state") or {}).get("nodus_status"),
                 "events_emitted": len((flow_result.get("state") or {}).get("nodus_events") or []),
                 "memory_writes_count": len((flow_result.get("state") or {}).get("nodus_memory_writes") or []),
                 "error": (flow_result.get("state") or {}).get("nodus_error") or flow_result.get("error"),
                 "execution_record": {"run_id": flow_result.get("run_id")},
             }):
            _run_scheduled_nodus_job(str(_job.id))

        return _job, mock_log

    def test_success_sets_job_last_run_status(self):
        job, _ = self._run_with_result({
            "status": "SUCCESS",
            "run_id": "r1",
            "state": {"nodus_status": "success", "nodus_events": [], "nodus_memory_writes": []},
        })
        assert job.last_run_status == "success"

    def test_success_sets_last_run_at(self):
        job, _ = self._run_with_result({
            "status": "SUCCESS",
            "run_id": "r1",
            "state": {"nodus_status": "success", "nodus_events": [], "nodus_memory_writes": []},
        })
        assert job.last_run_at is not None

    def test_flow_failure_sets_failure_status(self):
        job, _ = self._run_with_result({
            "status": "FAILED",
            "error": "node failed",
            "run_id": "r2",
            "state": {"nodus_status": "failure", "nodus_events": [], "nodus_memory_writes": []},
        })
        assert job.last_run_status == "failure"

    def test_runner_exception_sets_error_status_does_not_raise(self):
        from AINDY.runtime.nodus_schedule_service import _run_scheduled_nodus_job

        job = _make_job_row()
        mock_db = _make_db_with_result(job)

        with patch("AINDY.domain.task_services.is_background_leader", return_value=True), \
             patch("AINDY.db.database.SessionLocal", return_value=mock_db), \
             patch("AINDY.db.models.nodus_scheduled_job.NodusScheduledJob"), \
             patch("AINDY.db.models.automation_log.AutomationLog", return_value=MagicMock()), \
             patch("AINDY.runtime.nodus_execution_service.run_nodus_script_via_flow", side_effect=RuntimeError("boom")):
            _run_scheduled_nodus_job(str(job.id))  # must not raise

        assert job.last_run_status == "error"

    def test_db_session_always_closed(self):
        from AINDY.runtime.nodus_schedule_service import _run_scheduled_nodus_job

        job = _make_job_row()
        mock_db = _make_db_with_result(job)
        flow_result = {
            "status": "SUCCESS", "run_id": "r", "trace_id": "trace-r",
            "state": {"nodus_status": "success", "nodus_events": [], "nodus_memory_writes": []},
        }

        with patch("AINDY.domain.task_services.is_background_leader", return_value=True), \
             patch("AINDY.db.database.SessionLocal", return_value=mock_db), \
             patch("AINDY.db.models.nodus_scheduled_job.NodusScheduledJob"), \
             patch("AINDY.db.models.automation_log.AutomationLog", return_value=MagicMock()), \
             patch("AINDY.runtime.nodus_execution_service.run_nodus_script_via_flow", return_value=flow_result), \
             patch("AINDY.runtime.nodus_execution_service.format_nodus_flow_result", return_value={
                 "status": "SUCCESS",
                 "trace_id": "trace-r",
                 "run_id": "r",
                 "nodus_status": "success",
                 "events_emitted": 0,
                 "memory_writes_count": 0,
                 "error": None,
                 "execution_record": {"run_id": "r"},
             }):
            _run_scheduled_nodus_job(str(job.id))

        mock_db.close.assert_called_once()

    def test_uses_shared_nodus_flow_runner(self):
        from AINDY.runtime.nodus_schedule_service import _run_scheduled_nodus_job

        job = _make_job_row()
        mock_db = _make_db_with_result(job)
        flow_result = {
            "status": "SUCCESS", "run_id": "r", "trace_id": "trace-r",
            "state": {"nodus_status": "success", "nodus_events": [], "nodus_memory_writes": []},
        }

        with patch("AINDY.domain.task_services.is_background_leader", return_value=True), \
             patch("AINDY.db.database.SessionLocal", return_value=mock_db), \
             patch("AINDY.db.models.nodus_scheduled_job.NodusScheduledJob"), \
             patch("AINDY.db.models.automation_log.AutomationLog", return_value=MagicMock()), \
             patch("AINDY.runtime.nodus_execution_service.run_nodus_script_via_flow", return_value=flow_result) as mock_run, \
             patch("AINDY.runtime.nodus_execution_service.format_nodus_flow_result", return_value={
                 "status": "SUCCESS",
                 "trace_id": "trace-r",
                 "run_id": "r",
                 "nodus_status": "success",
                 "events_emitted": 0,
                 "memory_writes_count": 0,
                 "error": None,
                 "execution_record": {"run_id": "r"},
             }):
            _run_scheduled_nodus_job(str(job.id))

        mock_run.assert_called_once()
        assert mock_run.call_args.kwargs["workflow_type"] == "nodus_schedule"
        assert mock_run.call_args.kwargs["trace_id"] is not None

    def test_leader_check_exception_skips_gracefully(self):
        from AINDY.runtime.nodus_schedule_service import _run_scheduled_nodus_job

        with patch("AINDY.domain.task_services.is_background_leader", side_effect=RuntimeError("no db")), \
             patch("AINDY.db.database.SessionLocal") as mock_session:
            _run_scheduled_nodus_job(self._job_id())  # must not raise

        mock_session.assert_not_called()


# ---------------------------------------------------------------------------
# G. _serialize_job()
# ---------------------------------------------------------------------------

class TestSerializeJob:
    def test_contains_all_expected_keys(self):
        from AINDY.runtime.nodus_schedule_service import _serialize_job

        row = _make_job_row()
        result = _serialize_job(row)
        expected = {
            "id", "job_name", "script_name", "cron_expression",
            "error_policy", "max_retries", "is_active",
            "last_run_at", "last_run_status", "last_run_log_id",
            "next_run_at", "created_at",
        }
        assert expected == set(result.keys())

    def test_id_is_string(self):
        from AINDY.runtime.nodus_schedule_service import _serialize_job

        row = _make_job_row(id=uuid.UUID("aaaabbbb-cccc-dddd-eeee-ffff00001111"))
        result = _serialize_job(row)
        assert isinstance(result["id"], str)

    def test_next_run_at_passed_through(self):
        from AINDY.runtime.nodus_schedule_service import _serialize_job

        row = _make_job_row()
        result = _serialize_job(row, next_run_at="2026-04-02T10:00:00+00:00")
        assert result["next_run_at"] == "2026-04-02T10:00:00+00:00"

    def test_last_run_at_none_when_not_set(self):
        from AINDY.runtime.nodus_schedule_service import _serialize_job

        row = _make_job_row(last_run_at=None)
        result = _serialize_job(row)
        assert result["last_run_at"] is None

    def test_created_at_is_isoformat_string(self):
        from AINDY.runtime.nodus_schedule_service import _serialize_job

        now = datetime.now(timezone.utc)
        row = _make_job_row(created_at=now)
        result = _serialize_job(row)
        assert result["created_at"] == now.isoformat()


