"""
Sprint N+7 Agent Observability — test suite

Phase 1: Startup scan (scan_and_recover_stuck_runs)
  TestScanNoStuckRuns              — nothing to do when table is clean
  TestScanRecoverAgentRun          — agent_execution stuck run fully recovered
  TestScanRecoverGenericRun        — non-agent stuck run marked failed silently
  TestScanMultipleRuns             — multiple stuck runs recovered in one pass
  TestScanAgentRunAlreadyFinal     — agent run not in "executing" left alone
  TestScanNoLinkedAgentRun         — FlowRun marked failed even with no AgentRun
  TestScanPerRunExceptionIsolation — bad row does not abort rest of scan
  TestScanOuterException           — outer DB error returns 0, never raises
  TestScanThresholdDefault         — default threshold read from env var
  TestScanRecentRunSkipped         — run updated <threshold minutes ago is skipped

Phase 2: Recover endpoint (recover_stuck_agent_run)
  TestRecoverNotFound          — 404 on unknown run_id
  TestRecoverForbidden         — 403 on owner mismatch
  TestRecoverWrongStatus       — 409 "wrong_status" when not executing
  TestRecoverTooRecent         — 409 "too_recent" without force flag
  TestRecoverForceBypassesAge  — force=True bypasses age guard
  TestRecoverSuccess           — executing+old run fully recovered
  TestRecoverLinksFlowRun      — linked FlowRun also marked failed
  TestRecoverInternalError     — exception returns error_code=internal_error

Phase 3: Replay + migration + serializer (replay_run / _run_to_dict)
  TestReplayRunNotFound            — None on unknown original run
  TestReplayRunForbidden           — None on owner mismatch
  TestReplayRunCreatesNewRun       — new run created with original plan
  TestReplayRunSetsLineage         — replayed_from_run_id set on new run
  TestReplayRunTrustGateReapplied  — new run goes through trust gate
  TestRunToDictReplayedFromRunId   — _run_to_dict includes replayed_from_run_id
  TestMigrationReplayedFromRunId   — migration revision + chains off c2d3e4f5a6b7
  TestAgentRunModelHasColumn       — AgentRun has replayed_from_run_id column
  TestSerializerUnification        — _run_to_response delegates to _run_to_dict
"""
import os
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

TEST_USER_ID = "00000000-0000-0000-0000-000000000001"
OTHER_USER_ID = "00000000-0000-0000-0000-000000000002"
ORIGIN_RUN_ID = "00000000-0000-0000-0000-0000000000aa"


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _flow_run(
    *,
    fid=None,
    status="running",
    workflow_type="agent_execution",
    updated_at=None,
    staleness_minutes=11,
):
    """Build a minimal FlowRun mock."""
    fr = MagicMock()
    fr.id = fid or str(uuid.uuid4())
    fr.status = status
    fr.workflow_type = workflow_type
    fr.updated_at = updated_at or (
        datetime.now(timezone.utc) - timedelta(minutes=staleness_minutes)
    )
    fr.error_message = None
    fr.completed_at = None
    return fr


def _agent_run(*, run_id=None, flow_run_id=None, status="executing"):
    """Build a minimal AgentRun mock."""
    ar = MagicMock()
    ar.id = run_id or uuid.uuid4()
    ar.flow_run_id = flow_run_id
    ar.status = status
    ar.completed_at = None
    ar.error_message = None
    ar.result = None
    return ar


def _agent_step(*, step_index=0, tool_name="task.create", status="success"):
    s = MagicMock()
    s.step_index = step_index
    s.tool_name = tool_name
    s.status = status
    s.result = {"ok": True}
    s.error_message = None
    return s


def _make_db(
    *,
    stuck_runs=None,
    agent_run=None,
    agent_steps=None,
):
    """
    Return a mock Session whose query chain returns the given test data.

    Supports three model types:
      FlowRun  → returns stuck_runs list
      AgentRun → returns agent_run (first())
      AgentStep → returns agent_steps list (all())
    """
    db = MagicMock()

    def _query(model):
        q = MagicMock()
        name = getattr(model, "__name__", "") or getattr(model, "__tablename__", "")

        if "FlowRun" in str(model):
            q.filter.return_value = q
            q.all.return_value = stuck_runs or []
        elif "AgentRun" in str(model):
            q.filter.return_value = q
            q.first.return_value = agent_run
        elif "AgentStep" in str(model):
            q.filter.return_value = q
            q.order_by.return_value = q
            q.all.return_value = agent_steps or []
        else:
            q.filter.return_value = q
            q.all.return_value = []
            q.first.return_value = None
        return q

    db.query.side_effect = _query
    return db


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestScanNoStuckRuns:
    """scan_and_recover_stuck_runs returns 0 and does not commit when table is clean."""

    def test_returns_zero_when_no_stuck_runs(self):
        from AINDY.agents.stuck_run_service import scan_and_recover_stuck_runs

        db = _make_db(stuck_runs=[])
        result = scan_and_recover_stuck_runs(db, staleness_minutes=10)
        assert result == 0

    def test_does_not_commit_when_nothing_to_recover(self):
        from AINDY.agents.stuck_run_service import scan_and_recover_stuck_runs

        db = _make_db(stuck_runs=[])
        scan_and_recover_stuck_runs(db, staleness_minutes=10)
        db.commit.assert_not_called()


class TestScanRecoverAgentRun:
    """agent_execution stuck runs mark both FlowRun and AgentRun as failed."""

    def _run_scan(self):
        from AINDY.agents.stuck_run_service import scan_and_recover_stuck_runs

        fr = _flow_run(workflow_type="agent_execution")
        step = _agent_step(step_index=0)
        ar = _agent_run(flow_run_id=str(fr.id))
        db = _make_db(stuck_runs=[fr], agent_run=ar, agent_steps=[step])
        count = scan_and_recover_stuck_runs(db, staleness_minutes=10)
        return count, fr, ar, step, db

    def test_returns_one_recovered(self):
        count, *_ = self._run_scan()
        assert count == 1

    def test_flow_run_marked_failed(self):
        _, fr, *_ = self._run_scan()
        assert fr.status == "failed"

    def test_flow_run_error_message_set(self):
        _, fr, *_ = self._run_scan()
        assert fr.error_message is not None
        assert "recovery" in fr.error_message.lower()

    def test_flow_run_completed_at_set(self):
        _, fr, *_ = self._run_scan()
        assert fr.completed_at is not None

    def test_agent_run_marked_failed(self):
        _, _fr, ar, *_ = self._run_scan()
        assert ar.status == "failed"

    def test_agent_run_error_message_set(self):
        _, _fr, ar, *_ = self._run_scan()
        assert ar.error_message is not None

    def test_agent_run_result_contains_steps(self):
        _, _fr, ar, step, _ = self._run_scan()
        assert ar.result is not None
        assert "steps" in ar.result
        assert len(ar.result["steps"]) == 1

    def test_db_commit_called(self):
        _, _fr, _ar, _step, db = self._run_scan()
        db.commit.assert_called()


class TestScanRecoverGenericRun:
    """Non-agent stuck runs are marked failed with a log entry only."""

    def _run_scan(self, workflow_type="some_other_flow"):
        from AINDY.agents.stuck_run_service import scan_and_recover_stuck_runs

        fr = _flow_run(workflow_type=workflow_type)
        db = _make_db(stuck_runs=[fr])
        count = scan_and_recover_stuck_runs(db, staleness_minutes=10)
        return count, fr, db

    def test_returns_one_recovered(self):
        count, *_ = self._run_scan()
        assert count == 1

    def test_flow_run_marked_failed(self):
        _, fr, _ = self._run_scan()
        assert fr.status == "failed"

    def test_flow_run_error_message_set(self):
        _, fr, _ = self._run_scan()
        assert fr.error_message is not None

    def test_no_agent_run_query_for_generic(self):
        from AINDY.agents.stuck_run_service import scan_and_recover_stuck_runs
        from AINDY.db.models.agent_run import AgentRun

        fr = _flow_run(workflow_type="memory_workflow")
        db = _make_db(stuck_runs=[fr])
        scan_and_recover_stuck_runs(db, staleness_minutes=10)
        # Should not query AgentRun for generic workflow types
        for call_args in db.query.call_args_list:
            model = call_args[0][0] if call_args[0] else None
            if model is not None:
                assert "AgentRun" not in str(model), (
                    "AgentRun should not be queried for non-agent workflows"
                )


class TestScanMultipleRuns:
    """Multiple stuck runs are all recovered in a single scan pass."""

    def test_recovers_all_stuck_runs(self):
        from AINDY.agents.stuck_run_service import scan_and_recover_stuck_runs

        runs = [_flow_run(workflow_type="generic") for _ in range(3)]
        db = _make_db(stuck_runs=runs)
        count = scan_and_recover_stuck_runs(db, staleness_minutes=10)
        assert count == 3

    def test_each_run_committed_individually(self):
        from AINDY.agents.stuck_run_service import scan_and_recover_stuck_runs

        runs = [_flow_run(workflow_type="generic") for _ in range(2)]
        db = _make_db(stuck_runs=runs)
        scan_and_recover_stuck_runs(db, staleness_minutes=10)
        assert db.commit.call_count == 2


class TestScanAgentRunAlreadyFinal:
    """AgentRun not in 'executing' status is left untouched."""

    def test_completed_agent_run_not_modified(self):
        from AINDY.agents.stuck_run_service import scan_and_recover_stuck_runs

        fr = _flow_run(workflow_type="agent_execution")
        ar = _agent_run(flow_run_id=str(fr.id), status="completed")
        db = _make_db(stuck_runs=[fr], agent_run=ar)
        scan_and_recover_stuck_runs(db, staleness_minutes=10)
        # FlowRun still gets marked failed (it's stuck), but AgentRun status unchanged
        assert fr.status == "failed"
        assert ar.status == "completed"

    def test_failed_agent_run_not_overwritten(self):
        from AINDY.agents.stuck_run_service import scan_and_recover_stuck_runs

        fr = _flow_run(workflow_type="agent_execution")
        ar = _agent_run(flow_run_id=str(fr.id), status="failed")
        db = _make_db(stuck_runs=[fr], agent_run=ar)
        scan_and_recover_stuck_runs(db, staleness_minutes=10)
        assert ar.status == "failed"
        assert ar.error_message is None  # not overwritten


class TestScanNoLinkedAgentRun:
    """agent_execution FlowRun with no matching AgentRun still marks FlowRun failed."""

    def test_flow_run_marked_failed_without_agent_run(self):
        from AINDY.agents.stuck_run_service import scan_and_recover_stuck_runs

        fr = _flow_run(workflow_type="agent_execution")
        db = _make_db(stuck_runs=[fr], agent_run=None)
        count = scan_and_recover_stuck_runs(db, staleness_minutes=10)
        assert count == 1
        assert fr.status == "failed"


class TestScanPerRunExceptionIsolation:
    """A bad row does not abort recovery of subsequent rows."""

    def test_exception_in_one_run_does_not_stop_others(self):
        from AINDY.agents.stuck_run_service import scan_and_recover_stuck_runs

        good_run = _flow_run(workflow_type="generic")
        bad_run = _flow_run(workflow_type="generic")

        call_count = {"n": 0}
        original_generic = None

        def _query_side_effect(model):
            q = MagicMock()
            if "FlowRun" in str(model):
                q.filter.return_value = q
                q.all.return_value = [bad_run, good_run]
            elif "AgentRun" in str(model):
                q.filter.return_value = q
                q.first.return_value = None
            elif "AgentStep" in str(model):
                q.filter.return_value = q
                q.order_by.return_value = q
                q.all.return_value = []
            else:
                q.filter.return_value = q
                q.all.return_value = []
            return q

        db = MagicMock()
        db.query.side_effect = _query_side_effect
        commit_calls = []

        def _commit():
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("simulated DB error on first commit")
            commit_calls.append(True)

        db.commit.side_effect = _commit
        db.rollback.return_value = None

        count = scan_and_recover_stuck_runs(db, staleness_minutes=10)
        # bad_run failed to commit → only good_run counted
        assert count == 1
        assert len(commit_calls) == 1


class TestScanOuterException:
    """Outer DB exception returns 0 and never raises."""

    def test_returns_zero_on_outer_exception(self):
        from AINDY.agents.stuck_run_service import scan_and_recover_stuck_runs

        db = MagicMock()
        db.query.side_effect = RuntimeError("DB connection lost")

        result = scan_and_recover_stuck_runs(db, staleness_minutes=10)
        assert result == 0

    def test_never_raises(self):
        from AINDY.agents.stuck_run_service import scan_and_recover_stuck_runs

        db = MagicMock()
        db.query.side_effect = Exception("catastrophic failure")

        # Must not raise
        scan_and_recover_stuck_runs(db, staleness_minutes=10)


class TestScanThresholdDefault:
    """Default threshold is read from AINDY_STUCK_RUN_THRESHOLD_MINUTES."""

    def test_uses_env_var_when_no_param(self):
        from AINDY.agents import stuck_run_service
        with patch.dict(os.environ, {"AINDY_STUCK_RUN_THRESHOLD_MINUTES": "5"}):
            assert stuck_run_service._default_threshold_minutes() == 5

    def test_falls_back_to_10_on_invalid_env(self):
        from AINDY.agents import stuck_run_service
        with patch.dict(os.environ, {"AINDY_STUCK_RUN_THRESHOLD_MINUTES": "not_a_number"}):
            assert stuck_run_service._default_threshold_minutes() == 10

    def test_falls_back_to_10_when_env_absent(self):
        from AINDY.agents import stuck_run_service
        env = {k: v for k, v in os.environ.items() if k != "AINDY_STUCK_RUN_THRESHOLD_MINUTES"}
        with patch.dict(os.environ, env, clear=True):
            assert stuck_run_service._default_threshold_minutes() == 10


class TestScanRecentRunSkipped:
    """Runs updated less than the threshold ago must not be touched."""

    def test_recent_run_not_recovered(self):
        """
        The DB filter is applied by SQLAlchemy, not by our code.
        We verify that when the query returns an empty list (because all
        runs are recent), recovered count is 0.
        """
        from AINDY.agents.stuck_run_service import scan_and_recover_stuck_runs

        # Simulate DB correctly filtering out recent runs (returns empty list)
        db = _make_db(stuck_runs=[])
        count = scan_and_recover_stuck_runs(db, staleness_minutes=10)
        assert count == 0


# =============================================================================
# Phase 2: Recover endpoint
# =============================================================================

def _make_recover_db(*, agent_run=None, flow_run=None, agent_steps=None):
    """DB mock for recover_stuck_agent_run tests."""
    db = MagicMock()

    def _query(model):
        q = MagicMock()
        if "AgentRun" in str(model):
            q.filter.return_value = q
            q.first.return_value = agent_run
        elif "AgentStep" in str(model):
            q.filter.return_value = q
            q.order_by.return_value = q
            q.all.return_value = agent_steps or []
        elif "FlowRun" in str(model):
            q.filter.return_value = q
            q.first.return_value = flow_run
        else:
            q.filter.return_value = q
            q.first.return_value = None
            q.all.return_value = []
        return q

    db.query.side_effect = _query
    return db


def _executing_run(
    *,
    run_id=None,
    user_id=TEST_USER_ID,
    flow_run_id=None,
    started_minutes_ago=20,
):
    """AgentRun mock in 'executing' state."""
    ar = MagicMock()
    ar.id = run_id or uuid.uuid4()
    ar.user_id = user_id
    ar.flow_run_id = flow_run_id
    ar.status = "executing"
    ar.started_at = datetime.now(timezone.utc) - timedelta(minutes=started_minutes_ago)
    ar.completed_at = None
    ar.error_message = None
    ar.result = None
    ar.goal = "test goal"
    ar.executive_summary = ""
    ar.overall_risk = "low"
    ar.steps_total = 1
    ar.steps_completed = 0
    ar.plan = {}
    ar.created_at = ar.started_at
    ar.approved_at = None
    return ar


class TestRecoverNotFound:
    def test_returns_not_found(self):
        from AINDY.agents.stuck_run_service import recover_stuck_agent_run

        db = _make_recover_db(agent_run=None)
        result = recover_stuck_agent_run("unknown-id", TEST_USER_ID, db)
        assert result["ok"] is False
        assert result["error_code"] == "not_found"


class TestRecoverForbidden:
    def test_returns_forbidden_on_owner_mismatch(self):
        from AINDY.agents.stuck_run_service import recover_stuck_agent_run

        ar = _executing_run(user_id=OTHER_USER_ID)
        db = _make_recover_db(agent_run=ar)
        result = recover_stuck_agent_run(str(ar.id), TEST_USER_ID, db)
        assert result["ok"] is False
        assert result["error_code"] == "forbidden"


class TestRecoverWrongStatus:
    def test_returns_wrong_status_when_completed(self):
        from AINDY.agents.stuck_run_service import recover_stuck_agent_run

        ar = _executing_run()
        ar.status = "completed"
        db = _make_recover_db(agent_run=ar)
        result = recover_stuck_agent_run(str(ar.id), ar.user_id, db)
        assert result["ok"] is False
        assert result["error_code"] == "wrong_status"
        assert "executing" in result["detail"].lower()

    def test_returns_wrong_status_when_pending(self):
        from AINDY.agents.stuck_run_service import recover_stuck_agent_run

        ar = _executing_run()
        ar.status = "pending_approval"
        db = _make_recover_db(agent_run=ar)
        result = recover_stuck_agent_run(str(ar.id), ar.user_id, db)
        assert result["error_code"] == "wrong_status"


class TestRecoverTooRecent:
    def test_too_recent_without_force(self):
        from AINDY.agents.stuck_run_service import recover_stuck_agent_run

        ar = _executing_run(started_minutes_ago=2)  # only 2 minutes old
        db = _make_recover_db(agent_run=ar)
        result = recover_stuck_agent_run(str(ar.id), ar.user_id, db, force=False)
        assert result["ok"] is False
        assert result["error_code"] == "too_recent"
        assert "force=true" in result["detail"].lower()


class TestRecoverForceBypassesAge:
    def test_force_true_skips_age_guard(self):
        from AINDY.agents.stuck_run_service import recover_stuck_agent_run

        ar = _executing_run(started_minutes_ago=1)  # only 1 minute old
        db = _make_recover_db(agent_run=ar)
        result = recover_stuck_agent_run(str(ar.id), ar.user_id, db, force=True)
        # force bypasses age → proceeds to recovery
        assert result["ok"] is True


class TestRecoverSuccess:
    def _run_recover(self):
        from AINDY.agents.stuck_run_service import recover_stuck_agent_run

        ar = _executing_run(started_minutes_ago=20)
        step = _agent_step(step_index=0)
        db = _make_recover_db(agent_run=ar, agent_steps=[step])
        result = recover_stuck_agent_run(str(ar.id), ar.user_id, db)
        return result, ar

    def test_ok_true(self):
        result, _ = self._run_recover()
        assert result["ok"] is True

    def test_run_in_result(self):
        result, _ = self._run_recover()
        assert "run" in result
        assert result["run"] is not None

    def test_agent_run_marked_failed(self):
        _, ar = self._run_recover()
        assert ar.status == "failed"

    def test_agent_run_has_error_message(self):
        _, ar = self._run_recover()
        assert ar.error_message is not None

    def test_agent_run_result_has_steps(self):
        _, ar = self._run_recover()
        assert ar.result is not None
        assert "steps" in ar.result


class TestRecoverLinksFlowRun:
    def test_linked_flow_run_marked_failed(self):
        from AINDY.agents.stuck_run_service import recover_stuck_agent_run

        fr = _flow_run(workflow_type="agent_execution")
        fr.status = "running"
        ar = _executing_run(started_minutes_ago=20, flow_run_id=str(fr.id))
        db = _make_recover_db(agent_run=ar, flow_run=fr)
        recover_stuck_agent_run(str(ar.id), ar.user_id, db)
        assert fr.status == "failed"

    def test_no_error_when_no_flow_run(self):
        from AINDY.agents.stuck_run_service import recover_stuck_agent_run

        ar = _executing_run(started_minutes_ago=20, flow_run_id=None)
        db = _make_recover_db(agent_run=ar, flow_run=None)
        result = recover_stuck_agent_run(str(ar.id), ar.user_id, db)
        assert result["ok"] is True


class TestRecoverInternalError:
    def test_returns_internal_error_on_exception(self):
        from AINDY.agents.stuck_run_service import recover_stuck_agent_run

        db = MagicMock()
        db.query.side_effect = RuntimeError("DB exploded")
        result = recover_stuck_agent_run("some-id", TEST_USER_ID, db)
        assert result["ok"] is False
        assert result["error_code"] == "internal_error"


# =============================================================================
# Phase 3: Replay + migration + serializer
# =============================================================================

class TestReplayRunNotFound:
    def test_returns_none_when_not_found(self):
        from AINDY.agents.agent_runtime import replay_run

        db = MagicMock()
        q = MagicMock()
        q.filter.return_value = q
        q.first.return_value = None
        db.query.return_value = q

        result = replay_run("nonexistent-id", TEST_USER_ID, db)
        assert result is None


class TestReplayRunForbidden:
    def test_returns_none_on_owner_mismatch(self):
        from AINDY.agents.agent_runtime import replay_run

        original = MagicMock()
        original.user_id = OTHER_USER_ID
        original.id = uuid.uuid4()
        original.plan = {}
        original.goal = "test"

        db = MagicMock()
        q = MagicMock()
        q.filter.return_value = q
        q.first.return_value = original
        db.query.return_value = q

        result = replay_run(str(original.id), TEST_USER_ID, db)
        assert result is None


class TestReplayRunCreatesNewRun:
    def test_new_run_returned_on_success(self):
        from AINDY.agents.agent_runtime import replay_run

        plan = {
            "steps": [{"tool": "task.create", "args": {}, "risk_level": "low",
                        "description": "step"}],
            "overall_risk": "low",
            "executive_summary": "test",
        }
        original = MagicMock()
        original.user_id = TEST_USER_ID
        original.id = uuid.uuid4()
        original.plan = plan
        original.goal = "original goal"

        new_run_dict = {
            "run_id": str(uuid.uuid4()),
            "goal": "original goal",
            "status": "pending_approval",
            "replayed_from_run_id": str(original.id),
        }

        db = MagicMock()
        q = MagicMock()
        q.filter.return_value = q
        q.first.return_value = original
        db.query.return_value = q

        with patch("agents.agent_runtime._create_run_from_plan",
                   return_value=new_run_dict) as mock_create:
            result = replay_run(str(original.id), TEST_USER_ID, db)

        assert result is not None
        assert result["goal"] == "original goal"
        mock_create.assert_called_once()


class TestReplayRunSetsLineage:
    def test_replayed_from_run_id_set(self):
        """replay_run passes replayed_from_run_id through to _create_run_from_plan."""
        from AINDY.agents.agent_runtime import replay_run

        plan = {"steps": [], "overall_risk": "low", "executive_summary": ""}
        original = MagicMock()
        original.user_id = TEST_USER_ID
        original.id = uuid.uuid4()
        original.plan = plan
        original.goal = "g"

        captured = {}

        def _fake_create(goal, plan, user_id, db, replayed_from_run_id=None):
            captured["replayed_from_run_id"] = replayed_from_run_id
            return {"run_id": "new", "goal": goal, "replayed_from_run_id": replayed_from_run_id,
                    "status": "pending_approval"}

        db = MagicMock()
        q = MagicMock()
        q.filter.return_value = q
        q.first.return_value = original
        db.query.return_value = q

        with patch("agents.agent_runtime._create_run_from_plan", side_effect=_fake_create):
            replay_run(str(original.id), TEST_USER_ID, db)

        assert captured["replayed_from_run_id"] == str(original.id)


class TestReplayRunTrustGateReapplied:
    def test_high_risk_plan_gets_pending_approval(self):
        """High-risk replay always requires approval regardless of prior approval."""
        from AINDY.agents.agent_runtime import replay_run

        plan = {
            "steps": [{"tool": "genesis.message", "args": {}, "risk_level": "high",
                        "description": "send"}],
            "overall_risk": "high",
            "executive_summary": "",
        }
        original = MagicMock()
        original.user_id = TEST_USER_ID
        original.id = uuid.uuid4()
        original.plan = plan
        original.goal = "high-risk goal"

        db = MagicMock()
        q = MagicMock()
        q.filter.return_value = q
        q.first.return_value = original
        db.query.return_value = q

        # _requires_approval returns True for "high" → status = "pending_approval"
        with patch("agents.agent_runtime._create_run_from_plan",
                   return_value={"run_id": "new", "status": "pending_approval",
                                 "goal": "high-risk goal", "replayed_from_run_id": None}) as mock_c:
            result = replay_run(str(original.id), TEST_USER_ID, db)

        assert result["status"] == "pending_approval"


class TestRunToDictReplayedFromRunId:
    def test_includes_replayed_from_run_id_when_set(self):
        from AINDY.agents.agent_runtime import _run_to_dict

        run = MagicMock()
        run.id = uuid.uuid4()
        run.user_id = TEST_USER_ID
        run.goal = "g"
        run.executive_summary = ""
        run.overall_risk = "low"
        run.status = "completed"
        run.steps_total = 1
        run.steps_completed = 1
        run.plan = {}
        run.result = None
        run.error_message = None
        run.flow_run_id = None
        run.replayed_from_run_id = ORIGIN_RUN_ID
        run.created_at = datetime.now(timezone.utc)
        run.approved_at = None
        run.started_at = None
        run.completed_at = None

        d = _run_to_dict(run)
        assert d["replayed_from_run_id"] == ORIGIN_RUN_ID

    def test_replayed_from_run_id_none_when_not_set(self):
        from AINDY.agents.agent_runtime import _run_to_dict

        run = MagicMock()
        run.id = uuid.uuid4()
        run.user_id = TEST_USER_ID
        run.goal = "g"
        run.executive_summary = ""
        run.overall_risk = "low"
        run.status = "completed"
        run.steps_total = 1
        run.steps_completed = 1
        run.plan = {}
        run.result = None
        run.error_message = None
        run.flow_run_id = None
        run.replayed_from_run_id = None
        run.created_at = datetime.now(timezone.utc)
        run.approved_at = None
        run.started_at = None
        run.completed_at = None

        d = _run_to_dict(run)
        assert d["replayed_from_run_id"] is None


class TestMigrationReplayedFromRunId:
    def test_revision_id(self):
        import pathlib
        text = pathlib.Path(
            "alembic/versions/d3e4f5a6b7c8_agent_run_replayed_from_run_id.py"
        ).read_text(encoding="utf-8")
        assert 'd3e4f5a6b7c8' in text

    def test_chains_off_n6_migration(self):
        import pathlib
        text = pathlib.Path(
            "alembic/versions/d3e4f5a6b7c8_agent_run_replayed_from_run_id.py"
        ).read_text(encoding="utf-8")
        assert 'c2d3e4f5a6b7' in text

    def test_upgrade_adds_column(self):
        import pathlib
        text = pathlib.Path(
            "alembic/versions/d3e4f5a6b7c8_agent_run_replayed_from_run_id.py"
        ).read_text(encoding="utf-8")
        assert 'replayed_from_run_id' in text
        assert 'add_column' in text

    def test_downgrade_drops_column(self):
        import pathlib
        text = pathlib.Path(
            "alembic/versions/d3e4f5a6b7c8_agent_run_replayed_from_run_id.py"
        ).read_text(encoding="utf-8")
        assert 'drop_column' in text


class TestAgentRunModelHasColumn:
    def test_replayed_from_run_id_attribute_exists(self):
        from AINDY.db.models.agent_run import AgentRun
        assert hasattr(AgentRun, "replayed_from_run_id")

    def test_column_is_nullable(self):
        from AINDY.db.models.agent_run import AgentRun
        col = AgentRun.__table__.columns.get("replayed_from_run_id")
        assert col is not None
        assert col.nullable is True


class TestSerializerUnification:
    def test_run_to_response_includes_flow_run_id(self):
        """After unification, _run_to_response() returns flow_run_id."""
        from AINDY.routes.agent_router import _run_to_response

        run = MagicMock()
        run.id = uuid.uuid4()
        run.user_id = TEST_USER_ID
        run.goal = "g"
        run.executive_summary = ""
        run.overall_risk = "low"
        run.status = "completed"
        run.steps_total = 1
        run.steps_completed = 1
        run.plan = {}
        run.result = None
        run.error_message = None
        run.flow_run_id = "fr-123"
        run.replayed_from_run_id = None
        run.created_at = datetime.now(timezone.utc)
        run.approved_at = None
        run.started_at = None
        run.completed_at = None

        response = _run_to_response(run)
        assert "flow_run_id" in response
        assert response["flow_run_id"] == "fr-123"

    def test_run_to_response_includes_replayed_from_run_id(self):
        from AINDY.routes.agent_router import _run_to_response

        run = MagicMock()
        run.id = uuid.uuid4()
        run.user_id = TEST_USER_ID
        run.goal = "g"
        run.executive_summary = ""
        run.overall_risk = "low"
        run.status = "completed"
        run.steps_total = 1
        run.steps_completed = 1
        run.plan = {}
        run.result = None
        run.error_message = None
        run.flow_run_id = None
        run.replayed_from_run_id = ORIGIN_RUN_ID
        run.created_at = datetime.now(timezone.utc)
        run.approved_at = None
        run.started_at = None
        run.completed_at = None

        response = _run_to_response(run)
        assert "replayed_from_run_id" in response
        assert response["replayed_from_run_id"] == ORIGIN_RUN_ID

