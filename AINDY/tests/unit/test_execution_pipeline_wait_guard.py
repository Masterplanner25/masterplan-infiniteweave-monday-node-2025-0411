"""
Tests for WAIT guard enforcement in ExecutionPipeline.

Every WAIT must have a traceable ExecutionUnit; otherwise execution is
permanently lost (no eu_id → scheduler can't resume; no db → can't persist).

_safe_transition_eu_waiting() now raises RuntimeError in both cases.
The two WAIT paths in run() must convert that error to a failure result:

  Path A — dict-based  (handler returns {"status": "WAITING"})
            → RuntimeError raised inside the outer try → caught by except Exception
            → ExecutionResult(success=False)

  Path B — raise-based (handler raises ExecutionWaitSignal)
            → caught by except ExecutionWaitSignal → inner try/except
            → ExecutionResult(success=False)

Groups
------
A  _safe_transition_eu_waiting() guard — unit (no I/O)
B  run() dict-based WAIT path — integration via AsyncMock
C  run() raise-based WAIT path — integration via AsyncMock
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from AINDY.core.execution_pipeline import ExecutionContext, ExecutionPipeline, ExecutionResult


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ctx(*, eu_id="eu-abc", db=None, user_id="u1", route="task.do_thing"):
    ctx = ExecutionContext(
        request_id="trace-001",
        route_name=route,
        user_id=user_id,
    )
    ctx.metadata["eu_id"] = eu_id
    ctx.metadata["db"] = db
    ctx.metadata["trace_id"] = "trace-001"
    return ctx


def _run_pipeline(handler_fn, *, eu_id="eu-abc", db=None, user_id="u1"):
    """Run the pipeline synchronously via asyncio.run()."""
    pipeline = ExecutionPipeline()
    ctx = _ctx(eu_id=eu_id, db=db, user_id=user_id)
    return asyncio.run(pipeline.run(ctx, handler_fn))


# ═══════════════════════════════════════════════════════════════════════════════
# A: _safe_transition_eu_waiting() guard — direct unit tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestWaitGuardDirect:

    def _call(self, *, eu_id, db):
        pipeline = ExecutionPipeline()
        ctx = _ctx(eu_id=eu_id, db=db)
        pipeline._safe_transition_eu_waiting(ctx, wait_for="some.event")

    def test_raises_when_eu_id_is_none(self):
        with pytest.raises(RuntimeError, match="eu_id is absent"):
            self._call(eu_id=None, db=MagicMock())

    def test_raises_when_eu_id_is_empty_string(self):
        with pytest.raises(RuntimeError, match="eu_id is absent"):
            self._call(eu_id="", db=MagicMock())

    def test_raises_when_db_is_none(self):
        with pytest.raises(RuntimeError, match="db session is absent"):
            self._call(eu_id="eu-1", db=None)

    def test_error_message_includes_route_name(self):
        pipeline = ExecutionPipeline()
        ctx = _ctx(eu_id=None, db=None, route="agent.run_plan")
        with pytest.raises(RuntimeError) as exc_info:
            pipeline._safe_transition_eu_waiting(ctx, wait_for="approval.received")
        assert "agent.run_plan" in str(exc_info.value)

    def test_error_message_includes_wait_for(self):
        pipeline = ExecutionPipeline()
        ctx = _ctx(eu_id=None, db=None)
        with pytest.raises(RuntimeError) as exc_info:
            pipeline._safe_transition_eu_waiting(ctx, wait_for="payment.confirmed")
        assert "payment.confirmed" in str(exc_info.value)

    def test_no_raise_when_both_present(self):
        """Guard passes — subsequent logic runs (may fail for other reasons)."""
        pipeline = ExecutionPipeline()
        mock_db = MagicMock()
        ctx = _ctx(eu_id="eu-ok", db=mock_db)
        # Inner logic will import and call services — patch them to be safe.
        with patch("core.execution_unit_service.ExecutionUnitService") as mock_eus, \
             patch("kernel.scheduler_engine.get_scheduler_engine"):
            mock_eus.return_value.update_status.return_value = True
            mock_eus.return_value.set_wait_condition.return_value = True
            # Should NOT raise
            pipeline._safe_transition_eu_waiting(ctx, wait_for="ok.event")


# ═══════════════════════════════════════════════════════════════════════════════
# B: run() — dict-based WAIT path (handler returns {"status": "WAITING"})
# ═══════════════════════════════════════════════════════════════════════════════

class TestDictBasedWaitGuard:
    """
    Handler returns {"status": "WAITING", "wait_for": "event"}.
    _detect_wait() fires → _safe_transition_eu_waiting() raises → except Exception
    → ExecutionResult(success=False).
    """

    def _waiting_handler(self, ctx):
        return {"status": "WAITING", "wait_for": "some.event"}

    def test_no_eu_id_returns_failure(self):
        result = _run_pipeline(self._waiting_handler, eu_id=None, db=None)
        assert result.success is False
        assert "eu_id is absent" in (result.error or "")

    def test_no_db_returns_failure(self):
        result = _run_pipeline(self._waiting_handler, eu_id="eu-x", db=None)
        assert result.success is False
        assert "db session is absent" in (result.error or "")

    def test_failure_status_code_is_500(self):
        result = _run_pipeline(self._waiting_handler, eu_id=None, db=None)
        assert result.success is False
        assert result.metadata.get("status_code") == 500

    def test_eu_status_not_set_to_waiting_on_guard_failure(self):
        """eu_status must not be 'waiting' when the guard fired."""
        result = _run_pipeline(self._waiting_handler, eu_id=None, db=None)
        assert result.eu_status != "waiting"

    def test_success_with_valid_context(self):
        """When eu_id and db present, WAIT transitions correctly."""
        mock_db = MagicMock()

        def handler(ctx):
            return {"status": "WAITING", "wait_for": "approval"}

        with patch("core.execution_unit_service.ExecutionUnitService") as mock_eus, \
             patch("kernel.scheduler_engine.get_scheduler_engine"), \
             patch("core.execution_pipeline.ExecutionPipeline._safe_emit_event", return_value=None), \
             patch("core.execution_pipeline.ExecutionPipeline._safe_require_eu"), \
             patch("core.execution_pipeline.ExecutionPipeline._safe_recall_memory_count", return_value=0):
            mock_eus.return_value.update_status.return_value = True
            mock_eus.return_value.set_wait_condition.return_value = True
            result = _run_pipeline(handler, eu_id="eu-ok", db=mock_db)

        assert result.success is True
        assert result.eu_status == "waiting"


# ═══════════════════════════════════════════════════════════════════════════════
# C: run() — raise-based WAIT path (handler raises ExecutionWaitSignal)
# ═══════════════════════════════════════════════════════════════════════════════

class TestRaiseBasedWaitGuard:
    """
    Handler raises ExecutionWaitSignal.
    except ExecutionWaitSignal → _safe_transition_eu_waiting() raises →
    inner try/except → ExecutionResult(success=False).
    """

    def _signal_handler(self, ctx):
        from AINDY.core.execution_gate import ExecutionWaitSignal
        raise ExecutionWaitSignal("payment.confirmed", resume_key="inv-123")

    def test_no_eu_id_returns_failure(self):
        result = _run_pipeline(self._signal_handler, eu_id=None, db=None)
        assert result.success is False
        assert "eu_id is absent" in (result.error or "")

    def test_no_db_returns_failure(self):
        result = _run_pipeline(self._signal_handler, eu_id="eu-x", db=None)
        assert result.success is False
        assert "db session is absent" in (result.error or "")

    def test_failure_status_code_is_500(self):
        result = _run_pipeline(self._signal_handler, eu_id=None, db=None)
        assert result.success is False
        assert result.metadata.get("status_code") == 500

    def test_eu_status_not_waiting_when_guard_fires(self):
        result = _run_pipeline(self._signal_handler, eu_id=None, db=None)
        assert result.eu_status != "waiting"

    def test_raises_signal_without_eu_does_not_propagate_unhandled(self):
        """
        The RuntimeError from the guard must NOT escape run() as an unhandled
        exception — it must always be converted to an ExecutionResult.
        """
        result = _run_pipeline(self._signal_handler, eu_id=None, db=None)
        # If we got here without an exception, run() swallowed it correctly.
        assert isinstance(result, ExecutionResult)

    def test_success_with_valid_context(self):
        """When eu_id and db present, raised ExecutionWaitSignal transitions correctly."""
        mock_db = MagicMock()

        def handler(ctx):
            from AINDY.core.execution_gate import ExecutionWaitSignal
            raise ExecutionWaitSignal("webhook.received")

        with patch("core.execution_unit_service.ExecutionUnitService") as mock_eus, \
             patch("kernel.scheduler_engine.get_scheduler_engine"), \
             patch("core.execution_pipeline.ExecutionPipeline._safe_emit_event", return_value=None), \
             patch("core.execution_pipeline.ExecutionPipeline._safe_require_eu"), \
             patch("core.execution_pipeline.ExecutionPipeline._safe_recall_memory_count", return_value=0):
            mock_eus.return_value.update_status.return_value = True
            mock_eus.return_value.set_wait_condition.return_value = True
            result = _run_pipeline(handler, eu_id="eu-ok", db=mock_db)

        assert result.success is True
        assert result.eu_status == "waiting"
