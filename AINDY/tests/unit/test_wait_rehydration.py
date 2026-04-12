"""
Tests for core.wait_rehydration.rehydrate_waiting_eus().

Groups
------
A  Happy path — EUs are registered correctly
B  Idempotency / duplicate guard
C  Graceful degradation — missing or malformed wait_condition
D  Scheduler field mapping — priority, tenant_id, eu_type, correlation_id
E  Edge cases — empty table, DB error, all-skipped
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch, call

import pytest

from AINDY.core.wait_rehydration import rehydrate_waiting_eus, _TIME_SENTINEL


# ── Helpers ───────────────────────────────────────────────────────────────────

_UNSET = object()


def _eu(
    *,
    status="waiting",
    wait_condition=None,
    eu_type="flow",
    priority="normal",
    user_id=_UNSET,
    tenant_id=None,
    correlation_id=None,
    flow_run_id=None,
):
    eu = MagicMock()
    eu.id = uuid.uuid4()
    eu.status = status
    eu.wait_condition = wait_condition
    eu.type = eu_type
    eu.priority = priority
    # user_id=_UNSET → auto-assign random UUID (most tests don't care).
    # user_id=None   → explicitly no user (tests the "system" fallback).
    eu.user_id = uuid.uuid4() if user_id is _UNSET else user_id
    eu.tenant_id = tenant_id
    eu.correlation_id = correlation_id
    # Explicit None avoids the MagicMock truthy-attribute trap that would
    # trigger the FlowRun ownership guard in the EU resume callback.
    eu.flow_run_id = flow_run_id
    return eu


def _db_with(eus):
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = eus
    return db


def _scheduler(*, already_waiting_ids=None):
    se = MagicMock()
    already = set(already_waiting_ids or [])
    se.waiting_for.side_effect = lambda run_id: run_id if run_id in already else None
    return se


EVENT_WC = {"type": "event", "event_name": "approval.received", "trigger_at": None, "correlation_id": None}
TIME_WC  = {"type": "time",  "event_name": None, "trigger_at": "2099-01-01T00:00:00", "correlation_id": None}
EXT_WC   = {"type": "external", "event_name": "webhook.paid", "trigger_at": None, "correlation_id": "inv-123"}


# ═══════════════════════════════════════════════════════════════════════════════
# A: Happy path
# ═══════════════════════════════════════════════════════════════════════════════

class TestRehydrateHappyPath:

    def test_event_eu_is_registered(self):
        eu = _eu(wait_condition=EVENT_WC)
        db = _db_with([eu])
        se = _scheduler()

        with patch("core.wait_rehydration.get_scheduler_engine", return_value=se):
            count = rehydrate_waiting_eus(db)

        assert count == 1
        se.register_wait.assert_called_once()

    def test_register_wait_called_with_correct_event_name(self):
        eu = _eu(wait_condition=EVENT_WC)
        db = _db_with([eu])
        se = _scheduler()

        with patch("core.wait_rehydration.get_scheduler_engine", return_value=se):
            rehydrate_waiting_eus(db)

        _, kwargs = se.register_wait.call_args
        assert kwargs["wait_for_event"] == "approval.received"

    def test_register_wait_called_with_correct_run_id(self):
        eu = _eu(wait_condition=EVENT_WC)
        db = _db_with([eu])
        se = _scheduler()

        with patch("core.wait_rehydration.get_scheduler_engine", return_value=se):
            rehydrate_waiting_eus(db)

        _, kwargs = se.register_wait.call_args
        assert kwargs["run_id"] == str(eu.id)
        assert kwargs["eu_id"] == str(eu.id)

    def test_time_eu_registered_with_sentinel(self):
        eu = _eu(wait_condition=TIME_WC)
        db = _db_with([eu])
        se = _scheduler()

        with patch("core.wait_rehydration.get_scheduler_engine", return_value=se):
            count = rehydrate_waiting_eus(db)

        assert count == 1
        _, kwargs = se.register_wait.call_args
        assert kwargs["wait_for_event"] == _TIME_SENTINEL

    def test_external_eu_registered(self):
        eu = _eu(wait_condition=EXT_WC, correlation_id="inv-123")
        db = _db_with([eu])
        se = _scheduler()

        with patch("core.wait_rehydration.get_scheduler_engine", return_value=se):
            count = rehydrate_waiting_eus(db)

        assert count == 1
        _, kwargs = se.register_wait.call_args
        assert kwargs["wait_for_event"] == "webhook.paid"

    def test_multiple_eus_all_registered(self):
        eus = [_eu(wait_condition=EVENT_WC) for _ in range(4)]
        db = _db_with(eus)
        se = _scheduler()

        with patch("core.wait_rehydration.get_scheduler_engine", return_value=se):
            count = rehydrate_waiting_eus(db)

        assert count == 4
        assert se.register_wait.call_count == 4

    def test_resume_callback_is_callable(self):
        eu = _eu(wait_condition=EVENT_WC)
        db = _db_with([eu])
        se = _scheduler()

        with patch("core.wait_rehydration.get_scheduler_engine", return_value=se):
            rehydrate_waiting_eus(db)

        _, kwargs = se.register_wait.call_args
        assert callable(kwargs["resume_callback"])

    def test_wait_condition_object_forwarded(self):
        eu = _eu(wait_condition=EVENT_WC)
        db = _db_with([eu])
        se = _scheduler()

        with patch("core.wait_rehydration.get_scheduler_engine", return_value=se):
            rehydrate_waiting_eus(db)

        _, kwargs = se.register_wait.call_args
        wc = kwargs["wait_condition"]
        assert wc is not None
        assert wc.event_name == "approval.received"


# ═══════════════════════════════════════════════════════════════════════════════
# B: Idempotency / duplicate guard
# ═══════════════════════════════════════════════════════════════════════════════

class TestRehydrateIdempotency:

    def test_already_registered_eu_is_skipped(self):
        eu = _eu(wait_condition=EVENT_WC)
        db = _db_with([eu])
        # Simulate eu already in scheduler
        se = _scheduler(already_waiting_ids=[str(eu.id)])

        with patch("core.wait_rehydration.get_scheduler_engine", return_value=se):
            count = rehydrate_waiting_eus(db)

        assert count == 0
        se.register_wait.assert_not_called()

    def test_partial_duplicate_skipped(self):
        eu_fresh = _eu(wait_condition=EVENT_WC)
        eu_dupe  = _eu(wait_condition=EVENT_WC)
        db = _db_with([eu_fresh, eu_dupe])
        se = _scheduler(already_waiting_ids=[str(eu_dupe.id)])

        with patch("core.wait_rehydration.get_scheduler_engine", return_value=se):
            count = rehydrate_waiting_eus(db)

        assert count == 1
        assert se.register_wait.call_count == 1
        _, kwargs = se.register_wait.call_args
        assert kwargs["eu_id"] == str(eu_fresh.id)

    def test_calling_twice_is_safe(self):
        """Second call skips all EUs already registered by first call."""
        eu = _eu(wait_condition=EVENT_WC)
        db = _db_with([eu])
        eu_id = str(eu.id)
        registered = set()

        def _fake_register_wait(**kwargs):
            registered.add(kwargs["run_id"])

        def _fake_waiting_for(run_id):
            return run_id if run_id in registered else None

        se = MagicMock()
        se.register_wait.side_effect = _fake_register_wait
        se.waiting_for.side_effect = _fake_waiting_for

        with patch("core.wait_rehydration.get_scheduler_engine", return_value=se):
            first  = rehydrate_waiting_eus(db)
            second = rehydrate_waiting_eus(db)

        assert first  == 1
        assert second == 0


# ═══════════════════════════════════════════════════════════════════════════════
# C: Graceful degradation
# ═══════════════════════════════════════════════════════════════════════════════

class TestRehydrateDegradation:

    def test_eu_without_wait_condition_is_skipped(self):
        eu = _eu(wait_condition=None)
        db = _db_with([eu])
        se = _scheduler()

        with patch("core.wait_rehydration.get_scheduler_engine", return_value=se):
            count = rehydrate_waiting_eus(db)

        assert count == 0
        se.register_wait.assert_not_called()

    def test_eu_with_empty_wait_condition_dict_is_skipped(self):
        eu = _eu(wait_condition={})
        db = _db_with([eu])
        se = _scheduler()

        with patch("core.wait_rehydration.get_scheduler_engine", return_value=se):
            count = rehydrate_waiting_eus(db)

        # Empty dict → from_dict returns a default event WC with no event_name
        # → skipped (no event_name and type is not time)
        assert count == 0

    def test_eu_with_event_type_but_no_event_name_is_skipped(self):
        eu = _eu(wait_condition={"type": "event", "event_name": None})
        db = _db_with([eu])
        se = _scheduler()

        with patch("core.wait_rehydration.get_scheduler_engine", return_value=se):
            count = rehydrate_waiting_eus(db)

        assert count == 0
        se.register_wait.assert_not_called()

    def test_db_query_error_returns_zero(self):
        db = MagicMock()
        db.query.side_effect = Exception("connection lost")
        se = _scheduler()

        with patch("core.wait_rehydration.get_scheduler_engine", return_value=se):
            count = rehydrate_waiting_eus(db)

        assert count == 0

    def test_register_wait_error_on_one_does_not_abort_others(self):
        eu_bad  = _eu(wait_condition=EVENT_WC)
        eu_good = _eu(wait_condition=EXT_WC)
        db = _db_with([eu_bad, eu_good])
        se = _scheduler()
        # First call raises, second succeeds
        se.register_wait.side_effect = [RuntimeError("quota error"), None]

        with patch("core.wait_rehydration.get_scheduler_engine", return_value=se):
            count = rehydrate_waiting_eus(db)

        # eu_bad failed (counted as skipped), eu_good succeeded
        assert count == 1

    def test_empty_table_returns_zero(self):
        db = _db_with([])
        se = _scheduler()

        with patch("core.wait_rehydration.get_scheduler_engine", return_value=se):
            count = rehydrate_waiting_eus(db)

        assert count == 0
        se.register_wait.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════════
# D: Scheduler field mapping
# ═══════════════════════════════════════════════════════════════════════════════

class TestRehydrateFieldMapping:

    def test_tenant_id_preferred_over_user_id(self):
        eu = _eu(wait_condition=EVENT_WC, tenant_id="t-explicit", user_id=uuid.uuid4())
        db = _db_with([eu])
        se = _scheduler()

        with patch("core.wait_rehydration.get_scheduler_engine", return_value=se):
            rehydrate_waiting_eus(db)

        _, kwargs = se.register_wait.call_args
        assert kwargs["tenant_id"] == "t-explicit"

    def test_user_id_fallback_when_no_tenant_id(self):
        uid = uuid.uuid4()
        eu = _eu(wait_condition=EVENT_WC, tenant_id=None, user_id=uid)
        db = _db_with([eu])
        se = _scheduler()

        with patch("core.wait_rehydration.get_scheduler_engine", return_value=se):
            rehydrate_waiting_eus(db)

        _, kwargs = se.register_wait.call_args
        assert kwargs["tenant_id"] == str(uid)

    def test_system_fallback_when_no_tenant_or_user(self):
        eu = _eu(wait_condition=EVENT_WC, tenant_id=None, user_id=None)
        db = _db_with([eu])
        se = _scheduler()

        with patch("core.wait_rehydration.get_scheduler_engine", return_value=se):
            rehydrate_waiting_eus(db)

        _, kwargs = se.register_wait.call_args
        assert kwargs["tenant_id"] == "system"

    def test_priority_forwarded(self):
        eu = _eu(wait_condition=EVENT_WC, priority="high")
        db = _db_with([eu])
        se = _scheduler()

        with patch("core.wait_rehydration.get_scheduler_engine", return_value=se):
            rehydrate_waiting_eus(db)

        _, kwargs = se.register_wait.call_args
        assert kwargs["priority"] == "high"

    def test_eu_type_forwarded(self):
        eu = _eu(wait_condition=EVENT_WC, eu_type="agent")
        db = _db_with([eu])
        se = _scheduler()

        with patch("core.wait_rehydration.get_scheduler_engine", return_value=se):
            rehydrate_waiting_eus(db)

        _, kwargs = se.register_wait.call_args
        assert kwargs["eu_type"] == "agent"

    def test_correlation_id_forwarded(self):
        eu = _eu(wait_condition=EVENT_WC, correlation_id="corr-xyz")
        db = _db_with([eu])
        se = _scheduler()

        with patch("core.wait_rehydration.get_scheduler_engine", return_value=se):
            rehydrate_waiting_eus(db)

        _, kwargs = se.register_wait.call_args
        assert kwargs["correlation_id"] == "corr-xyz"

    def test_correlation_id_none_when_absent(self):
        eu = _eu(wait_condition=EVENT_WC, correlation_id=None)
        db = _db_with([eu])
        se = _scheduler()

        with patch("core.wait_rehydration.get_scheduler_engine", return_value=se):
            rehydrate_waiting_eus(db)

        _, kwargs = se.register_wait.call_args
        assert kwargs["correlation_id"] is None

    def test_default_priority_when_eu_has_none(self):
        eu = _eu(wait_condition=EVENT_WC)
        eu.priority = None
        db = _db_with([eu])
        se = _scheduler()

        with patch("core.wait_rehydration.get_scheduler_engine", return_value=se):
            rehydrate_waiting_eus(db)

        _, kwargs = se.register_wait.call_args
        assert kwargs["priority"] == "normal"


# ═══════════════════════════════════════════════════════════════════════════════
# E: Resume callback correctness
# ═══════════════════════════════════════════════════════════════════════════════

class TestRehydrateCallback:

    def test_callback_calls_resume_execution_unit(self):
        eu = _eu(wait_condition=EVENT_WC)
        db = _db_with([eu])
        se = _scheduler()

        with patch("core.wait_rehydration.get_scheduler_engine", return_value=se):
            rehydrate_waiting_eus(db)

        _, kwargs = se.register_wait.call_args
        callback = kwargs["resume_callback"]

        mock_eus = MagicMock()
        mock_eus.resume_execution_unit.return_value = True
        mock_session = MagicMock()

        # Invoke the closure, patching the lazy imports it uses internally
        with patch("db.database.SessionLocal", return_value=mock_session), \
             patch("core.execution_unit_service.ExecutionUnitService", return_value=mock_eus):
            callback()

        mock_eus.resume_execution_unit.assert_called_once_with(str(eu.id))

    def test_callback_closes_db_session_on_success(self):
        eu = _eu(wait_condition=EVENT_WC)
        db = _db_with([eu])
        se = _scheduler()

        with patch("core.wait_rehydration.get_scheduler_engine", return_value=se):
            rehydrate_waiting_eus(db)

        _, kwargs = se.register_wait.call_args
        callback = kwargs["resume_callback"]

        mock_session = MagicMock()
        mock_eus = MagicMock()
        mock_eus.resume_execution_unit.return_value = True

        with patch("db.database.SessionLocal", return_value=mock_session), \
             patch("core.execution_unit_service.ExecutionUnitService", return_value=mock_eus):
            callback()

        mock_session.close.assert_called_once()

    def test_callback_closes_db_session_on_error(self):
        eu = _eu(wait_condition=EVENT_WC)
        db = _db_with([eu])
        se = _scheduler()

        with patch("core.wait_rehydration.get_scheduler_engine", return_value=se):
            rehydrate_waiting_eus(db)

        _, kwargs = se.register_wait.call_args
        callback = kwargs["resume_callback"]

        mock_session = MagicMock()
        mock_eus = MagicMock()
        mock_eus.resume_execution_unit.side_effect = RuntimeError("db error")

        with patch("db.database.SessionLocal", return_value=mock_session), \
             patch("core.execution_unit_service.ExecutionUnitService", return_value=mock_eus):
            callback()  # must not raise

        mock_session.close.assert_called_once()
