"""
Flow Engine Phase B Tests — PersistentFlowRunner
"""
import pytest
from uuid import uuid4
from unittest.mock import MagicMock, patch


class TestFlowEngineCore:

    def test_flow_engine_importable(self):
        from runtime.flow_engine import (
            FLOW_REGISTRY,
            NODE_REGISTRY,
            PersistentFlowRunner,
            execute_intent,
            execute_node,
            record_outcome,
            register_flow,
            register_node,
            resolve_next_node,
            route_event,
            select_strategy,
        )
        assert PersistentFlowRunner is not None

    def test_register_node_decorator(self):
        from runtime.flow_engine import NODE_REGISTRY, register_node

        @register_node("test_node_phase_b")
        def test_node(state, context):
            return {"status": "SUCCESS", "output_patch": {"done": True}}

        assert "test_node_phase_b" in NODE_REGISTRY

    def test_register_flow(self):
        from runtime.flow_engine import FLOW_REGISTRY, register_flow

        register_flow(
            "test_flow_phase_b",
            {"start": "node_a", "edges": {"node_a": ["node_b"]}, "end": ["node_b"]},
        )

        assert "test_flow_phase_b" in FLOW_REGISTRY

    def test_resolve_next_node_simple(self):
        from runtime.flow_engine import resolve_next_node

        flow = {"edges": {"node_a": ["node_b"]}}
        result = resolve_next_node("node_a", {}, flow)
        assert result == "node_b"

    def test_resolve_next_node_conditional(self):
        from runtime.flow_engine import resolve_next_node

        flow = {
            "edges": {
                "node_a": [
                    {
                        "condition": lambda s: s.get("score", 0) >= 7,
                        "target": "high_score_node",
                    },
                    {"condition": lambda s: True, "target": "default_node"},
                ]
            }
        }

        # High score → first branch
        result = resolve_next_node("node_a", {"score": 8}, flow)
        assert result == "high_score_node"

        # Low score → default branch
        result = resolve_next_node("node_a", {"score": 3}, flow)
        assert result == "default_node"

    def test_resolve_next_node_no_edges(self):
        from runtime.flow_engine import resolve_next_node

        result = resolve_next_node("orphan_node", {}, {"edges": {}})
        assert result is None

    def test_enforce_policy_blocks_node(self):
        from runtime.flow_engine import POLICY, enforce_policy

        POLICY["blocked_nodes"].append("test_blocked_node")

        try:
            with pytest.raises(PermissionError):
                enforce_policy("test_blocked_node")
        finally:
            POLICY["blocked_nodes"].remove("test_blocked_node")

    def test_execute_node_unknown_raises(self, mock_db):
        from runtime.flow_engine import execute_node

        with pytest.raises(KeyError):
            execute_node(
                "nonexistent_node_xyz",
                {},
                {"attempts": {}, "db": mock_db},
            )

    def test_compile_plan_to_flow(self):
        from runtime.flow_engine import compile_plan_to_flow

        plan = {"steps": ["step_a", "step_b", "step_c"]}
        flow = compile_plan_to_flow(plan)

        assert flow["start"] == "step_a"
        assert flow["end"] == ["step_c"]
        assert flow["edges"]["step_a"] == ["step_b"]
        assert flow["edges"]["step_b"] == ["step_c"]

    def test_compile_empty_plan_raises(self):
        from runtime.flow_engine import compile_plan_to_flow

        with pytest.raises(ValueError):
            compile_plan_to_flow({"steps": []})


class TestPersistentFlowRunner:

    @staticmethod
    def _create_run(db_session, current_node, user_id, state=None):
        from db.models.flow_run import FlowRun

        run = FlowRun(
            id=str(uuid4()),
            flow_name="test_flow_phase_b",
            workflow_type="test",
            state=state or {},
            current_node=current_node,
            status="running",
            trace_id=str(uuid4()),
            user_id=user_id,
        )
        db_session.add(run)
        db_session.commit()
        db_session.refresh(run)
        return run

    def test_runner_instantiates(self, db_session, test_user):
        from runtime.flow_engine import PersistentFlowRunner

        runner = PersistentFlowRunner(
            flow={"start": "node_a", "edges": {}, "end": ["node_a"]},
            db=db_session,
            user_id=test_user.id,
            workflow_type="test",
        )
        assert runner is not None

    def test_runner_handles_missing_run(self, db_session):
        """resume() returns FAILED if run not found."""
        from runtime.flow_engine import PersistentFlowRunner

        runner = PersistentFlowRunner(
            flow={"start": "n", "edges": {}, "end": ["n"]},
            db=db_session,
        )
        result = runner.resume("nonexistent-run-id")
        assert result["status"] == "FAILED"

    def test_flow_success_path(self, db_session, test_user):
        """Single-node flow completes successfully."""
        from runtime.flow_engine import PersistentFlowRunner, register_node

        @register_node("test_success_node_b")
        def success_node(state, context):
            return {"status": "SUCCESS", "output_patch": {"result": "done"}}

        run = self._create_run(
            db_session,
            current_node="test_success_node_b",
            user_id=test_user.id,
            state={"input": "data"},
        )

        flow = {
            "start": "test_success_node_b",
            "edges": {},
            "end": ["test_success_node_b"],
        }

        runner = PersistentFlowRunner(flow=flow, db=db_session, user_id=test_user.id)
        result = runner.resume(run.id)

        assert result["status"] == "SUCCESS"

    def test_flow_failure_path(self, db_session, test_user):
        """Node returning FAILURE fails the run."""
        from runtime.flow_engine import PersistentFlowRunner, register_node

        @register_node("test_failure_node_b")
        def failure_node(state, context):
            return {"status": "FAILURE", "error": "intentional failure"}

        run = self._create_run(
            db_session,
            current_node="test_failure_node_b",
            user_id=test_user.id,
        )

        flow = {
            "start": "test_failure_node_b",
            "edges": {},
            "end": ["test_failure_node_b"],
        }

        runner = PersistentFlowRunner(flow=flow, db=db_session, user_id=test_user.id)
        result = runner.resume(run.id)

        assert result["status"] == "FAILED"

    def test_flow_wait_path(self, db_session, test_user):
        """Node returning WAIT suspends the run."""
        from runtime.flow_engine import PersistentFlowRunner, register_node

        @register_node("test_wait_node_b")
        def wait_node(state, context):
            return {"status": "WAIT", "wait_for": "user_approval"}

        run = self._create_run(
            db_session,
            current_node="test_wait_node_b",
            user_id=test_user.id,
        )

        flow = {
            "start": "test_wait_node_b",
            "edges": {},
            "end": ["test_wait_node_b"],
        }

        runner = PersistentFlowRunner(flow=flow, db=db_session, user_id=test_user.id)
        result = runner.resume(run.id)

        assert result["status"] == "WAITING"
        assert result["result"]["waiting_for"] == "user_approval"

    def test_flow_wait_without_wait_for_is_failure(self, db_session, test_user):
        """Node returning WAIT without wait_for treats as FAILURE."""
        from runtime.flow_engine import PersistentFlowRunner, register_node

        @register_node("test_wait_no_event_node_b")
        def bad_wait_node(state, context):
            return {"status": "WAIT"}  # missing wait_for

        run = self._create_run(
            db_session,
            current_node="test_wait_no_event_node_b",
            user_id=test_user.id,
        )

        flow = {
            "start": "test_wait_no_event_node_b",
            "edges": {},
            "end": ["test_wait_no_event_node_b"],
        }

        runner = PersistentFlowRunner(flow=flow, db=db_session, user_id=test_user.id)
        result = runner.resume(run.id)

        assert result["status"] == "FAILED"

    def test_flow_exception_in_node_fails_run(self, db_session, test_user):
        """Unhandled exception in node fn fails the run."""
        from runtime.flow_engine import PersistentFlowRunner, register_node

        @register_node("test_exception_node_b")
        def exploding_node(state, context):
            raise RuntimeError("boom")

        run = self._create_run(
            db_session,
            current_node="test_exception_node_b",
            user_id=test_user.id,
        )

        flow = {
            "start": "test_exception_node_b",
            "edges": {},
            "end": ["test_exception_node_b"],
        }

        runner = PersistentFlowRunner(flow=flow, db=db_session, user_id=test_user.id)
        result = runner.resume(run.id)

        assert result["status"] == "FAILED"
        assert "boom" in result.get("result", {}).get("error", "")

    def test_multi_node_flow_advances(self, db_session, test_user):
        """Two-node flow: node_a → node_b (end)."""
        from runtime.flow_engine import PersistentFlowRunner, register_node

        call_order = []

        @register_node("test_node_a_phase_b")
        def node_a(state, context):
            call_order.append("a")
            return {"status": "SUCCESS", "output_patch": {"a": True}}

        @register_node("test_node_b_phase_b")
        def node_b(state, context):
            call_order.append("b")
            return {"status": "SUCCESS", "output_patch": {"b": True}}

        run = self._create_run(
            db_session,
            current_node="test_node_a_phase_b",
            user_id=test_user.id,
        )

        flow = {
            "start": "test_node_a_phase_b",
            "edges": {"test_node_a_phase_b": ["test_node_b_phase_b"]},
            "end": ["test_node_b_phase_b"],
        }

        runner = PersistentFlowRunner(flow=flow, db=db_session, user_id=test_user.id)
        result = runner.resume(run.id)

        assert result["status"] == "SUCCESS"
        assert call_order == ["a", "b"]


class TestFlowDefinitions:

    def test_all_flows_registered_at_startup(self):
        from runtime.flow_definitions import register_all_flows
        from runtime.flow_engine import FLOW_REGISTRY

        register_all_flows()

        expected_flows = ["arm_analysis", "task_completion", "leadgen_search"]
        for flow_name in expected_flows:
            assert flow_name in FLOW_REGISTRY, f"Flow not registered: {flow_name}"

    def test_all_flow_nodes_in_registry(self):
        from runtime.flow_definitions import register_all_flows
        from runtime.flow_engine import NODE_REGISTRY

        register_all_flows()

        expected_nodes = [
            "arm_validate_input",
            "arm_analyze_code",
            "arm_store_result",
            "task_validate",
            "task_complete",
            "task_orchestrate",
            "leadgen_validate",
            "leadgen_search",
            "leadgen_store",
        ]
        for node_name in expected_nodes:
            assert node_name in NODE_REGISTRY, f"Node not registered: {node_name}"

    def test_flow_graphs_valid(self):
        """All flow graphs have valid structure."""
        from runtime.flow_definitions import register_all_flows
        from runtime.flow_engine import FLOW_REGISTRY

        register_all_flows()

        for name, flow in FLOW_REGISTRY.items():
            assert "start" in flow, f"Flow {name} missing 'start'"
            assert "edges" in flow, f"Flow {name} missing 'edges'"
            assert "end" in flow, f"Flow {name} missing 'end'"
            assert isinstance(flow["end"], list), f"Flow {name} 'end' must be a list"

    def test_arm_validate_input_passes_with_file_path(self):
        from runtime.flow_engine import NODE_REGISTRY
        from runtime.flow_definitions import register_all_flows

        register_all_flows()
        node_fn = NODE_REGISTRY["arm_validate_input"]
        result = node_fn({"file_path": "/some/file.py"}, {"attempts": {}})
        assert result["status"] == "SUCCESS"

    def test_arm_validate_input_fails_without_file_path(self):
        from runtime.flow_engine import NODE_REGISTRY
        from runtime.flow_definitions import register_all_flows

        register_all_flows()
        node_fn = NODE_REGISTRY["arm_validate_input"]
        result = node_fn({}, {"attempts": {}})
        assert result["status"] == "FAILURE"

    def test_task_validate_passes_with_task_name(self):
        from runtime.flow_engine import NODE_REGISTRY
        from runtime.flow_definitions import register_all_flows

        register_all_flows()
        node_fn = NODE_REGISTRY["task_validate"]
        result = node_fn({"task_name": "my task"}, {"attempts": {}})
        assert result["status"] == "SUCCESS"

    def test_task_validate_fails_without_task_name(self):
        from runtime.flow_engine import NODE_REGISTRY
        from runtime.flow_definitions import register_all_flows

        register_all_flows()
        node_fn = NODE_REGISTRY["task_validate"]
        result = node_fn({}, {"attempts": {}})
        assert result["status"] == "FAILURE"

    def test_leadgen_validate_passes_with_query(self):
        from runtime.flow_engine import NODE_REGISTRY
        from runtime.flow_definitions import register_all_flows

        register_all_flows()
        node_fn = NODE_REGISTRY["leadgen_validate"]
        result = node_fn({"query": "AI companies"}, {"attempts": {}})
        assert result["status"] == "SUCCESS"

    def test_leadgen_validate_fails_without_query(self):
        from runtime.flow_engine import NODE_REGISTRY
        from runtime.flow_definitions import register_all_flows

        register_all_flows()
        node_fn = NODE_REGISTRY["leadgen_validate"]
        result = node_fn({}, {"attempts": {}})
        assert result["status"] == "FAILURE"

    def test_store_nodes_return_success_on_exception(self, mock_db):
        """Storage failure nodes return SUCCESS even when exception occurs."""
        from runtime.flow_engine import NODE_REGISTRY
        from runtime.flow_definitions import register_all_flows

        register_all_flows()

        # Pass a broken db that raises on execute
        bad_db = MagicMock()
        bad_db.add.side_effect = RuntimeError("DB down")

        context = {
            "db": bad_db,
            "user_id": "00000000-0000-0000-0000-000000000001",
            "attempts": {},
        }

        for store_node in ["arm_store_result", "leadgen_store"]:
            node_fn = NODE_REGISTRY[store_node]
            result = node_fn({}, context)
            assert result["status"] == "SUCCESS", (
                f"Store node {store_node} should return SUCCESS even on exception"
            )


class TestFlowRouterEndpoints:

    def test_list_runs_requires_auth(self, client):
        r = client.get("/flows/runs")
        assert r.status_code == 401

    def test_get_run_requires_auth(self, client):
        r = client.get("/flows/runs/test-id")
        assert r.status_code == 401

    def test_history_requires_auth(self, client):
        r = client.get("/flows/runs/test-id/history")
        assert r.status_code == 401

    def test_resume_requires_auth(self, client):
        r = client.post(
            "/flows/runs/test-id/resume",
            json={"event_type": "test", "payload": {}},
        )
        assert r.status_code == 401

    def test_registry_requires_auth(self, client):
        r = client.get("/flows/registry")
        assert r.status_code == 401

    def test_list_runs_with_auth(self, client, auth_headers):
        r = client.get("/flows/runs", headers=auth_headers)
        assert r.status_code != 401
        if r.status_code == 200:
            data = r.json()
            assert "runs" in data
            assert "count" in data

    def test_registry_with_auth(self, client, auth_headers):
        r = client.get("/flows/registry", headers=auth_headers)
        assert r.status_code != 401
        if r.status_code == 200:
            data = r.json()
            assert "flows" in data
            assert "nodes" in data

    def test_resume_non_waiting_run_rejected(self, client, auth_headers):
        """
        Resuming a non-waiting run returns 404 (not found in test db)
        or 400 (wrong status if found). Either is acceptable; 401 is not.
        """
        r = client.post(
            "/flows/runs/fake-non-waiting-run/resume",
            json={"event_type": "test_event", "payload": {}},
            headers=auth_headers,
        )
        assert r.status_code in (400, 404)
        assert r.status_code != 401

    def test_flow_routes_registered_in_app(self, app):
        """All 5 flow routes are registered in the app."""
        routes = [r.path for r in app.routes]
        assert "/flows/runs" in routes
        assert "/flows/runs/{run_id}" in routes
        assert "/flows/runs/{run_id}/history" in routes
        assert "/flows/runs/{run_id}/resume" in routes
        assert "/flows/registry" in routes


class TestStrategySelection:

    def test_select_strategy_no_strategies(self, db_session, test_user):
        from runtime.flow_engine import select_strategy

        result = select_strategy(
            intent_type="unknown_intent", db=db_session, user_id=test_user.id
        )
        assert result is None

    def test_update_strategy_score_success(self, db_session, test_user):
        from db.models.flow_run import Strategy
        from runtime.flow_engine import update_strategy_score

        strategy = Strategy(
            id=str(uuid4()),
            intent_type="test_intent",
            flow={"start": "a", "edges": {}, "end": ["a"]},
            score=1.0,
            success_count=0,
            failure_count=0,
            user_id=test_user.id,
        )
        db_session.add(strategy)
        db_session.commit()

        update_strategy_score(
            intent_type="test_intent",
            flow_name="test_flow",
            success=True,
            db=db_session,
            user_id=test_user.id,
        )

        db_session.refresh(strategy)
        assert strategy.score == pytest.approx(1.1, abs=1e-9)
        assert strategy.success_count == 1

    def test_update_strategy_score_failure(self, db_session, test_user):
        from db.models.flow_run import Strategy
        from runtime.flow_engine import update_strategy_score

        strategy = Strategy(
            id=str(uuid4()),
            intent_type="test_intent",
            flow={"start": "a", "edges": {}, "end": ["a"]},
            score=1.0,
            success_count=0,
            failure_count=0,
            user_id=test_user.id,
        )
        db_session.add(strategy)
        db_session.commit()

        update_strategy_score(
            intent_type="test_intent",
            flow_name="test_flow",
            success=False,
            db=db_session,
            user_id=test_user.id,
        )

        db_session.refresh(strategy)
        assert strategy.score == pytest.approx(0.85, abs=1e-9)
        assert strategy.failure_count == 1

    def test_strategy_score_floor(self, db_session, test_user):
        """Score cannot go below 0.1."""
        from db.models.flow_run import Strategy
        from runtime.flow_engine import update_strategy_score

        strategy = Strategy(
            id=str(uuid4()),
            intent_type="test",
            flow={"start": "a", "edges": {}, "end": ["a"]},
            score=0.15,
            success_count=0,
            failure_count=0,
            user_id=test_user.id,
        )
        db_session.add(strategy)
        db_session.commit()

        update_strategy_score(
            intent_type="test",
            flow_name="test",
            success=False,
            db=db_session,
            user_id=test_user.id,
        )

        db_session.refresh(strategy)
        assert strategy.score >= 0.1

    def test_strategy_score_ceiling(self, db_session, test_user):
        """Score cannot exceed 2.0."""
        from db.models.flow_run import Strategy
        from runtime.flow_engine import update_strategy_score

        strategy = Strategy(
            id=str(uuid4()),
            intent_type="test",
            flow={"start": "a", "edges": {}, "end": ["a"]},
            score=1.95,
            success_count=0,
            failure_count=0,
            user_id=test_user.id,
        )
        db_session.add(strategy)
        db_session.commit()

        update_strategy_score(
            intent_type="test",
            flow_name="test",
            success=True,
            db=db_session,
            user_id=test_user.id,
        )

        db_session.refresh(strategy)
        assert strategy.score <= 2.0

    def test_update_strategy_score_no_strategy_is_noop(self, db_session, test_user):
        """update_strategy_score is a no-op when no strategy found."""
        from runtime.flow_engine import update_strategy_score

        # Should not raise
        update_strategy_score(
            intent_type="missing",
            flow_name="test",
            success=True,
            db=db_session,
            user_id=test_user.id,
        )


class TestRuntimeRedirects:

    def test_memory_loop_redirects_to_flow_engine(self):
        """runtime/memory_loop.py re-exports from flow_engine."""
        from runtime import memory_loop

        assert hasattr(memory_loop, "PersistentFlowRunner")

    def test_memory_loop_preserves_execution_loop_class_name(self):
        """ExecutionLoop class is still accessible (existing code depends on it)."""
        from runtime import memory_loop

        assert hasattr(memory_loop, "ExecutionLoop")

    def test_execution_registry_redirects(self):
        """runtime/execution_registry.py re-exports from flow_engine."""
        from runtime import execution_registry

        assert hasattr(execution_registry, "NODE_REGISTRY")

    def test_execution_registry_preserves_existing_registry(self):
        """REGISTRY singleton is still accessible (existing code depends on it)."""
        from runtime import execution_registry

        assert hasattr(execution_registry, "REGISTRY")


class TestFlowEngineModels:

    def test_flow_run_model_importable(self):
        from db.models.flow_run import FlowRun

        assert FlowRun.__tablename__ == "flow_runs"

    def test_flow_history_model_importable(self):
        from db.models.flow_run import FlowHistory

        assert FlowHistory.__tablename__ == "flow_history"

    def test_event_outcome_model_importable(self):
        from db.models.flow_run import EventOutcome

        assert EventOutcome.__tablename__ == "event_outcomes"

    def test_strategy_model_importable(self):
        from db.models.flow_run import Strategy

        assert Strategy.__tablename__ == "strategies"

    def test_models_exported_from_package(self):
        from db.models import EventOutcome, FlowHistory, FlowRun, Strategy

        assert FlowRun is not None
        assert FlowHistory is not None
        assert EventOutcome is not None
        assert Strategy is not None

    def test_flow_run_instantiates(self):
        from db.models.flow_run import FlowRun

        run = FlowRun(
            flow_name="test_flow",
            workflow_type="arm_analysis",
            state={"input": "data"},
            current_node="node_a",
            status="running",
        )
        assert run.flow_name == "test_flow"
        assert run.workflow_type == "arm_analysis"
        assert run.status == "running"

    def test_flow_history_instantiates(self):
        from db.models.flow_run import FlowHistory

        history = FlowHistory(
            flow_run_id="test-run-id",
            node_name="test_node",
            status="SUCCESS",
        )
        assert history.node_name == "test_node"
        assert history.status == "SUCCESS"

    def test_strategy_instantiates(self):
        from db.models.flow_run import Strategy

        strategy = Strategy(
            intent_type="arm_analysis",
            flow={"start": "n", "edges": {}, "end": ["n"]},
            score=1.0,
        )
        assert strategy.intent_type == "arm_analysis"
        assert strategy.score == 1.0

    def test_event_outcome_instantiates(self):
        from db.models.flow_run import EventOutcome

        outcome = EventOutcome(
            event_type="arm_analysis",
            flow_name="arm_analysis",
            success=True,
        )
        assert outcome.event_type == "arm_analysis"
        assert outcome.success is True

    def test_flow_run_id_has_uuid_default(self):
        from db.models.flow_run import FlowRun

        id_col = FlowRun.__table__.columns["id"]
        assert id_col.default is not None
        assert callable(id_col.default.arg)


class TestGeneratePlanFromIntent:

    def test_arm_analysis_plan(self):
        from runtime.flow_engine import generate_plan_from_intent

        plan = generate_plan_from_intent({"workflow_type": "arm_analysis"})
        assert "steps" in plan
        assert len(plan["steps"]) >= 1

    def test_task_completion_plan(self):
        from runtime.flow_engine import generate_plan_from_intent

        plan = generate_plan_from_intent({"workflow_type": "task_completion"})
        assert "steps" in plan

    def test_leadgen_search_plan(self):
        from runtime.flow_engine import generate_plan_from_intent

        plan = generate_plan_from_intent({"workflow_type": "leadgen_search"})
        assert "steps" in plan

    def test_generic_plan_fallback(self):
        from runtime.flow_engine import generate_plan_from_intent

        plan = generate_plan_from_intent({"workflow_type": "nonexistent_type"})
        assert "steps" in plan
        assert len(plan["steps"]) >= 1

    def test_missing_workflow_type_defaults_to_generic(self):
        from runtime.flow_engine import generate_plan_from_intent

        plan = generate_plan_from_intent({})
        assert "steps" in plan


# ═══════════════════════════════════════════════════════════════════════════════
# Fail-fast EU guard — PersistentFlowRunner.start()
# ═══════════════════════════════════════════════════════════════════════════════

class TestFlowRunnerEUFailFast:
    """
    PersistentFlowRunner.start() must raise RuntimeError immediately when
    ExecutionUnitService.create() returns None (EU creation failed).

    All tests use a fully-mocked DB to avoid calling self.db.commit() on
    the shared db_session fixture — real commits release the SQLite SAVEPOINT
    used for test isolation and corrupt subsequent tests.

    The guard logic verified here:
    - RuntimeError is raised before self.resume() is called
    - FlowRun.status is set to "failed" and db.commit() is called before raise
    - _eu_id is never silently set to None
    - When create() succeeds, the guard passes and resume() is called
    """

    _SIMPLE_FLOW = {
        "start": "noop_node",
        "edges": {},
        "end": ["noop_node"],
    }

    def teardown_method(self, method):
        # PersistentFlowRunner.start() calls ensure_trace_id() which sets
        # _trace_id_ctx without saving a token. Reset to the default sentinel
        # so downstream tests that call get_current_trace_id() (e.g. run_loop)
        # don't pick up a leaked UUID and write events with the wrong trace_id.
        from utils.trace_context import _trace_id_ctx
        _trace_id_ctx.set("-")

    @staticmethod
    def _mock_db():
        """Build a MagicMock DB that simulates add/commit/refresh/flush."""
        db = MagicMock()
        db.add.return_value = None
        db.commit.return_value = None
        db.refresh.return_value = None
        db.flush.return_value = None
        return db

    _TEST_USER_ID = "00000000-0000-0000-0000-000000000001"

    @staticmethod
    def _runner(mock_db, user_id=None):
        from runtime.flow_engine import PersistentFlowRunner
        uid = user_id or TestFlowRunnerEUFailFast._TEST_USER_ID
        return PersistentFlowRunner(
            flow={"start": "noop_node", "edges": {}, "end": ["noop_node"]},
            db=mock_db,
            user_id=uid,
            workflow_type="test",
        )

    def test_raises_runtime_error_when_eu_creation_returns_none(self):
        """start() raises RuntimeError when create() returns None."""
        db = self._mock_db()
        runner = self._runner(db)

        with patch("core.execution_unit_service.ExecutionUnitService.create", return_value=None), \
             patch("runtime.flow_engine.emit_system_event", return_value=None):
            with pytest.raises(RuntimeError, match="ExecutionUnit creation returned None"):
                runner.start({"input": "data"}, flow_name="test_flow")

    def test_error_message_contains_flow_name(self):
        db = self._mock_db()
        runner = self._runner(db)

        with patch("core.execution_unit_service.ExecutionUnitService.create", return_value=None), \
             patch("runtime.flow_engine.emit_system_event", return_value=None):
            with pytest.raises(RuntimeError) as exc_info:
                runner.start({}, flow_name="my_important_flow")

        assert "my_important_flow" in str(exc_info.value)

    def test_flow_run_marked_failed_before_raise(self):
        """FlowRun.status must be set to 'failed' and commit() called before raise."""
        db = self._mock_db()
        runner = self._runner(db)
        captured_run = {}

        def _capture_add(obj):
            from db.models.flow_run import FlowRun
            if isinstance(obj, FlowRun):
                captured_run["obj"] = obj

        db.add.side_effect = _capture_add

        with patch("core.execution_unit_service.ExecutionUnitService.create", return_value=None), \
             patch("runtime.flow_engine.emit_system_event", return_value=None):
            with pytest.raises(RuntimeError):
                runner.start({}, flow_name="failing_flow")

        run = captured_run.get("obj")
        assert run is not None, "FlowRun was never added to session"
        assert run.status == "failed"
        # commit() must have been called (at least once for the FlowRun creation,
        # and once more in the RuntimeError handler for the status update)
        assert db.commit.call_count >= 2

    def test_resume_never_called_when_eu_missing(self):
        """self.resume() must not be called when EU creation fails."""
        db = self._mock_db()
        runner = self._runner(db)

        with patch("core.execution_unit_service.ExecutionUnitService.create", return_value=None), \
             patch("runtime.flow_engine.emit_system_event", return_value=None), \
             patch.object(runner, "resume") as mock_resume:
            with pytest.raises(RuntimeError):
                runner.start({}, flow_name="test_flow")

        mock_resume.assert_not_called()

    def test_eu_id_not_set_to_none_silently(self):
        """
        The raise happens before self._eu_id is assigned, so _eu_id is never
        silently set to None when create() fails.
        """
        db = self._mock_db()
        runner = self._runner(db)

        with patch("core.execution_unit_service.ExecutionUnitService.create", return_value=None), \
             patch("runtime.flow_engine.emit_system_event", return_value=None):
            with pytest.raises(RuntimeError):
                runner.start({}, flow_name="test_flow")

        assert not getattr(runner, "_eu_id", None)

    def test_valid_eu_guard_passes_and_resume_called(self):
        """When create() returns a valid EU, the guard passes and resume() is called."""
        import uuid as _uuid
        db = self._mock_db()
        runner = self._runner(db)

        mock_eu = MagicMock()
        mock_eu.id = _uuid.uuid4()

        with patch("core.execution_unit_service.ExecutionUnitService.create", return_value=mock_eu), \
             patch("runtime.flow_engine.emit_system_event", return_value=None), \
             patch.object(runner, "resume", return_value={"status": "SUCCESS"}) as mock_resume:
            result = runner.start({}, flow_name="eu_guard_noop_flow")

        mock_resume.assert_called_once()
        assert runner._eu_id == mock_eu.id
        assert result["status"] == "SUCCESS"

