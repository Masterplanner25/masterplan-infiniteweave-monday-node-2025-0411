"""
Tests for core.flow_run_rehydration.rehydrate_waiting_flow_runs().

Groups
------
A  Happy path — FlowRuns are registered correctly
B  Idempotency / duplicate guard
C  Graceful degradation — missing fields, DB error, bad flow_name
D  Scheduler field mapping — tenant_id, priority, eu_id, correlation_id
E  Resume callback correctness — runner.resume() called, DB closed
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from core.flow_run_rehydration import rehydrate_waiting_flow_runs


# ── Helpers ───────────────────────────────────────────────────────────────────

_UNSET = object()


def _run(
    *,
    flow_name: str = "test_flow",
    waiting_for: str | None = "approval.granted",
    status: str = "waiting",
    workflow_type: str = "test",
    user_id=_UNSET,
    trace_id: str | None = None,
    state: dict | None = None,
    run_id: str | None = None,
):
    """Build a mock FlowRun.

    ``user_id=_UNSET``  → assign a fresh random UUID (most tests don't care).
    ``user_id=None``    → explicitly no user (tests the "system" fallback).
    """
    r = MagicMock()
    r.id = run_id or str(uuid.uuid4())
    r.flow_name = flow_name
    r.waiting_for = waiting_for
    r.status = status
    r.workflow_type = workflow_type
    r.user_id = uuid.uuid4() if user_id is _UNSET else user_id
    r.trace_id = trace_id or str(uuid.uuid4())
    r.state = state if state is not None else {}
    return r


def _eu_for(run_id: str, *, priority: str = "normal"):
    """Build a mock ExecutionUnit linked to *run_id*."""
    eu = MagicMock()
    eu.id = uuid.uuid4()
    eu.flow_run_id = run_id
    eu.priority = priority
    return eu


def _db_with(runs, eus=None):
    """Build a mock DB session returning *runs* on first query, *eus* on second."""
    db = MagicMock()
    eu_list = eus if eus is not None else []

    run_chain = MagicMock()
    run_chain.filter.return_value.all.return_value = runs

    eu_chain = MagicMock()
    eu_chain.filter.return_value.all.return_value = eu_list

    # First db.query() → FlowRun chain; second → ExecutionUnit chain.
    db.query.side_effect = [run_chain, eu_chain]
    return db


def _scheduler(*, already_waiting_ids=None):
    se = MagicMock()
    already = set(already_waiting_ids or [])
    se.waiting_for.side_effect = lambda run_id: run_id if run_id in already else None
    return se


# ═══════════════════════════════════════════════════════════════════════════════
# A: Happy path
# ═══════════════════════════════════════════════════════════════════════════════

class TestFlowRunRehydrateHappyPath:

    def test_single_waiting_run_is_registered(self):
        run = _run()
        db = _db_with([run])
        se = _scheduler()

        with patch("core.flow_run_rehydration.get_scheduler_engine", return_value=se):
            count = rehydrate_waiting_flow_runs(db)

        assert count == 1
        se.register_wait.assert_called_once()

    def test_register_wait_uses_correct_run_id(self):
        run = _run()
        db = _db_with([run])
        se = _scheduler()

        with patch("core.flow_run_rehydration.get_scheduler_engine", return_value=se):
            rehydrate_waiting_flow_runs(db)

        _, kwargs = se.register_wait.call_args
        assert kwargs["run_id"] == str(run.id)

    def test_register_wait_uses_waiting_for_as_event(self):
        run = _run(waiting_for="task.completed")
        db = _db_with([run])
        se = _scheduler()

        with patch("core.flow_run_rehydration.get_scheduler_engine", return_value=se):
            rehydrate_waiting_flow_runs(db)

        _, kwargs = se.register_wait.call_args
        assert kwargs["wait_for_event"] == "task.completed"

    def test_eu_type_is_always_flow(self):
        run = _run()
        db = _db_with([run])
        se = _scheduler()

        with patch("core.flow_run_rehydration.get_scheduler_engine", return_value=se):
            rehydrate_waiting_flow_runs(db)

        _, kwargs = se.register_wait.call_args
        assert kwargs["eu_type"] == "flow"

    def test_wait_condition_forwarded_with_correct_event(self):
        run = _run(waiting_for="payment.received")
        db = _db_with([run])
        se = _scheduler()

        with patch("core.flow_run_rehydration.get_scheduler_engine", return_value=se):
            rehydrate_waiting_flow_runs(db)

        _, kwargs = se.register_wait.call_args
        wc = kwargs["wait_condition"]
        assert wc is not None
        assert wc.event_name == "payment.received"

    def test_multiple_runs_all_registered(self):
        runs = [_run(waiting_for=f"evt.{i}") for i in range(5)]
        db = _db_with(runs)
        se = _scheduler()

        with patch("core.flow_run_rehydration.get_scheduler_engine", return_value=se):
            count = rehydrate_waiting_flow_runs(db)

        assert count == 5
        assert se.register_wait.call_count == 5

    def test_resume_callback_is_callable(self):
        run = _run()
        db = _db_with([run])
        se = _scheduler()

        with patch("core.flow_run_rehydration.get_scheduler_engine", return_value=se):
            rehydrate_waiting_flow_runs(db)

        _, kwargs = se.register_wait.call_args
        assert callable(kwargs["resume_callback"])

    def test_no_waiting_runs_returns_zero(self):
        db = _db_with([])
        se = _scheduler()

        with patch("core.flow_run_rehydration.get_scheduler_engine", return_value=se):
            count = rehydrate_waiting_flow_runs(db)

        assert count == 0
        se.register_wait.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════════
# B: Idempotency / duplicate guard
# ═══════════════════════════════════════════════════════════════════════════════

class TestFlowRunRehydrateIdempotency:

    def test_already_registered_run_is_skipped(self):
        run = _run()
        db = _db_with([run])
        se = _scheduler(already_waiting_ids=[str(run.id)])

        with patch("core.flow_run_rehydration.get_scheduler_engine", return_value=se):
            count = rehydrate_waiting_flow_runs(db)

        assert count == 0
        se.register_wait.assert_not_called()

    def test_partial_duplicate_skips_only_duplicate(self):
        run_fresh = _run(waiting_for="evt.a")
        run_dupe  = _run(waiting_for="evt.b")
        db = _db_with([run_fresh, run_dupe])
        se = _scheduler(already_waiting_ids=[str(run_dupe.id)])

        with patch("core.flow_run_rehydration.get_scheduler_engine", return_value=se):
            count = rehydrate_waiting_flow_runs(db)

        assert count == 1
        _, kwargs = se.register_wait.call_args
        assert kwargs["run_id"] == str(run_fresh.id)

    def test_calling_twice_is_safe(self):
        """Second call sees all runs already in registry and skips them."""
        run = _run()
        registered = set()

        def _fake_register(**kwargs):
            registered.add(kwargs["run_id"])

        def _fake_waiting_for(run_id):
            return run_id if run_id in registered else None

        se = MagicMock()
        se.register_wait.side_effect = _fake_register
        se.waiting_for.side_effect = _fake_waiting_for

        with patch("core.flow_run_rehydration.get_scheduler_engine", return_value=se):
            # First call: fresh DB mock
            db1 = _db_with([run])
            first = rehydrate_waiting_flow_runs(db1)
            # Second call: same run is now in registry
            db2 = _db_with([run])
            second = rehydrate_waiting_flow_runs(db2)

        assert first == 1
        assert second == 0

    # ── Coexistence: EU-level callback already registered ─────────────────────

    def test_registers_flow_run_even_when_eu_already_in_scheduler(self):
        """Guard 2 must PROCEED, not skip — both callbacks are complementary."""
        run = _run(waiting_for="ev")
        eu = _eu_for(str(run.id))
        db = _db_with([run], eus=[eu])

        # Simulate EU rehydration already registered _waiting[eu.id].
        # _waiting[flow_run.id] is NOT yet registered.
        eu_id_str = str(eu.id)
        se = MagicMock()
        se.waiting_for.side_effect = lambda rid: "ev" if rid == eu_id_str else None

        with patch("core.flow_run_rehydration.get_scheduler_engine", return_value=se):
            count = rehydrate_waiting_flow_runs(db)

        assert count == 1
        se.register_wait.assert_called_once()

    def test_register_call_uses_flow_run_id_not_eu_id(self):
        """FlowRun callback must be keyed on flow_run.id, not eu.id."""
        run = _run(waiting_for="ev")
        eu = _eu_for(str(run.id))
        db = _db_with([run], eus=[eu])

        se = MagicMock()
        se.waiting_for.return_value = None  # nothing registered yet

        with patch("core.flow_run_rehydration.get_scheduler_engine", return_value=se):
            rehydrate_waiting_flow_runs(db)

        kwargs = se.register_wait.call_args.kwargs
        assert kwargs["run_id"] == str(run.id)
        assert kwargs["run_id"] != str(eu.id)

    def test_flow_run_guard_does_not_fire_for_eu_id(self):
        """Guard 1 must only respond to flow_run.id being registered, not eu.id."""
        run = _run(waiting_for="ev")
        eu = _eu_for(str(run.id))
        db = _db_with([run], eus=[eu])

        eu_id_str = str(eu.id)
        run_id_str = str(run.id)

        # EU is registered, FlowRun is not.
        se = MagicMock()
        se.waiting_for.side_effect = lambda rid: "ev" if rid == eu_id_str else None

        with patch("core.flow_run_rehydration.get_scheduler_engine", return_value=se):
            count = rehydrate_waiting_flow_runs(db)

        # Must register (Guard 1 did not incorrectly block it)
        assert count == 1


# ═══════════════════════════════════════════════════════════════════════════════
# C: Graceful degradation
# ═══════════════════════════════════════════════════════════════════════════════

class TestFlowRunRehydrateDegradation:

    def test_run_without_waiting_for_is_skipped(self):
        run = _run(waiting_for=None)
        db = _db_with([run])
        se = _scheduler()

        with patch("core.flow_run_rehydration.get_scheduler_engine", return_value=se):
            count = rehydrate_waiting_flow_runs(db)

        assert count == 0
        se.register_wait.assert_not_called()

    def test_run_with_empty_waiting_for_is_skipped(self):
        run = _run(waiting_for="")
        db = _db_with([run])
        se = _scheduler()

        with patch("core.flow_run_rehydration.get_scheduler_engine", return_value=se):
            count = rehydrate_waiting_flow_runs(db)

        assert count == 0
        se.register_wait.assert_not_called()

    def test_db_query_error_returns_zero(self):
        db = MagicMock()
        db.query.side_effect = Exception("connection lost")
        se = _scheduler()

        with patch("core.flow_run_rehydration.get_scheduler_engine", return_value=se):
            count = rehydrate_waiting_flow_runs(db)

        assert count == 0
        se.register_wait.assert_not_called()

    def test_register_wait_error_does_not_abort_remaining_runs(self):
        run_bad  = _run(waiting_for="evt.a")
        run_good = _run(waiting_for="evt.b")
        db = _db_with([run_bad, run_good])
        se = _scheduler()
        se.register_wait.side_effect = [RuntimeError("quota exceeded"), None]

        with patch("core.flow_run_rehydration.get_scheduler_engine", return_value=se):
            count = rehydrate_waiting_flow_runs(db)

        assert count == 1  # run_good registered; run_bad skipped

    def test_eu_preload_failure_does_not_abort_rehydration(self):
        """If EU bulk query fails, runs are still registered with defaults."""
        run = _run()
        db = MagicMock()

        # First query (FlowRun) succeeds; second (ExecutionUnit) raises.
        run_chain = MagicMock()
        run_chain.filter.return_value.all.return_value = [run]
        eu_chain = MagicMock()
        eu_chain.filter.side_effect = Exception("eu query failed")
        db.query.side_effect = [run_chain, eu_chain]

        se = _scheduler()

        with patch("core.flow_run_rehydration.get_scheduler_engine", return_value=se):
            count = rehydrate_waiting_flow_runs(db)

        assert count == 1
        _, kwargs = se.register_wait.call_args
        assert kwargs["eu_id"] == ""       # fallback: no EU
        assert kwargs["priority"] == "normal"  # fallback default


# ═══════════════════════════════════════════════════════════════════════════════
# D: Scheduler field mapping
# ═══════════════════════════════════════════════════════════════════════════════

class TestFlowRunRehydrateFieldMapping:

    def test_tenant_id_derived_from_user_id(self):
        uid = uuid.uuid4()
        run = _run(user_id=uid)
        db = _db_with([run])
        se = _scheduler()

        with patch("core.flow_run_rehydration.get_scheduler_engine", return_value=se):
            rehydrate_waiting_flow_runs(db)

        _, kwargs = se.register_wait.call_args
        assert kwargs["tenant_id"] == str(uid)

    def test_system_fallback_when_user_id_is_none(self):
        run = _run(user_id=None)
        db = _db_with([run])
        se = _scheduler()

        with patch("core.flow_run_rehydration.get_scheduler_engine", return_value=se):
            rehydrate_waiting_flow_runs(db)

        _, kwargs = se.register_wait.call_args
        assert kwargs["tenant_id"] == "system"

    def test_eu_id_from_associated_execution_unit(self):
        run = _run()
        eu = _eu_for(str(run.id))
        db = _db_with([run], eus=[eu])
        se = _scheduler()

        with patch("core.flow_run_rehydration.get_scheduler_engine", return_value=se):
            rehydrate_waiting_flow_runs(db)

        _, kwargs = se.register_wait.call_args
        assert kwargs["eu_id"] == str(eu.id)

    def test_eu_id_empty_when_no_eu_found(self):
        run = _run()
        db = _db_with([run], eus=[])  # no EU for this run
        se = _scheduler()

        with patch("core.flow_run_rehydration.get_scheduler_engine", return_value=se):
            rehydrate_waiting_flow_runs(db)

        _, kwargs = se.register_wait.call_args
        assert kwargs["eu_id"] == ""

    def test_priority_from_eu_when_available(self):
        run = _run()
        eu = _eu_for(str(run.id), priority="high")
        db = _db_with([run], eus=[eu])
        se = _scheduler()

        with patch("core.flow_run_rehydration.get_scheduler_engine", return_value=se):
            rehydrate_waiting_flow_runs(db)

        _, kwargs = se.register_wait.call_args
        assert kwargs["priority"] == "high"

    def test_priority_defaults_to_normal_when_no_eu(self):
        run = _run()
        db = _db_with([run], eus=[])
        se = _scheduler()

        with patch("core.flow_run_rehydration.get_scheduler_engine", return_value=se):
            rehydrate_waiting_flow_runs(db)

        _, kwargs = se.register_wait.call_args
        assert kwargs["priority"] == "normal"

    def test_priority_defaults_to_normal_when_eu_priority_is_none(self):
        run = _run()
        eu = _eu_for(str(run.id), priority=None)
        eu.priority = None
        db = _db_with([run], eus=[eu])
        se = _scheduler()

        with patch("core.flow_run_rehydration.get_scheduler_engine", return_value=se):
            rehydrate_waiting_flow_runs(db)

        _, kwargs = se.register_wait.call_args
        assert kwargs["priority"] == "normal"

    def test_correlation_id_from_trace_id(self):
        run = _run(trace_id="trace-abc-123")
        db = _db_with([run])
        se = _scheduler()

        with patch("core.flow_run_rehydration.get_scheduler_engine", return_value=se):
            rehydrate_waiting_flow_runs(db)

        _, kwargs = se.register_wait.call_args
        assert kwargs["correlation_id"] == "trace-abc-123"

    def test_correlation_id_falls_back_to_run_id_when_no_trace(self):
        run = _run(trace_id=None)
        run.trace_id = None
        db = _db_with([run])
        se = _scheduler()

        with patch("core.flow_run_rehydration.get_scheduler_engine", return_value=se):
            rehydrate_waiting_flow_runs(db)

        _, kwargs = se.register_wait.call_args
        assert kwargs["correlation_id"] == str(run.id)

    def test_trace_id_forwarded_to_scheduler(self):
        run = _run(trace_id="trace-xyz")
        db = _db_with([run])
        se = _scheduler()

        with patch("core.flow_run_rehydration.get_scheduler_engine", return_value=se):
            rehydrate_waiting_flow_runs(db)

        _, kwargs = se.register_wait.call_args
        assert kwargs["trace_id"] == "trace-xyz"


# ═══════════════════════════════════════════════════════════════════════════════
# E: Resume callback correctness
# ═══════════════════════════════════════════════════════════════════════════════

class TestFlowRunRehydrateCallback:

    def _extract_callback(self, run, eus=None):
        db = _db_with([run], eus=eus or [])
        se = _scheduler()
        with patch("core.flow_run_rehydration.get_scheduler_engine", return_value=se):
            rehydrate_waiting_flow_runs(db)
        _, kwargs = se.register_wait.call_args
        return kwargs["resume_callback"]

    def test_callback_calls_runner_resume_with_run_id(self):
        run = _run(flow_name="test_flow")
        callback = self._extract_callback(run)

        mock_flow = {"start": "n", "edges": {}, "end": ["n"]}
        mock_runner = MagicMock()
        mock_session = MagicMock()

        with patch("db.database.SessionLocal", return_value=mock_session), \
             patch(
                 "runtime.flow_engine.FLOW_REGISTRY",
                 {"test_flow": mock_flow},
             ), \
             patch("runtime.flow_engine.PersistentFlowRunner", return_value=mock_runner):
            callback()

        mock_runner.resume.assert_called_once_with(str(run.id))

    def test_callback_closes_session_on_success(self):
        run = _run(flow_name="test_flow")
        callback = self._extract_callback(run)

        mock_flow = {"start": "n", "edges": {}, "end": ["n"]}
        mock_runner = MagicMock()
        mock_session = MagicMock()

        with patch("db.database.SessionLocal", return_value=mock_session), \
             patch("runtime.flow_engine.FLOW_REGISTRY", {"test_flow": mock_flow}), \
             patch("runtime.flow_engine.PersistentFlowRunner", return_value=mock_runner):
            callback()

        mock_session.close.assert_called_once()

    def test_callback_closes_session_on_runner_error(self):
        run = _run(flow_name="test_flow")
        callback = self._extract_callback(run)

        mock_flow = {"start": "n", "edges": {}, "end": ["n"]}
        mock_runner = MagicMock()
        mock_runner.resume.side_effect = RuntimeError("resume failed")
        mock_session = MagicMock()

        with patch("db.database.SessionLocal", return_value=mock_session), \
             patch("runtime.flow_engine.FLOW_REGISTRY", {"test_flow": mock_flow}), \
             patch("runtime.flow_engine.PersistentFlowRunner", return_value=mock_runner):
            callback()  # must not raise

        mock_session.close.assert_called_once()

    def test_callback_skips_resume_when_flow_not_in_registry(self):
        run = _run(flow_name="ghost_flow")
        callback = self._extract_callback(run)

        mock_session = MagicMock()

        with patch("db.database.SessionLocal", return_value=mock_session), \
             patch("runtime.flow_engine.FLOW_REGISTRY", {}), \
             patch("runtime.flow_engine.PersistentFlowRunner") as mock_runner_cls:
            callback()  # must not raise

        mock_runner_cls.assert_not_called()
        # Session is NOT opened when the flow lookup fails early
        mock_session.close.assert_not_called()

    def test_callback_passes_correct_user_id_to_runner(self):
        uid = uuid.uuid4()
        run = _run(flow_name="test_flow", user_id=uid)
        callback = self._extract_callback(run)

        mock_flow = {"start": "n", "edges": {}, "end": ["n"]}
        mock_session = MagicMock()
        runner_kwargs = {}

        def _capture_runner(*, flow, db, user_id, workflow_type, **kw):
            runner_kwargs["user_id"] = user_id
            return MagicMock()

        with patch("db.database.SessionLocal", return_value=mock_session), \
             patch("runtime.flow_engine.FLOW_REGISTRY", {"test_flow": mock_flow}), \
             patch("runtime.flow_engine.PersistentFlowRunner", side_effect=_capture_runner):
            callback()

        assert runner_kwargs["user_id"] == uid

    def test_callback_passes_workflow_type_to_runner(self):
        run = _run(flow_name="test_flow", workflow_type="arm_analysis")
        callback = self._extract_callback(run)

        mock_flow = {"start": "n", "edges": {}, "end": ["n"]}
        mock_session = MagicMock()
        runner_kwargs = {}

        def _capture_runner(*, flow, db, user_id, workflow_type, **kw):
            runner_kwargs["workflow_type"] = workflow_type
            return MagicMock()

        with patch("db.database.SessionLocal", return_value=mock_session), \
             patch("runtime.flow_engine.FLOW_REGISTRY", {"test_flow": mock_flow}), \
             patch("runtime.flow_engine.PersistentFlowRunner", side_effect=_capture_runner):
            callback()

        assert runner_kwargs["workflow_type"] == "arm_analysis"

    def test_callback_defaults_workflow_type_when_none(self):
        run = _run(flow_name="test_flow", workflow_type=None)
        run.workflow_type = None
        callback = self._extract_callback(run)

        mock_flow = {"start": "n", "edges": {}, "end": ["n"]}
        mock_session = MagicMock()
        runner_kwargs = {}

        def _capture_runner(*, flow, db, user_id, workflow_type, **kw):
            runner_kwargs["workflow_type"] = workflow_type
            return MagicMock()

        with patch("db.database.SessionLocal", return_value=mock_session), \
             patch("runtime.flow_engine.FLOW_REGISTRY", {"test_flow": mock_flow}), \
             patch("runtime.flow_engine.PersistentFlowRunner", side_effect=_capture_runner):
            callback()

        assert runner_kwargs["workflow_type"] == "flow"


# ═══════════════════════════════════════════════════════════════════════════════
# F: derive_wait_condition_from_flow — unit tests for the helper
# ═══════════════════════════════════════════════════════════════════════════════

class TestDeriveWaitCondition:
    """Direct tests for derive_wait_condition_from_flow()."""

    # ── Event-based ────────────────────────────────────────────────────────────

    def test_event_type_for_waiting_for(self):
        from core.flow_run_rehydration import derive_wait_condition_from_flow
        r = _run(waiting_for="plan.approved")
        wc = derive_wait_condition_from_flow(r)
        assert wc is not None
        assert wc.type == "event"

    def test_event_name_matches_waiting_for(self):
        from core.flow_run_rehydration import derive_wait_condition_from_flow
        r = _run(waiting_for="task.done")
        wc = derive_wait_condition_from_flow(r)
        assert wc.event_name == "task.done"

    def test_correlation_id_uses_trace_id(self):
        from core.flow_run_rehydration import derive_wait_condition_from_flow
        r = _run(waiting_for="x.event", trace_id="trace-foo")
        wc = derive_wait_condition_from_flow(r)
        assert wc.correlation_id == "trace-foo"

    def test_correlation_id_falls_back_to_run_id_when_no_trace(self):
        from core.flow_run_rehydration import derive_wait_condition_from_flow
        run_id = str(uuid.uuid4())
        r = _run(waiting_for="x.event", trace_id=None, run_id=run_id)
        r.trace_id = None
        wc = derive_wait_condition_from_flow(r)
        assert wc.correlation_id == run_id

    def test_event_beats_state_trigger(self):
        """waiting_for takes priority over state time fields."""
        from core.flow_run_rehydration import derive_wait_condition_from_flow
        r = _run(
            waiting_for="my.event",
            state={"trigger_at": "2099-01-01T00:00:00Z"},
        )
        wc = derive_wait_condition_from_flow(r)
        assert wc.type == "event"
        assert wc.event_name == "my.event"

    def test_trigger_at_is_none_for_event_condition(self):
        from core.flow_run_rehydration import derive_wait_condition_from_flow
        r = _run(waiting_for="plan.approved")
        wc = derive_wait_condition_from_flow(r)
        assert wc.trigger_at is None

    # ── Time-based ─────────────────────────────────────────────────────────────

    def test_time_type_from_trigger_at_key(self):
        from core.flow_run_rehydration import derive_wait_condition_from_flow
        r = _run(waiting_for=None, state={"trigger_at": "2099-06-15T12:00:00Z"})
        wc = derive_wait_condition_from_flow(r)
        assert wc is not None
        assert wc.type == "time"

    def test_time_type_from_wait_until_key(self):
        from core.flow_run_rehydration import derive_wait_condition_from_flow
        r = _run(waiting_for=None, state={"wait_until": "2099-06-15T12:00:00+00:00"})
        wc = derive_wait_condition_from_flow(r)
        assert wc is not None
        assert wc.type == "time"

    def test_trigger_at_parsed_as_utc_aware_datetime(self):
        from core.flow_run_rehydration import derive_wait_condition_from_flow
        from datetime import datetime
        r = _run(waiting_for=None, state={"trigger_at": "2099-06-15T12:00:00Z"})
        wc = derive_wait_condition_from_flow(r)
        assert isinstance(wc.trigger_at, datetime)
        assert wc.trigger_at.tzinfo is not None

    def test_trigger_at_key_wins_over_wait_until(self):
        from core.flow_run_rehydration import derive_wait_condition_from_flow
        r = _run(
            waiting_for=None,
            state={
                "trigger_at": "2099-01-01T00:00:00Z",
                "wait_until": "2099-12-31T00:00:00Z",
            },
        )
        wc = derive_wait_condition_from_flow(r)
        assert wc.trigger_at.month == 1  # trigger_at, not wait_until

    def test_event_name_none_for_time_condition(self):
        from core.flow_run_rehydration import derive_wait_condition_from_flow
        r = _run(waiting_for=None, state={"trigger_at": "2099-01-01T00:00:00Z"})
        wc = derive_wait_condition_from_flow(r)
        assert wc.event_name is None

    def test_correlation_id_set_for_time_condition(self):
        from core.flow_run_rehydration import derive_wait_condition_from_flow
        r = _run(waiting_for=None, trace_id="trace-bar", state={"trigger_at": "2099-01-01T00:00:00Z"})
        wc = derive_wait_condition_from_flow(r)
        assert wc.correlation_id == "trace-bar"

    # ── Returns None ───────────────────────────────────────────────────────────

    def test_returns_none_for_no_waiting_for_and_empty_state(self):
        from core.flow_run_rehydration import derive_wait_condition_from_flow
        r = _run(waiting_for=None, state={})
        assert derive_wait_condition_from_flow(r) is None

    def test_returns_none_for_no_waiting_for_and_null_state(self):
        from core.flow_run_rehydration import derive_wait_condition_from_flow
        r = _run(waiting_for=None, state=None)
        assert derive_wait_condition_from_flow(r) is None

    def test_returns_none_for_unparseable_trigger_at(self):
        from core.flow_run_rehydration import derive_wait_condition_from_flow
        r = _run(waiting_for=None, state={"trigger_at": "not-a-date"})
        assert derive_wait_condition_from_flow(r) is None

    def test_returns_none_for_empty_waiting_for_string(self):
        from core.flow_run_rehydration import derive_wait_condition_from_flow
        r = _run(waiting_for="", state={})
        assert derive_wait_condition_from_flow(r) is None

    def test_non_dict_state_does_not_crash(self):
        """state might be a stale string from old serialization — must not raise."""
        from core.flow_run_rehydration import derive_wait_condition_from_flow
        r = _run(waiting_for=None)
        r.state = "legacy string"
        assert derive_wait_condition_from_flow(r) is None


# ═══════════════════════════════════════════════════════════════════════════════
# G: Callback ordering — FlowRun claim gates EU resume and flow execution
# ═══════════════════════════════════════════════════════════════════════════════

class TestFlowRunCallbackOrdering:
    """
    The FlowRun callback must enforce the ordering:
      1. FlowRun atomic claim
      2. EU status transition  (only if claim won)
      3. Flow execution        (only if claim won)
    """

    _MOCK_FLOW = {"start": "n", "edges": {}, "end": ["n"]}

    def _extract_callback(self, run, eu=None):
        """Return the registered resume_callback from rehydrate_waiting_flow_runs."""
        db = _db_with([run], eus=[eu] if eu else [])
        se = _scheduler()
        with patch("core.flow_run_rehydration.get_scheduler_engine", return_value=se):
            rehydrate_waiting_flow_runs(db)
        _, kwargs = se.register_wait.call_args
        return kwargs["resume_callback"]

    def _call_callback(
        self,
        callback,
        *,
        update_rowcount: int = 1,
        commit_raises: Exception | None = None,
        flow_name: str = "test_flow",
    ):
        """
        Invoke *callback* with mocked session, FLOW_REGISTRY, EU service, and
        PersistentFlowRunner.  Returns (mock_eu_svc, mock_runner).
        """
        mock_session = MagicMock()
        # The claim UPDATE chain: query().filter().update() → rowcount
        mock_session.query.return_value.filter.return_value.update.return_value = (
            update_rowcount
        )
        if commit_raises:
            mock_session.commit.side_effect = commit_raises

        mock_eu_svc = MagicMock()
        mock_runner = MagicMock()

        with (
            patch("db.database.SessionLocal", return_value=mock_session),
            patch("runtime.flow_engine.FLOW_REGISTRY", {flow_name: self._MOCK_FLOW}),
            patch("runtime.flow_engine.PersistentFlowRunner", return_value=mock_runner),
            patch(
                "core.execution_unit_service.ExecutionUnitService",
                return_value=mock_eu_svc,
            ),
        ):
            callback()

        return mock_eu_svc, mock_runner

    # ── Claim win ─────────────────────────────────────────────────────────────

    def test_claim_win_calls_runner_resume(self):
        """When claim wins (rowcount=1), runner.resume() must be called."""
        run = _run(flow_name="test_flow")
        cb = self._extract_callback(run)
        _, mock_runner = self._call_callback(cb, update_rowcount=1)
        mock_runner.resume.assert_called_once_with(str(run.id))

    def test_claim_win_calls_eu_service_when_eu_id_present(self):
        """When claim wins AND eu_id is non-empty, EU service is called."""
        run = _run(flow_name="test_flow")
        eu = _eu_for(str(run.id))
        cb = self._extract_callback(run, eu=eu)
        mock_eu_svc, _ = self._call_callback(cb, update_rowcount=1)
        mock_eu_svc.resume_execution_unit.assert_called_once()

    def test_claim_win_eu_called_before_runner(self):
        """EU resume must be called before runner.resume() (ordering guarantee)."""
        run = _run(flow_name="test_flow")
        eu = _eu_for(str(run.id))
        cb = self._extract_callback(run, eu=eu)

        call_order = []
        mock_eu_svc = MagicMock()
        mock_eu_svc.resume_execution_unit.side_effect = lambda _: call_order.append("eu")
        mock_runner = MagicMock()
        mock_runner.resume.side_effect = lambda _: call_order.append("runner")

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.update.return_value = 1

        with (
            patch("db.database.SessionLocal", return_value=mock_session),
            patch("runtime.flow_engine.FLOW_REGISTRY", {"test_flow": self._MOCK_FLOW}),
            patch("runtime.flow_engine.PersistentFlowRunner", return_value=mock_runner),
            patch(
                "core.execution_unit_service.ExecutionUnitService",
                return_value=mock_eu_svc,
            ),
        ):
            cb()

        assert call_order == ["eu", "runner"], (
            f"Expected EU before runner, got: {call_order}"
        )

    # ── Claim loss ────────────────────────────────────────────────────────────

    def test_claim_loss_skips_runner_resume(self):
        """When claim fails (rowcount=0), runner.resume() must NOT be called."""
        run = _run(flow_name="test_flow")
        cb = self._extract_callback(run)
        _, mock_runner = self._call_callback(cb, update_rowcount=0)
        mock_runner.resume.assert_not_called()

    def test_claim_loss_skips_eu_service(self):
        """When claim fails (rowcount=0), EU status transition must NOT happen."""
        run = _run(flow_name="test_flow")
        eu = _eu_for(str(run.id))
        cb = self._extract_callback(run, eu=eu)
        mock_eu_svc, _ = self._call_callback(cb, update_rowcount=0)
        mock_eu_svc.resume_execution_unit.assert_not_called()

    def test_claim_commit_failure_skips_eu_and_runner(self):
        """If the claim commit raises, both EU resume and runner are skipped."""
        run = _run(flow_name="test_flow")
        eu = _eu_for(str(run.id))
        cb = self._extract_callback(run, eu=eu)
        mock_eu_svc, mock_runner = self._call_callback(
            cb, commit_raises=Exception("DB timeout")
        )
        mock_eu_svc.resume_execution_unit.assert_not_called()
        mock_runner.resume.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════════
# H: wait_rehydration.py — FlowRun ownership guard on EU callback
# ═══════════════════════════════════════════════════════════════════════════════

class TestEuCallbackFlowRunOwnershipGuard:
    """
    The EU callback in wait_rehydration must skip EU transition when the
    FlowRun that owns the EU has already been claimed by another instance.
    """

    def _extract_eu_callback(self, flow_run_id: str | None):
        """Return the registered resume_callback from rehydrate_waiting_eus()."""
        from core.wait_rehydration import rehydrate_waiting_eus

        eu = MagicMock()
        eu.id = str(uuid.uuid4())
        eu.status = "waiting"
        eu.wait_condition = {"type": "event", "event_name": "some.event"}
        eu.flow_run_id = flow_run_id
        eu.tenant_id = str(uuid.uuid4())
        eu.user_id = None
        eu.priority = "normal"
        eu.correlation_id = None
        eu.type = "flow"

        db = MagicMock()
        db.query.return_value.filter.return_value.all.return_value = [eu]

        se = MagicMock()
        se.waiting_for.return_value = None

        with patch("core.wait_rehydration.get_scheduler_engine", return_value=se):
            rehydrate_waiting_eus(db)

        _, kwargs = se.register_wait.call_args
        return kwargs["resume_callback"]

    def _call_with_flow_run_status(self, flow_run_status: str | None, flow_run_id: str):
        """
        Invoke the EU callback with a mock DB that returns a FlowRun with the
        given status (None → FlowRun row not found in DB).
        """
        callback = self._extract_eu_callback(flow_run_id)

        mock_db = MagicMock()
        mock_eu_service = MagicMock()

        fr_mock = MagicMock()
        fr_mock.status = flow_run_status or "waiting"
        mock_db.query.return_value.filter.return_value.first.return_value = (
            fr_mock if flow_run_status is not None else None
        )

        with (
            patch("db.database.SessionLocal", return_value=mock_db),
            patch(
                "core.execution_unit_service.ExecutionUnitService",
                return_value=mock_eu_service,
            ),
        ):
            callback()

        return mock_eu_service

    def test_eu_transition_skipped_when_flow_run_already_executing(self):
        """FlowRun status='executing' → another instance won → skip EU."""
        frid = str(uuid.uuid4())
        svc = self._call_with_flow_run_status("executing", frid)
        svc.resume_execution_unit.assert_not_called()

    def test_eu_transition_skipped_when_flow_run_completed(self):
        """FlowRun status='completed' → already done → skip EU."""
        frid = str(uuid.uuid4())
        svc = self._call_with_flow_run_status("completed", frid)
        svc.resume_execution_unit.assert_not_called()

    def test_eu_transition_skipped_when_flow_run_failed(self):
        """FlowRun status='failed' → not resumable → skip EU."""
        frid = str(uuid.uuid4())
        svc = self._call_with_flow_run_status("failed", frid)
        svc.resume_execution_unit.assert_not_called()

    def test_eu_transition_proceeds_when_flow_run_still_waiting(self):
        """FlowRun status='waiting' → race not yet resolved → EU proceeds."""
        frid = str(uuid.uuid4())
        svc = self._call_with_flow_run_status("waiting", frid)
        svc.resume_execution_unit.assert_called_once()

    def test_eu_transition_proceeds_when_no_flow_run_found(self):
        """FlowRun row not found (orphan EU) → guard cannot block → EU proceeds."""
        frid = str(uuid.uuid4())
        svc = self._call_with_flow_run_status(None, frid)
        svc.resume_execution_unit.assert_called_once()

    def test_eu_transition_proceeds_when_no_flow_run_id(self):
        """Standalone EU (no flow_run_id) → no FlowRun query, EU proceeds."""
        callback = self._extract_eu_callback(flow_run_id=None)

        mock_db = MagicMock()
        mock_eu_service = MagicMock()

        with (
            patch("db.database.SessionLocal", return_value=mock_db),
            patch(
                "core.execution_unit_service.ExecutionUnitService",
                return_value=mock_eu_service,
            ),
        ):
            callback()

        mock_db.query.assert_not_called()
        mock_eu_service.resume_execution_unit.assert_called_once()
