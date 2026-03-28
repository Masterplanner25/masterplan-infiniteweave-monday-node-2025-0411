"""
Flow Engine Phase C + D Tests

Phase C — Genesis → executable flow with WAIT states
  - genesis nodes registered (validate_session, record_exchange, store_synthesis)
  - genesis_conversation flow registered with correct graph structure
  - genesis_record_exchange: WAIT when synthesis_ready=False
  - genesis_record_exchange: SUCCESS when synthesis_ready=True (from state)
  - genesis_record_exchange: SUCCESS when synthesis_ready=True (from event payload)
  - genesis_validate_session: FAILURE without session_id
  - genesis_store_synthesis: SUCCESS even on exception (non-fatal)
  - genesis_router source has FlowRun integration (fire-and-forget block)
  - WAIT/RESUME round-trip via route_event

Phase D — FlowHistory → Memory Bridge
  - _capture_flow_completion exists on PersistentFlowRunner
  - skipped when user_id is None
  - skipped when workflow_type is None
  - calls MemoryCaptureEngine with correct event_type per workflow_type
  - non-fatal: exception in MemoryCaptureEngine does not crash the run
  - flow_completion in memory_capture_engine EVENT_SIGNIFICANCE
  - called automatically on flow SUCCESS in PersistentFlowRunner.resume()
"""
import pytest
import uuid
from unittest.mock import MagicMock, patch, call


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_mock_run(run_id="test-run-id", state=None, current_node="node_a"):
    run = MagicMock()
    run.id = run_id
    run.state = state or {}
    run.current_node = current_node
    run.user_id = "00000000-0000-0000-0000-000000000001"
    run.flow_name = "test_flow"
    run.workflow_type = "test"
    return run


def _seed_flow_history(db_session, flow_run_id, entries=None):
    from db.models.flow_run import FlowHistory, FlowRun

    entries = entries or [
        {
            "node_name": "node_a",
            "status": "SUCCESS",
            "execution_time_ms": 200,
        }
    ]
    existing_run = db_session.query(FlowRun).filter(FlowRun.id == flow_run_id).first()
    if existing_run is None:
        db_session.add(
            FlowRun(
                id=flow_run_id,
                flow_name="test_flow",
                workflow_type="arm_analysis",
                state={},
                current_node="node_a",
                status="running",
                trace_id=str(uuid.uuid4()),
            )
        )
        db_session.commit()
    for entry in entries:
        db_session.add(
            FlowHistory(
                id=str(uuid.uuid4()),
                flow_run_id=flow_run_id,
                node_name=entry["node_name"],
                status=entry["status"],
                execution_time_ms=entry.get("execution_time_ms"),
                input_state=entry.get("input_state"),
                output_patch=entry.get("output_patch"),
            )
        )
    db_session.commit()


# ══════════════════════════════════════════════════════════════════════════════
# PHASE C
# ══════════════════════════════════════════════════════════════════════════════


class TestGenesisNodesRegistered:
    """All genesis Phase C nodes must be in NODE_REGISTRY."""

    def test_genesis_nodes_registered(self):
        from services.flow_engine import NODE_REGISTRY
        from services.flow_definitions import register_all_flows
        register_all_flows()
        expected = [
            "genesis_validate_session",
            "genesis_record_exchange",
            "genesis_store_synthesis",
        ]
        for name in expected:
            assert name in NODE_REGISTRY, f"Node not registered: {name}"

    def test_genesis_conversation_flow_registered(self):
        from services.flow_engine import FLOW_REGISTRY
        from services.flow_definitions import register_all_flows
        register_all_flows()
        assert "genesis_conversation" in FLOW_REGISTRY

    def test_genesis_conversation_flow_structure(self):
        from services.flow_engine import FLOW_REGISTRY
        from services.flow_definitions import register_all_flows
        register_all_flows()
        flow = FLOW_REGISTRY["genesis_conversation"]
        assert flow["start"] == "genesis_validate_session"
        assert "genesis_validate_session" in flow["edges"]
        assert "genesis_record_exchange" in flow["edges"]
        assert flow["end"] == ["genesis_store_synthesis"]

    def test_genesis_conversation_has_conditional_edge(self):
        from services.flow_engine import FLOW_REGISTRY
        from services.flow_definitions import register_all_flows
        register_all_flows()
        flow = FLOW_REGISTRY["genesis_conversation"]
        edges = flow["edges"]["genesis_record_exchange"]
        assert len(edges) == 1
        assert isinstance(edges[0], dict)
        assert "condition" in edges[0]
        assert edges[0]["target"] == "genesis_store_synthesis"


class TestGenesisValidateSession:

    def test_passes_with_session_id(self):
        from services.flow_definitions import genesis_validate_session
        result = genesis_validate_session({"session_id": 42}, {"attempts": {}})
        assert result["status"] == "SUCCESS"

    def test_fails_without_session_id(self):
        from services.flow_definitions import genesis_validate_session
        result = genesis_validate_session({}, {"attempts": {}})
        assert result["status"] == "FAILURE"
        assert "session_id" in result["error"]


class TestGenesisRecordExchange:

    def test_returns_wait_when_not_ready(self):
        from services.flow_definitions import genesis_record_exchange
        result = genesis_record_exchange(
            {"session_id": 1, "synthesis_ready": False},
            {"attempts": {}},
        )
        assert result["status"] == "WAIT"
        assert result["wait_for"] == "genesis_user_message"

    def test_returns_wait_when_no_synthesis_ready_key(self):
        from services.flow_definitions import genesis_record_exchange
        result = genesis_record_exchange({"session_id": 1}, {"attempts": {}})
        assert result["status"] == "WAIT"
        assert result["wait_for"] == "genesis_user_message"

    def test_returns_success_when_ready_in_state(self):
        from services.flow_definitions import genesis_record_exchange
        result = genesis_record_exchange(
            {"session_id": 1, "synthesis_ready": True},
            {"attempts": {}},
        )
        assert result["status"] == "SUCCESS"
        assert result["output_patch"]["synthesis_ready"] is True

    def test_returns_success_when_ready_in_event(self):
        """After WAIT resume, synthesis_ready comes from state['event'] payload."""
        from services.flow_definitions import genesis_record_exchange
        state = {
            "session_id": 1,
            "synthesis_ready": False,
            "event": {"synthesis_ready": True},
        }
        result = genesis_record_exchange(state, {"attempts": {}})
        assert result["status"] == "SUCCESS"
        assert result["output_patch"]["synthesis_ready"] is True

    def test_conditional_edge_matches_when_ready(self):
        """The conditional edge lambda evaluates correctly for synthesis_ready."""
        from services.flow_engine import FLOW_REGISTRY
        from services.flow_definitions import register_all_flows
        register_all_flows()
        flow = FLOW_REGISTRY["genesis_conversation"]
        condition = flow["edges"]["genesis_record_exchange"][0]["condition"]

        # Not ready → condition False
        assert condition({"synthesis_ready": False}) is False
        assert condition({}) is False

        # Ready via state → condition True
        assert condition({"synthesis_ready": True}) is True

        # Ready via event payload → condition True
        assert condition({"event": {"synthesis_ready": True}}) is True


class TestGenesisStoreSynthesis:

    def test_returns_success_normally(self, mock_db):
        from services.flow_definitions import genesis_store_synthesis
        with patch("services.flow_definitions.logger"):
            result = genesis_store_synthesis(
                {"session_id": 1},
                {"db": None, "user_id": None, "attempts": {}},
            )
        assert result["status"] == "SUCCESS"

    def test_returns_success_even_on_exception(self, mock_db):
        """Storage failure is non-fatal — must return SUCCESS."""
        from services.flow_definitions import genesis_store_synthesis

        with patch(
            "services.memory_capture_engine.MemoryCaptureEngine",
            side_effect=Exception("DB down"),
        ):
            result = genesis_store_synthesis(
                {"session_id": 1},
                {"db": mock_db, "user_id": "u1", "attempts": {}},
            )
        assert result["status"] == "SUCCESS"
        assert result["output_patch"]["stored"] is False


class TestGenesisRouterIntegration:
    """Verify genesis_router.py has Phase C fire-and-forget block."""

    def _router_source(self):
        from pathlib import Path

        path = Path(__file__).resolve().parents[2] / "routes" / "genesis_router.py"
        return path.read_text(encoding="utf-8")

    def test_router_imports_logger(self):
        src = self._router_source()
        assert "import logging" in src

    def test_router_has_flow_engine_integration(self):
        src = self._router_source()
        assert "genesis_message" in src, (
            "genesis_router.py must reference genesis_message flow"
        )

    def test_router_uses_execute_intent(self):
        src = self._router_source()
        assert "execute_intent" in src, (
            "genesis_router.py must execute through execute_intent"
        )

    def test_router_sets_genesis_message_workflow_type(self):
        src = self._router_source()
        assert '"workflow_type": "genesis_message"' in src, (
            "genesis_router.py must set workflow_type to genesis_message"
        )

    def test_router_integration_fails_closed_on_flow_error(self):
        """Genesis message execution must fail closed if the canonical flow fails."""
        src = self._router_source()
        idx = src.index("genesis_message")
        block_area = src[max(0, idx - 200):idx + 2000]
        assert 'result.get("status") != "SUCCESS"' in block_area, (
            "genesis_router.py must enforce successful flow execution"
        )
        assert 'HTTPException(status_code=500, detail="Genesis message execution failed")' in block_area, (
            "genesis_router.py must fail closed on canonical flow failure"
        )

    def test_router_genesis_message_endpoint_still_returns_reply(
        self, client, auth_headers
    ):
        """Existing genesis/message behavior preserved — 400 for missing session."""
        r = client.post(
            "/genesis/message",
            json={"message": "hello"},
            headers=auth_headers,
        )
        assert r.status_code == 400


class TestGenesisWaitResumeRoundTrip:
    """WAIT/RESUME round-trip for genesis_conversation via mock DB."""

    @staticmethod
    def _create_flow_run(db_session, user_id, state, current_node):
        from db.models.flow_run import FlowRun

        run = FlowRun(
            id=str(uuid.uuid4()),
            flow_name="genesis_conversation",
            workflow_type="genesis_conversation",
            state=state,
            current_node=current_node,
            status="running",
            trace_id=str(uuid.uuid4()),
            user_id=user_id,
        )
        db_session.add(run)
        db_session.commit()
        db_session.refresh(run)
        return run

    def test_genesis_flow_starts_in_wait_state(self, db_session, test_user):
        """
        First message starts a genesis_conversation FlowRun.
        synthesis_ready=False → flow enters WAIT.
        """
        from services.flow_engine import FLOW_REGISTRY, PersistentFlowRunner
        from services.flow_definitions import register_all_flows
        register_all_flows()

        run = self._create_flow_run(
            db_session,
            user_id=test_user.id,
            state={"session_id": 1, "synthesis_ready": False},
            current_node="genesis_validate_session",
        )

        flow = FLOW_REGISTRY["genesis_conversation"]
        runner = PersistentFlowRunner(
            flow=flow,
            db=db_session,
            user_id=test_user.id,
            workflow_type="genesis_conversation",
        )
        result = runner.resume(run.id)

        assert result["status"] == "WAITING"
        assert result["result"]["waiting_for"] == "genesis_user_message"

    def test_genesis_flow_completes_when_synthesis_ready(self, db_session, test_user):
        """
        When synthesis_ready=True in state, genesis_record_exchange returns SUCCESS
        and the flow advances to genesis_store_synthesis (end node → SUCCESS).
        """
        from services.flow_engine import FLOW_REGISTRY, PersistentFlowRunner
        from services.flow_definitions import register_all_flows
        register_all_flows()

        run = self._create_flow_run(
            db_session,
            user_id=test_user.id,
            state={"session_id": 1, "synthesis_ready": True},
            current_node="genesis_validate_session",
        )

        flow = FLOW_REGISTRY["genesis_conversation"]
        runner = PersistentFlowRunner(
            flow=flow,
            db=db_session,
            user_id=test_user.id,
            workflow_type="genesis_conversation",
        )

        # genesis_record_exchange sees synthesis_ready=True → SUCCESS → store → end
        result = runner.resume(run.id)
        assert result["status"] == "SUCCESS"


# ══════════════════════════════════════════════════════════════════════════════
# PHASE D
# ══════════════════════════════════════════════════════════════════════════════


class TestFlowCompletionEventSignificance:

    def test_flow_completion_in_event_significance(self):
        from services.memory_capture_engine import EVENT_SIGNIFICANCE
        assert "flow_completion" in EVENT_SIGNIFICANCE, (
            "flow_completion must be in EVENT_SIGNIFICANCE for Phase D"
        )

    def test_flow_completion_significance_value(self):
        from services.memory_capture_engine import EVENT_SIGNIFICANCE
        score = EVENT_SIGNIFICANCE["flow_completion"]
        assert 0.3 <= score <= 1.0, (
            f"flow_completion significance must be between 0.3 and 1.0, got {score}"
        )


class TestCaptureFlowCompletionMethod:

    def test_method_exists_on_runner(self, db_session, test_user):
        from services.flow_engine import PersistentFlowRunner
        runner = PersistentFlowRunner(
            flow={"start": "n", "edges": {}, "end": ["n"]},
            db=db_session,
            user_id=test_user.id,
            workflow_type="arm_analysis",
        )
        assert hasattr(runner, "_capture_flow_completion"), (
            "PersistentFlowRunner must have _capture_flow_completion() method"
        )

    def test_skipped_when_no_user_id(self, db_session):
        """No user_id → capture skipped, no exception."""
        from services.flow_engine import PersistentFlowRunner
        runner = PersistentFlowRunner(
            flow={"start": "n", "edges": {}, "end": ["n"]},
            db=db_session,
            user_id=None,
            workflow_type="arm_analysis",
        )
        mock_run = _make_mock_run()
        runner._capture_flow_completion(mock_run, {})

    def test_skipped_when_no_workflow_type(self, db_session, test_user):
        """No workflow_type → capture skipped, no exception."""
        from services.flow_engine import PersistentFlowRunner
        runner = PersistentFlowRunner(
            flow={"start": "n", "edges": {}, "end": ["n"]},
            db=db_session,
            user_id=test_user.id,
            workflow_type=None,
        )
        mock_run = _make_mock_run()
        runner._capture_flow_completion(mock_run, {})

    def test_non_fatal_when_memory_capture_raises(self, db_session, test_user):
        """Exception in MemoryCaptureEngine must not propagate."""
        from services.flow_engine import PersistentFlowRunner

        runner = PersistentFlowRunner(
            flow={"start": "n", "edges": {}, "end": ["n"]},
            db=db_session,
            user_id=test_user.id,
            workflow_type="arm_analysis",
        )
        mock_run = _make_mock_run(run_id=str(uuid.uuid4()))
        _seed_flow_history(
            db_session,
            mock_run.id,
            entries=[{"node_name": "test_node", "status": "SUCCESS", "execution_time_ms": 100}],
        )

        with patch(
            "services.memory_capture_engine.MemoryCaptureEngine",
            side_effect=Exception("capture failed"),
        ):
            runner._capture_flow_completion(mock_run, {})

    def test_skipped_when_no_history(self, db_session, test_user):
        """Empty FlowHistory → capture skipped gracefully."""
        from services.flow_engine import PersistentFlowRunner

        runner = PersistentFlowRunner(
            flow={"start": "n", "edges": {}, "end": ["n"]},
            db=db_session,
            user_id=test_user.id,
            workflow_type="arm_analysis",
        )
        mock_run = _make_mock_run(run_id=str(uuid.uuid4()))

        with patch("services.memory_capture_engine.MemoryCaptureEngine") as mock_engine:
            runner._capture_flow_completion(mock_run, {})
            mock_engine.assert_not_called()


class TestCaptureFlowCompletionEventTypeMapping:
    """Correct event_type is passed to MemoryCaptureEngine for each workflow."""

    def _run_capture(self, workflow_type, db_session, test_user):
        from services.flow_engine import PersistentFlowRunner

        runner = PersistentFlowRunner(
            flow={"start": "n", "edges": {}, "end": ["n"]},
            db=db_session,
            user_id=test_user.id,
            workflow_type=workflow_type,
        )
        mock_run = _make_mock_run(run_id=str(uuid.uuid4()))
        mock_run.flow_name = "test_flow"
        _seed_flow_history(
            db_session,
            mock_run.id,
            entries=[{"node_name": "node_a", "status": "SUCCESS", "execution_time_ms": 200}],
        )

        captured_calls = []

        class _MockEngine:
            def __init__(self, **kwargs):
                pass

            def evaluate_and_capture(self, **kwargs):
                captured_calls.append(kwargs)

        # MemoryCaptureEngine is imported lazily inside _capture_flow_completion.
        # Patch at the source module so the lazy import picks up the mock.
        with patch("services.memory_capture_engine.MemoryCaptureEngine", _MockEngine):
            runner._capture_flow_completion(mock_run, {})

        return captured_calls

    def test_arm_analysis_maps_to_arm_analysis_complete(self, db_session, test_user):
        calls = self._run_capture("arm_analysis", db_session, test_user)
        assert calls, "MemoryCaptureEngine.evaluate_and_capture not called"
        assert calls[0]["event_type"] == "arm_analysis_complete"

    def test_task_completion_maps_to_task_completed(self, db_session, test_user):
        calls = self._run_capture("task_completion", db_session, test_user)
        assert calls
        assert calls[0]["event_type"] == "task_completed"

    def test_leadgen_search_maps_to_leadgen_search(self, db_session, test_user):
        calls = self._run_capture("leadgen_search", db_session, test_user)
        assert calls
        assert calls[0]["event_type"] == "leadgen_search"

    def test_genesis_conversation_maps_to_genesis_synthesized(self, db_session, test_user):
        calls = self._run_capture("genesis_conversation", db_session, test_user)
        assert calls
        assert calls[0]["event_type"] == "genesis_synthesized"

    def test_unknown_workflow_maps_to_flow_completion(self, db_session, test_user):
        calls = self._run_capture("custom_workflow", db_session, test_user)
        assert calls
        assert calls[0]["event_type"] == "flow_completion"

    def test_capture_includes_flow_history_tags(self, db_session, test_user):
        calls = self._run_capture("arm_analysis", db_session, test_user)
        assert calls
        tags = calls[0]["tags"]
        assert "flow_history" in tags
        assert "execution_pattern" in tags

    def test_capture_source_includes_flow_name(self, db_session, test_user):
        calls = self._run_capture("arm_analysis", db_session, test_user)
        assert calls
        assert "flow_history:" in calls[0]["source"]

    def test_content_includes_node_summary(self, db_session, test_user):
        calls = self._run_capture("arm_analysis", db_session, test_user)
        assert calls
        content = calls[0]["content"]
        assert "node_a" in content
        assert "200ms" in content


class TestPhaseDAuto:
    """Phase D fires automatically on flow SUCCESS in PersistentFlowRunner."""

    @staticmethod
    def _create_run(db_session, user_id, current_node):
        from db.models.flow_run import FlowRun

        run = FlowRun(
            id=str(uuid.uuid4()),
            flow_name="test_flow",
            workflow_type="arm_analysis",
            state={},
            current_node=current_node,
            status="running",
            trace_id=str(uuid.uuid4()),
            user_id=user_id,
        )
        db_session.add(run)
        db_session.commit()
        db_session.refresh(run)
        return run

    def test_capture_called_on_success(self, db_session, test_user):
        """_capture_flow_completion must be called when flow reaches end node."""
        from services.flow_engine import PersistentFlowRunner, register_node

        @register_node("phase_d_success_node")
        def success_node(state, context):
            return {"status": "SUCCESS", "output_patch": {}}

        run = self._create_run(db_session, test_user.id, "phase_d_success_node")

        flow = {
            "start": "phase_d_success_node",
            "edges": {},
            "end": ["phase_d_success_node"],
        }
        runner = PersistentFlowRunner(
            flow=flow,
            db=db_session,
            user_id=test_user.id,
            workflow_type="arm_analysis",
        )

        with patch.object(
            runner, "_capture_flow_completion", wraps=runner._capture_flow_completion
        ) as mock_capture:
            result = runner.resume(run.id)

        assert result["status"] == "SUCCESS"
        mock_capture.assert_called_once()

    def test_capture_not_called_on_failure(self, db_session, test_user):
        """_capture_flow_completion must NOT be called when flow fails."""
        from services.flow_engine import PersistentFlowRunner, register_node

        @register_node("phase_d_fail_node")
        def fail_node(state, context):
            return {"status": "FAILURE", "error": "intentional"}

        run = self._create_run(db_session, test_user.id, "phase_d_fail_node")

        flow = {
            "start": "phase_d_fail_node",
            "edges": {},
            "end": ["phase_d_fail_node"],
        }
        runner = PersistentFlowRunner(
            flow=flow,
            db=db_session,
            user_id=test_user.id,
            workflow_type="arm_analysis",
        )

        with patch.object(runner, "_capture_flow_completion") as mock_capture:
            result = runner.resume(run.id)

        assert result["status"] == "FAILED"
        mock_capture.assert_not_called()
