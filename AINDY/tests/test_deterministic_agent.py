"""
Deterministic Agent Tests — Sprint N+6

Phase 1: DB column + migration
  - AgentRun.flow_run_id column exists and is nullable
  - Migration file chains off b1c2d3e4f5a6 and adds flow_run_id

Phase 2: NodusAgentAdapter nodes
  - agent_validate_steps: success with steps / failure with empty plan
  - agent_execute_step: success path, retry for low/medium, no-retry for high
  - agent_execute_step: exhausted retries → FAILURE
  - agent_execute_step: persists AgentStep row and updates progress counters
  - agent_finalize_run: marks AgentRun completed, writes step_results

Phase 3: Flow graph structure
  - AGENT_FLOW keys present, start/end correct
  - _more_steps conditional edge logic

Phase 4: execute_with_flow integration
  - Successful run → AgentRun.status = "completed", flow_run_id linked
  - Failed run (step FAILURE) → AgentRun.status = "failed"
  - Empty plan → validates to FAILURE

Phase 5: execute_run delegates to adapter
  - execute_run wires "executing" then calls adapter
  - run dict includes flow_run_id key
"""
import pathlib
import time
from datetime import datetime, timezone
from unittest.mock import MagicMock, call, patch

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# Phase 1 — DB column
# ─────────────────────────────────────────────────────────────────────────────

class TestAgentRunFlowRunIdColumn:

    def test_flow_run_id_column_exists(self):
        from db.models.agent_run import AgentRun
        cols = {c.name for c in AgentRun.__table__.columns}
        assert "flow_run_id" in cols, "AgentRun must have flow_run_id column"

    def test_flow_run_id_is_nullable(self):
        from db.models.agent_run import AgentRun
        col = AgentRun.__table__.columns["flow_run_id"]
        assert col.nullable is True, "flow_run_id must be nullable for backward-compatibility"

    def test_flow_run_id_column_type_is_string(self):
        from db.models.agent_run import AgentRun
        from sqlalchemy import String
        col = AgentRun.__table__.columns["flow_run_id"]
        assert isinstance(col.type, String)

    def test_existing_columns_still_present(self):
        """Regression: adding flow_run_id must not remove any existing column."""
        from db.models.agent_run import AgentRun
        cols = {c.name for c in AgentRun.__table__.columns}
        required = {
            "id", "user_id", "goal", "plan", "executive_summary",
            "overall_risk", "status", "steps_total", "steps_completed",
            "current_step", "result", "error_message",
            "created_at", "approved_at", "started_at", "completed_at",
        }
        assert required.issubset(cols)


class TestAgentRunFlowRunIdMigration:

    def _migration_path(self):
        here = pathlib.Path(__file__).parent.parent
        return here / "alembic" / "versions" / "c2d3e4f5a6b7_agent_run_flow_run_id.py"

    def test_migration_file_exists(self):
        assert self._migration_path().exists(), "Migration file must exist"

    def test_revision_id(self):
        src = self._migration_path().read_text(encoding="utf-8")
        assert 'revision: str = "c2d3e4f5a6b7"' in src

    def test_down_revision_chains_off_watcher_signal_user_id(self):
        src = self._migration_path().read_text(encoding="utf-8")
        assert "b1c2d3e4f5a6" in src, "Must chain off b1c2d3e4f5a6 (WatcherSignal user_id)"

    def test_upgrade_adds_flow_run_id(self):
        src = self._migration_path().read_text(encoding="utf-8")
        assert "flow_run_id" in src
        assert "def upgrade" in src

    def test_downgrade_drops_flow_run_id(self):
        src = self._migration_path().read_text(encoding="utf-8")
        assert "def downgrade" in src
        assert "flow_run_id" in src


# ─────────────────────────────────────────────────────────────────────────────
# Phase 2 — Node: agent_validate_steps
# ─────────────────────────────────────────────────────────────────────────────

class TestAgentValidateStepsNode:

    def _call(self, state, context=None):
        from services.nodus_adapter import agent_validate_steps
        return agent_validate_steps(state, context or {})

    def test_success_with_steps(self):
        result = self._call({
            "agent_run_id": "run-1",
            "user_id": "u1",
            "steps": [{"tool": "task.create", "args": {}}],
        })
        assert result["status"] == "SUCCESS"

    def test_success_initialises_current_step_index(self):
        result = self._call({
            "agent_run_id": "run-1",
            "user_id": "u1",
            "steps": [{"tool": "task.create", "args": {}}],
        })
        assert result["output_patch"]["current_step_index"] == 0

    def test_success_initialises_step_results_empty(self):
        result = self._call({
            "agent_run_id": "run-1",
            "user_id": "u1",
            "steps": [{"tool": "task.create", "args": {}}],
        })
        assert result["output_patch"]["step_results"] == []

    def test_failure_when_no_steps(self):
        result = self._call({
            "agent_run_id": "run-1",
            "user_id": "u1",
            "steps": [],
        })
        assert result["status"] == "FAILURE"

    def test_failure_when_steps_key_missing(self):
        result = self._call({"agent_run_id": "run-1", "user_id": "u1"})
        assert result["status"] == "FAILURE"

    def test_failure_includes_error_message(self):
        result = self._call({"agent_run_id": "run-1", "user_id": "u1", "steps": []})
        assert "error" in result
        assert result["error"]

    def test_multiple_steps_accepted(self):
        result = self._call({
            "agent_run_id": "run-1",
            "user_id": "u1",
            "steps": [
                {"tool": "task.create", "args": {}},
                {"tool": "memory.recall", "args": {}},
                {"tool": "arm.analyze", "args": {}},
            ],
        })
        assert result["status"] == "SUCCESS"


# ─────────────────────────────────────────────────────────────────────────────
# Phase 2 — Node: agent_execute_step
# ─────────────────────────────────────────────────────────────────────────────

def _make_db_mock(run_id="run-1"):
    """Build a minimal SQLAlchemy session mock for node tests."""
    db = MagicMock()
    mock_run = MagicMock()
    mock_run.id = run_id
    mock_run.steps_completed = 0
    mock_run.current_step = 0
    db.query.return_value.filter.return_value.first.return_value = mock_run
    return db, mock_run


def _step_state(
    idx=0,
    tool="task.create",
    risk="low",
    step_results=None,
    extra_steps=None,
):
    """Build a minimal state dict for agent_execute_step tests."""
    steps = [{"tool": tool, "args": {"name": "T"}, "risk_level": risk, "description": "d"}]
    if extra_steps:
        steps.extend(extra_steps)
    return {
        "agent_run_id": "run-1",
        "user_id": "u1",
        "steps": steps,
        "current_step_index": idx,
        "step_results": step_results or [],
    }


class TestAgentExecuteStepNodeSuccess:

    def test_returns_success_on_tool_success(self):
        db, _ = _make_db_mock()
        state = _step_state()
        with patch("services.nodus_adapter.execute_tool", return_value={"success": True, "result": {"ok": 1}}):
            from services.nodus_adapter import agent_execute_step
            result = agent_execute_step(state, {"db": db})
        assert result["status"] == "SUCCESS"

    def test_increments_current_step_index(self):
        db, _ = _make_db_mock()
        state = _step_state(idx=0)
        with patch("services.nodus_adapter.execute_tool", return_value={"success": True, "result": {}}):
            from services.nodus_adapter import agent_execute_step
            result = agent_execute_step(state, {"db": db})
        assert result["output_patch"]["current_step_index"] == 1

    def test_appends_to_step_results(self):
        db, _ = _make_db_mock()
        state = _step_state(idx=0)
        with patch("services.nodus_adapter.execute_tool", return_value={"success": True, "result": {"r": 1}}):
            from services.nodus_adapter import agent_execute_step
            result = agent_execute_step(state, {"db": db})
        results = result["output_patch"]["step_results"]
        assert len(results) == 1
        assert results[0]["tool"] == "task.create"
        assert results[0]["status"] == "success"

    def test_persists_agent_step_row(self):
        db, _ = _make_db_mock()
        state = _step_state()
        with patch("services.nodus_adapter.execute_tool", return_value={"success": True, "result": {}}):
            from services.nodus_adapter import agent_execute_step
            agent_execute_step(state, {"db": db})
        db.add.assert_called_once()
        db.commit.assert_called()

    def test_updates_progress_counters(self):
        db, mock_run = _make_db_mock()
        # idx=0 with 3 steps so the guard doesn't fire; after execution idx→1
        state = _step_state(
            idx=0,
            extra_steps=[
                {"tool": "memory.recall", "args": {}, "risk_level": "low", "description": ""},
                {"tool": "arm.analyze", "args": {}, "risk_level": "medium", "description": ""},
            ],
        )
        with patch("services.nodus_adapter.execute_tool", return_value={"success": True, "result": {}}):
            from services.nodus_adapter import agent_execute_step
            agent_execute_step(state, {"db": db})
        assert mock_run.steps_completed == 1
        assert mock_run.current_step == 1

    def test_index_beyond_steps_returns_success_noop(self):
        """Guard: if called past end of steps, return SUCCESS with empty patch."""
        db, _ = _make_db_mock()
        state = _step_state(idx=99)
        from services.nodus_adapter import agent_execute_step
        result = agent_execute_step(state, {"db": db})
        assert result["status"] == "SUCCESS"
        assert result["output_patch"] == {}


class TestAgentExecuteStepRetry:

    def test_low_risk_retries_on_failure(self):
        db, _ = _make_db_mock()
        state = _step_state(risk="low")
        # Fail twice, succeed on third
        side_effects = [
            {"success": False, "error": "transient"},
            {"success": False, "error": "transient"},
            {"success": True, "result": {}},
        ]
        with patch("services.nodus_adapter.execute_tool", side_effect=side_effects) as mock_tool:
            from services.nodus_adapter import agent_execute_step
            result = agent_execute_step(state, {"db": db})
        assert result["status"] == "SUCCESS"
        assert mock_tool.call_count == 3

    def test_medium_risk_retries_on_failure(self):
        db, _ = _make_db_mock()
        state = _step_state(tool="arm.analyze", risk="medium")
        side_effects = [
            {"success": False, "error": "err"},
            {"success": True, "result": {}},
        ]
        with patch("services.nodus_adapter.execute_tool", side_effect=side_effects) as mock_tool:
            from services.nodus_adapter import agent_execute_step
            result = agent_execute_step(state, {"db": db})
        assert result["status"] == "SUCCESS"
        assert mock_tool.call_count == 2

    def test_low_risk_exhausted_retries_returns_failure(self):
        db, _ = _make_db_mock()
        state = _step_state(risk="low")
        fail = {"success": False, "error": "permanent"}
        with patch("services.nodus_adapter.execute_tool", return_value=fail) as mock_tool:
            from services.nodus_adapter import agent_execute_step
            from services.nodus_adapter import MAX_STEP_RETRIES
            result = agent_execute_step(state, {"db": db})
        assert result["status"] == "FAILURE"
        assert mock_tool.call_count == MAX_STEP_RETRIES

    def test_medium_risk_exhausted_retries_returns_failure(self):
        db, _ = _make_db_mock()
        state = _step_state(tool="task.complete", risk="medium")
        fail = {"success": False, "error": "permanent"}
        with patch("services.nodus_adapter.execute_tool", return_value=fail):
            from services.nodus_adapter import agent_execute_step
            result = agent_execute_step(state, {"db": db})
        assert result["status"] == "FAILURE"

    def test_failure_result_includes_error(self):
        db, _ = _make_db_mock()
        state = _step_state(risk="low")
        with patch("services.nodus_adapter.execute_tool", return_value={"success": False, "error": "boom"}):
            from services.nodus_adapter import agent_execute_step
            result = agent_execute_step(state, {"db": db})
        assert "error" in result
        assert "boom" in result["error"]


class TestAgentExecuteStepHighRiskNoRetry:

    def test_high_risk_fails_immediately_no_retry(self):
        """genesis.message must not be auto-retried."""
        db, _ = _make_db_mock()
        state = _step_state(tool="genesis.message", risk="high")
        fail = {"success": False, "error": "denied"}
        with patch("services.nodus_adapter.execute_tool", return_value=fail) as mock_tool:
            from services.nodus_adapter import agent_execute_step
            result = agent_execute_step(state, {"db": db})
        assert result["status"] == "FAILURE"
        assert mock_tool.call_count == 1, "High-risk must halt after exactly 1 attempt"

    def test_high_risk_success_on_first_attempt(self):
        db, _ = _make_db_mock()
        state = _step_state(tool="genesis.message", risk="high")
        with patch("services.nodus_adapter.execute_tool", return_value={"success": True, "result": {}}):
            from services.nodus_adapter import agent_execute_step
            result = agent_execute_step(state, {"db": db})
        assert result["status"] == "SUCCESS"

    def test_high_risk_step_result_has_failed_status(self):
        db, _ = _make_db_mock()
        state = _step_state(tool="genesis.message", risk="high")
        with patch("services.nodus_adapter.execute_tool", return_value={"success": False, "error": "e"}):
            from services.nodus_adapter import agent_execute_step
            result = agent_execute_step(state, {"db": db})
        # The step_results in output_patch should record "failed"
        step_results = result.get("output_patch", {}).get("step_results", [])
        if step_results:
            assert step_results[0]["status"] == "failed"


# ─────────────────────────────────────────────────────────────────────────────
# Phase 2 — Node: agent_finalize_run
# ─────────────────────────────────────────────────────────────────────────────

class TestAgentFinalizeRunNode:

    def _call(self, agent_run_id="run-1", step_results=None):
        from services.nodus_adapter import agent_finalize_run
        db = MagicMock()
        mock_run = MagicMock()
        mock_run.id = agent_run_id
        mock_run.status = "executing"
        db.query.return_value.filter.return_value.first.return_value = mock_run
        state = {
            "agent_run_id": agent_run_id,
            "user_id": "u1",
            "step_results": step_results or [],
        }
        result = agent_finalize_run(state, {"db": db})
        return result, mock_run, db

    def test_returns_success(self):
        result, _, _ = self._call()
        assert result["status"] == "SUCCESS"

    def test_sets_status_completed(self):
        _, mock_run, _ = self._call()
        assert mock_run.status == "completed"

    def test_sets_completed_at(self):
        _, mock_run, _ = self._call()
        assert mock_run.completed_at is not None

    def test_writes_step_results_to_result(self):
        steps = [{"step_index": 0, "tool": "task.create", "status": "success"}]
        _, mock_run, _ = self._call(step_results=steps)
        assert mock_run.result["steps"] == steps

    def test_commits_to_db(self):
        _, _, db = self._call()
        db.commit.assert_called()

    def test_output_patch_has_finalized_true(self):
        result, _, _ = self._call()
        assert result["output_patch"]["finalized"] is True

    def test_no_agent_run_found_does_not_raise(self):
        """If AgentRun is missing, node must not raise."""
        from services.nodus_adapter import agent_finalize_run
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        result = agent_finalize_run(
            {"agent_run_id": "missing", "user_id": "u1", "step_results": []},
            {"db": db},
        )
        assert result["status"] == "SUCCESS"


# ─────────────────────────────────────────────────────────────────────────────
# Phase 3 — Flow graph structure
# ─────────────────────────────────────────────────────────────────────────────

class TestAgentFlowDefinition:

    def test_agent_flow_has_start(self):
        from services.nodus_adapter import AGENT_FLOW
        assert AGENT_FLOW["start"] == "agent_validate_steps"

    def test_agent_flow_has_end(self):
        from services.nodus_adapter import AGENT_FLOW
        assert "agent_finalize_run" in AGENT_FLOW["end"]

    def test_validate_steps_edges_to_execute_step(self):
        from services.nodus_adapter import AGENT_FLOW
        edges = AGENT_FLOW["edges"]["agent_validate_steps"]
        assert "agent_execute_step" in edges

    def test_execute_step_has_two_conditional_edges(self):
        from services.nodus_adapter import AGENT_FLOW
        edges = AGENT_FLOW["edges"]["agent_execute_step"]
        assert len(edges) == 2
        assert all(isinstance(e, dict) for e in edges)

    def test_execute_step_loops_back_to_itself_when_steps_remain(self):
        from services.nodus_adapter import AGENT_FLOW
        edges = AGENT_FLOW["edges"]["agent_execute_step"]
        loop_edge = edges[0]
        state_with_steps = {"current_step_index": 0, "steps": [{"tool": "x"}]}
        assert loop_edge["condition"](state_with_steps)
        assert loop_edge["target"] == "agent_execute_step"

    def test_execute_step_advances_to_finalize_when_done(self):
        from services.nodus_adapter import AGENT_FLOW
        edges = AGENT_FLOW["edges"]["agent_execute_step"]
        loop_edge = edges[0]
        state_done = {"current_step_index": 1, "steps": [{"tool": "x"}]}
        assert not loop_edge["condition"](state_done)
        fallthrough_edge = edges[1]
        assert fallthrough_edge["target"] == "agent_finalize_run"

    def test_finalize_run_has_no_outgoing_edges(self):
        from services.nodus_adapter import AGENT_FLOW
        assert AGENT_FLOW["edges"]["agent_finalize_run"] == []

    def test_more_steps_helper(self):
        from services.nodus_adapter import _more_steps
        assert _more_steps({"current_step_index": 0, "steps": [1, 2]}) is True
        assert _more_steps({"current_step_index": 2, "steps": [1, 2]}) is False
        assert _more_steps({"current_step_index": 0, "steps": []}) is False


class TestNodeRegistry:

    def test_all_three_nodes_registered(self):
        from services.flow_engine import NODE_REGISTRY
        # Ensure adapter is imported (triggers @register_node decorators)
        import services.nodus_adapter  # noqa: F401
        for name in ("agent_validate_steps", "agent_execute_step", "agent_finalize_run"):
            assert name in NODE_REGISTRY, f"{name} must be in NODE_REGISTRY"


# ─────────────────────────────────────────────────────────────────────────────
# Phase 4 — execute_with_flow integration
# ─────────────────────────────────────────────────────────────────────────────

def _make_full_db_mock(run_id="run-abc", status="executing"):
    """DB mock that simulates the AgentRun query pattern."""
    db = MagicMock()
    mock_run = MagicMock()
    mock_run.id = run_id
    mock_run.status = status
    mock_run.steps_completed = 0
    mock_run.current_step = 0
    mock_run.flow_run_id = None
    db.query.return_value.filter.return_value.first.return_value = mock_run
    db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []
    return db, mock_run


class TestNodusAdapterExecuteWithFlow:

    def test_successful_run_returns_success_status(self):
        db, mock_run = _make_full_db_mock()
        plan = {
            "steps": [{"tool": "task.create", "args": {}, "risk_level": "low", "description": "d"}],
            "overall_risk": "low",
        }
        mock_flow_result = {"status": "SUCCESS", "run_id": "flow-123", "state": {}}
        with patch("services.nodus_adapter.PersistentFlowRunner") as MockRunner:
            MockRunner.return_value.start.return_value = mock_flow_result
            from services.nodus_adapter import NodusAgentAdapter
            result = NodusAgentAdapter.execute_with_flow(
                run_id="run-abc", plan=plan, user_id="u1", db=db
            )
        assert result["status"] == "SUCCESS"

    def test_successful_run_links_flow_run_id(self):
        db, mock_run = _make_full_db_mock()
        plan = {"steps": [{"tool": "task.create", "args": {}, "risk_level": "low", "description": ""}]}
        mock_flow_result = {"status": "SUCCESS", "run_id": "flow-xyz", "state": {}}
        with patch("services.nodus_adapter.PersistentFlowRunner") as MockRunner:
            MockRunner.return_value.start.return_value = mock_flow_result
            from services.nodus_adapter import NodusAgentAdapter
            NodusAgentAdapter.execute_with_flow(
                run_id="run-abc", plan=plan, user_id="u1", db=db
            )
        assert mock_run.flow_run_id == "flow-xyz"

    def test_failed_run_finalises_agent_run(self):
        db, mock_run = _make_full_db_mock(status="executing")
        plan = {"steps": [{"tool": "genesis.message", "args": {}, "risk_level": "high", "description": ""}]}
        mock_flow_result = {
            "status": "FAILED",
            "run_id": "flow-err",
            "error": "Step 0 failed",
            "failed_node": "agent_execute_step",
        }
        with patch("services.nodus_adapter.PersistentFlowRunner") as MockRunner:
            MockRunner.return_value.start.return_value = mock_flow_result
            from services.nodus_adapter import NodusAgentAdapter
            result = NodusAgentAdapter.execute_with_flow(
                run_id="run-abc", plan=plan, user_id="u1", db=db
            )
        assert mock_run.status == "failed"
        assert result["status"] == "FAILED"

    def test_failed_run_writes_error_message(self):
        db, mock_run = _make_full_db_mock(status="executing")
        plan = {"steps": [{"tool": "task.create", "args": {}, "risk_level": "low", "description": ""}]}
        mock_flow_result = {"status": "FAILED", "run_id": "flow-1", "error": "boom"}
        with patch("services.nodus_adapter.PersistentFlowRunner") as MockRunner:
            MockRunner.return_value.start.return_value = mock_flow_result
            from services.nodus_adapter import NodusAgentAdapter
            NodusAgentAdapter.execute_with_flow(
                run_id="run-abc", plan=plan, user_id="u1", db=db
            )
        assert "boom" in (mock_run.error_message or "")

    def test_empty_plan_passes_empty_steps_to_runner(self):
        db, _ = _make_full_db_mock()
        mock_flow_result = {"status": "FAILED", "run_id": "flow-1", "error": "no steps"}
        with patch("services.nodus_adapter.PersistentFlowRunner") as MockRunner:
            MockRunner.return_value.start.return_value = mock_flow_result
            from services.nodus_adapter import NodusAgentAdapter
            NodusAgentAdapter.execute_with_flow(
                run_id="run-abc", plan={}, user_id="u1", db=db
            )
        # Runner was still started (validate_steps will fail inside the flow)
        MockRunner.return_value.start.assert_called_once()

    def test_none_plan_handled_gracefully(self):
        db, _ = _make_full_db_mock()
        mock_flow_result = {"status": "FAILED", "run_id": "flow-1", "error": "none plan"}
        with patch("services.nodus_adapter.PersistentFlowRunner") as MockRunner:
            MockRunner.return_value.start.return_value = mock_flow_result
            from services.nodus_adapter import NodusAgentAdapter
            result = NodusAgentAdapter.execute_with_flow(
                run_id="run-abc", plan=None, user_id="u1", db=db
            )
        assert result is not None

    def test_runner_exception_returns_failed_dict(self):
        db, _ = _make_full_db_mock()
        plan = {"steps": [{"tool": "task.create", "args": {}, "risk_level": "low", "description": ""}]}
        with patch("services.nodus_adapter.PersistentFlowRunner") as MockRunner:
            MockRunner.return_value.start.side_effect = RuntimeError("db gone")
            from services.nodus_adapter import NodusAgentAdapter
            result = NodusAgentAdapter.execute_with_flow(
                run_id="run-abc", plan=plan, user_id="u1", db=db
            )
        assert result["status"] == "FAILED"
        assert "db gone" in result["error"]


# ─────────────────────────────────────────────────────────────────────────────
# Phase 5 — execute_run delegates to adapter
# ─────────────────────────────────────────────────────────────────────────────

class TestExecuteRunDelegatestoAdapter:

    def _make_run(self, status="approved"):
        run = MagicMock()
        run.id = "run-test"
        run.user_id = "u1"
        run.status = status
        run.plan = {"steps": [{"tool": "task.create", "args": {}, "risk_level": "low"}]}
        run.goal = "test goal"
        run.executive_summary = ""
        run.overall_risk = "low"
        run.steps_total = 1
        run.steps_completed = 1
        run.result = {"steps": []}
        run.error_message = None
        run.flow_run_id = "flow-1"
        run.created_at = datetime.now(timezone.utc)
        run.approved_at = None
        run.started_at = None
        run.completed_at = None
        return run

    def test_execute_run_calls_adapter_execute_with_flow(self):
        mock_run = self._make_run()
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = mock_run

        with patch("services.nodus_adapter.NodusAgentAdapter.execute_with_flow") as mock_adapter:
            mock_adapter.return_value = {"status": "SUCCESS", "run_id": "flow-1"}
            from services.agent_runtime import execute_run
            execute_run(run_id="run-test", user_id="u1", db=db)

        mock_adapter.assert_called_once()

    def test_execute_run_sets_status_executing_before_adapter(self):
        """The run must be marked 'executing' and committed before the adapter runs."""
        mock_run = self._make_run()
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = mock_run

        status_at_call = []

        def capture(*args, **kwargs):
            status_at_call.append(mock_run.status)
            return {"status": "SUCCESS", "run_id": "f1"}

        with patch("services.nodus_adapter.NodusAgentAdapter.execute_with_flow", side_effect=capture):
            from services.agent_runtime import execute_run
            execute_run(run_id="run-test", user_id="u1", db=db)

        assert status_at_call[0] == "executing"

    def test_execute_run_returns_dict_with_run_id(self):
        mock_run = self._make_run()
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = mock_run

        with patch("services.nodus_adapter.NodusAgentAdapter.execute_with_flow",
                   return_value={"status": "SUCCESS", "run_id": "f1"}):
            from services.agent_runtime import execute_run
            result = execute_run(run_id="run-test", user_id="u1", db=db)

        assert result is not None
        assert "run_id" in result

    def test_execute_run_returns_none_when_run_not_found(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        from services.agent_runtime import execute_run
        result = execute_run(run_id="missing", user_id="u1", db=db)
        assert result is None

    def test_execute_run_returns_run_dict_when_not_approved(self):
        mock_run = self._make_run(status="pending_approval")
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = mock_run
        from services.agent_runtime import execute_run
        result = execute_run(run_id="run-test", user_id="u1", db=db)
        # Should return run dict, not None
        assert result is not None

    def test_execute_run_returns_none_on_user_mismatch(self):
        mock_run = self._make_run(status="approved")
        mock_run.user_id = "other-user"
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = mock_run
        from services.agent_runtime import execute_run
        result = execute_run(run_id="run-test", user_id="u1", db=db)
        assert result is None

    def test_run_dict_includes_flow_run_id_key(self):
        mock_run = self._make_run()
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = mock_run

        with patch("services.nodus_adapter.NodusAgentAdapter.execute_with_flow",
                   return_value={"status": "SUCCESS", "run_id": "f1"}):
            from services.agent_runtime import execute_run
            result = execute_run(run_id="run-test", user_id="u1", db=db)

        assert "flow_run_id" in result

    def test_execute_run_does_not_contain_for_loop_over_steps(self):
        """
        Smoke-check: execute_run source must not contain the old
        step-execution for-loop (execute_tool called inside for idx, step).
        Ensures N+4 loop was fully replaced.
        """
        import inspect
        from services import agent_runtime
        src = inspect.getsource(agent_runtime.execute_run)
        # The N+4 loop enumerated steps directly — this is no longer present
        assert "for idx, step in enumerate(steps)" not in src


class TestAdapterExceptionRecovery:
    """Tests for the outer exception handler in execute_with_flow."""

    def test_runner_constructor_exception_returns_failed(self):
        """If PersistentFlowRunner() raises, adapter returns FAILED without blowing up."""
        db = MagicMock()
        mock_run = MagicMock()
        mock_run.status = "executing"
        db.query.return_value.filter.return_value.first.return_value = mock_run

        with patch("services.nodus_adapter.PersistentFlowRunner", side_effect=Exception("no db")):
            from services.nodus_adapter import NodusAgentAdapter
            result = NodusAgentAdapter.execute_with_flow(
                run_id="run-1",
                plan={"steps": [{"tool": "task.create", "args": {}, "risk_level": "low", "description": ""}]},
                user_id="u1",
                db=db,
            )
        assert result["status"] == "FAILED"
        assert "no db" in result["error"]

    def test_runner_exception_marks_agent_run_failed(self):
        db = MagicMock()
        mock_run = MagicMock()
        mock_run.status = "executing"
        db.query.return_value.filter.return_value.first.return_value = mock_run

        with patch("services.nodus_adapter.PersistentFlowRunner", side_effect=RuntimeError("crash")):
            from services.nodus_adapter import NodusAgentAdapter
            NodusAgentAdapter.execute_with_flow(
                run_id="run-1",
                plan={"steps": []},
                user_id="u1",
                db=db,
            )
        assert mock_run.status == "failed"


class TestAgentRuntimeRequiresApproval:

    def test_high_risk_always_requires_approval(self):
        from services.agent_runtime import _requires_approval
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        assert _requires_approval("high", "u1", db) is True

    def test_no_trust_settings_requires_approval(self):
        from services.agent_runtime import _requires_approval
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        assert _requires_approval("low", "u1", db) is True

    def test_auto_execute_low_bypasses_approval(self):
        from services.agent_runtime import _requires_approval
        trust = MagicMock()
        trust.auto_execute_low = True
        trust.auto_execute_medium = False
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = trust
        assert _requires_approval("low", "u1", db) is False

    def test_auto_execute_medium_bypasses_approval_for_medium(self):
        from services.agent_runtime import _requires_approval
        trust = MagicMock()
        trust.auto_execute_low = False
        trust.auto_execute_medium = True
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = trust
        assert _requires_approval("medium", "u1", db) is False

    def test_medium_still_requires_approval_when_flag_off(self):
        from services.agent_runtime import _requires_approval
        trust = MagicMock()
        trust.auto_execute_low = True
        trust.auto_execute_medium = False
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = trust
        assert _requires_approval("medium", "u1", db) is True


class TestApproveRun:
    """Direct unit tests for approve_run() — covers lines 336-354."""

    def _mock_run(self, status="pending_approval", user_id="u1"):
        run = MagicMock()
        run.id = "run-1"
        run.user_id = user_id
        run.status = status
        run.goal = "g"
        run.executive_summary = ""
        run.overall_risk = "low"
        run.steps_total = 0
        run.steps_completed = 0
        run.plan = {"steps": []}
        run.result = {}
        run.error_message = None
        run.flow_run_id = None
        run.created_at = datetime.now(timezone.utc)
        run.approved_at = None
        run.started_at = None
        run.completed_at = None
        return run

    def test_approve_returns_none_when_run_not_found(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        from services.agent_runtime import approve_run
        assert approve_run("missing", "u1", db) is None

    def test_approve_returns_none_when_user_mismatch(self):
        db = MagicMock()
        run = self._mock_run(user_id="other")
        db.query.return_value.filter.return_value.first.return_value = run
        from services.agent_runtime import approve_run
        assert approve_run("run-1", "u1", db) is None

    def test_approve_returns_run_dict_when_not_pending(self):
        db = MagicMock()
        run = self._mock_run(status="completed")
        db.query.return_value.filter.return_value.first.return_value = run
        from services.agent_runtime import approve_run
        result = approve_run("run-1", "u1", db)
        assert result is not None
        assert result["run_id"] == "run-1"

    def test_approve_marks_status_approved_then_calls_execute(self):
        db = MagicMock()
        run = self._mock_run(status="pending_approval")
        db.query.return_value.filter.return_value.first.return_value = run
        with patch("services.agent_runtime.execute_run", return_value={"run_id": "run-1", "status": "completed"}) as mock_exec:
            from services.agent_runtime import approve_run
            result = approve_run("run-1", "u1", db)
        assert run.status == "approved"
        mock_exec.assert_called_once_with(run_id="run-1", user_id="u1", db=db)

    def test_approve_sets_approved_at(self):
        db = MagicMock()
        run = self._mock_run(status="pending_approval")
        db.query.return_value.filter.return_value.first.return_value = run
        with patch("services.agent_runtime.execute_run", return_value={"run_id": "run-1"}):
            from services.agent_runtime import approve_run
            approve_run("run-1", "u1", db)
        assert run.approved_at is not None


class TestRejectRun:
    """Direct unit tests for reject_run() — covers lines 359-377."""

    def _mock_run(self, status="pending_approval", user_id="u1"):
        run = MagicMock()
        run.id = "run-1"
        run.user_id = user_id
        run.status = status
        run.goal = "g"
        run.executive_summary = ""
        run.overall_risk = "low"
        run.steps_total = 0
        run.steps_completed = 0
        run.plan = {}
        run.result = {}
        run.error_message = None
        run.flow_run_id = None
        run.created_at = datetime.now(timezone.utc)
        run.approved_at = None
        run.started_at = None
        run.completed_at = None
        return run

    def test_reject_returns_none_when_run_not_found(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        from services.agent_runtime import reject_run
        assert reject_run("missing", "u1", db) is None

    def test_reject_returns_none_when_user_mismatch(self):
        db = MagicMock()
        run = self._mock_run(user_id="other")
        db.query.return_value.filter.return_value.first.return_value = run
        from services.agent_runtime import reject_run
        assert reject_run("run-1", "u1", db) is None

    def test_reject_returns_run_dict_when_not_pending(self):
        db = MagicMock()
        run = self._mock_run(status="completed")
        db.query.return_value.filter.return_value.first.return_value = run
        from services.agent_runtime import reject_run
        result = reject_run("run-1", "u1", db)
        assert result is not None

    def test_reject_marks_status_rejected(self):
        db = MagicMock()
        run = self._mock_run(status="pending_approval")
        db.query.return_value.filter.return_value.first.return_value = run
        from services.agent_runtime import reject_run
        reject_run("run-1", "u1", db)
        assert run.status == "rejected"

    def test_reject_sets_completed_at(self):
        db = MagicMock()
        run = self._mock_run(status="pending_approval")
        db.query.return_value.filter.return_value.first.return_value = run
        from services.agent_runtime import reject_run
        reject_run("run-1", "u1", db)
        assert run.completed_at is not None

    def test_reject_commits_to_db(self):
        db = MagicMock()
        run = self._mock_run(status="pending_approval")
        db.query.return_value.filter.return_value.first.return_value = run
        from services.agent_runtime import reject_run
        reject_run("run-1", "u1", db)
        db.commit.assert_called()


class TestRunToDictFlowRunId:

    def test_run_to_dict_includes_flow_run_id_when_set(self):
        from services.agent_runtime import _run_to_dict
        run = MagicMock()
        run.id = "run-1"
        run.user_id = "u1"
        run.goal = "g"
        run.executive_summary = ""
        run.overall_risk = "low"
        run.status = "completed"
        run.steps_total = 1
        run.steps_completed = 1
        run.plan = {}
        run.result = {}
        run.error_message = None
        run.flow_run_id = "flow-abc"
        run.created_at = datetime.now(timezone.utc)
        run.approved_at = None
        run.started_at = None
        run.completed_at = None
        d = _run_to_dict(run)
        assert d["flow_run_id"] == "flow-abc"

    def test_run_to_dict_flow_run_id_none_when_not_set(self):
        from services.agent_runtime import _run_to_dict
        run = MagicMock()
        run.id = "run-1"
        run.user_id = "u1"
        run.goal = "g"
        run.executive_summary = ""
        run.overall_risk = "low"
        run.status = "completed"
        run.steps_total = 0
        run.steps_completed = 0
        run.plan = {}
        run.result = {}
        run.error_message = None
        run.flow_run_id = None
        run.created_at = datetime.now(timezone.utc)
        run.approved_at = None
        run.started_at = None
        run.completed_at = None
        d = _run_to_dict(run)
        assert d["flow_run_id"] is None
