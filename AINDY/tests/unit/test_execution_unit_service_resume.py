"""
Tests for ExecutionUnitService.resume_execution_unit() idempotency guard.

The scheduler registers two callbacks per flow WAIT:
  - runner.resume()            (PersistentFlowRunner)
  - eus.resume_execution_unit()  (ExecutionUnitService)

Both fire when an event arrives.  The second call must be a clean no-op:
  - No duplicate status transition
  - No duplicate event emission
  - Returns True (caller treats skip as success)
  - Emits a debug log

Groups
------
A  Guard fires for already-resumed statuses (resumed / executing / completed)
B  Guard does not fire for valid starting statuses (waiting / pending)
C  Guard pre-check exception falls through to normal path
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch
import uuid

import pytest

from core.execution_unit_service import ExecutionUnitService


# ── Helpers ───────────────────────────────────────────────────────────────────

def _eu(status: str):
    """Return a minimal mock ExecutionUnit with the given status."""
    eu = MagicMock()
    eu.id = uuid.uuid4()
    eu.status = status
    eu.wait_condition = None
    return eu


def _eus(eu):
    """Build an ExecutionUnitService whose DB query returns `eu`."""
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = eu
    return ExecutionUnitService(db=db)


# ═══════════════════════════════════════════════════════════════════════════════
# A: Guard fires for terminal/in-progress statuses
# ═══════════════════════════════════════════════════════════════════════════════

class TestResumeIdempotencyGuard:

    @pytest.mark.parametrize("status", ["resumed", "executing", "completed"])
    def test_returns_true_when_already_past_waiting(self, status):
        eu = _eu(status)
        eus = _eus(eu)
        result = eus.resume_execution_unit(str(eu.id))
        assert result is True

    @pytest.mark.parametrize("status", ["resumed", "executing", "completed"])
    def test_no_status_mutation_when_guard_fires(self, status):
        eu = _eu(status)
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = eu
        eus = ExecutionUnitService(db=db)
        eus.resume_execution_unit(str(eu.id))
        # status should not have been changed
        assert eu.status == status

    @pytest.mark.parametrize("status", ["resumed", "executing", "completed"])
    def test_update_status_not_called_when_guard_fires(self, status):
        eu = _eu(status)
        eus = _eus(eu)
        with patch.object(eus, "update_status") as mock_upd:
            eus.resume_execution_unit(str(eu.id))
        mock_upd.assert_not_called()

    @pytest.mark.parametrize("status", ["resumed", "executing", "completed"])
    def test_debug_log_emitted_when_guard_fires(self, status, caplog):
        import logging
        eu = _eu(status)
        eus = _eus(eu)
        with caplog.at_level(logging.DEBUG, logger="core.execution_unit_service"):
            eus.resume_execution_unit(str(eu.id))
        assert any("skipped duplicate resume" in r.message for r in caplog.records)

    @pytest.mark.parametrize("status", ["resumed", "executing", "completed"])
    def test_no_wait_condition_cleared_when_guard_fires(self, status):
        eu = _eu(status)
        eu.wait_condition = {"type": "event", "event_name": "foo"}
        db = MagicMock()
        # first query (idempotency check) returns eu with non-waiting status
        db.query.return_value.filter.return_value.first.return_value = eu
        eus = ExecutionUnitService(db=db)
        eus.resume_execution_unit(str(eu.id))
        # wait_condition should be untouched
        assert eu.wait_condition == {"type": "event", "event_name": "foo"}


# ═══════════════════════════════════════════════════════════════════════════════
# B: Guard does NOT fire for valid starting statuses
# ═══════════════════════════════════════════════════════════════════════════════

class TestResumeGuardAllowsValidTransitions:

    def test_waiting_status_proceeds_to_normal_path(self):
        eu = _eu("waiting")
        eus = _eus(eu)
        with patch.object(eus, "update_status", return_value=True) as mock_upd:
            eus.resume_execution_unit(str(eu.id))
        # update_status should have been called (normal path)
        assert mock_upd.called

    def test_failed_status_also_proceeds(self):
        """'failed' is not in the guard set — let update_status decide."""
        eu = _eu("failed")
        eus = _eus(eu)
        with patch.object(eus, "update_status", return_value=False) as mock_upd:
            eus.resume_execution_unit(str(eu.id))
        assert mock_upd.called


# ═══════════════════════════════════════════════════════════════════════════════
# C: Guard pre-check exception — falls through to normal path
# ═══════════════════════════════════════════════════════════════════════════════

class TestResumeGuardExceptionFallthrough:

    def test_db_error_in_check_falls_through(self):
        """If the pre-check DB query raises, normal path is still attempted."""
        db = MagicMock()
        db.query.side_effect = Exception("db timeout")
        eus = ExecutionUnitService(db=db)
        # Normal path will also fail (db is broken), but should not raise
        with patch.object(eus, "update_status", return_value=False):
            result = eus.resume_execution_unit("eu-bad-db")
        assert result is False  # update_status returned False → normal failure

    def test_none_eu_in_check_falls_through(self):
        """If pre-check returns None (eu not found), normal path runs."""
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        eus = ExecutionUnitService(db=db)
        with patch.object(eus, "update_status", return_value=False) as mock_upd:
            eus.resume_execution_unit("eu-missing")
        assert mock_upd.called
