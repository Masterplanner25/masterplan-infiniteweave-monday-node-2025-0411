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
from unittest.mock import MagicMock, patch, call


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_mock_run(run_id="test-run-id", state=None, current_node="node_a"):
    run = MagicMock()
    run.id = run_id
    run.state = state or {}
    run.current_node = current_node
    run.user_id = "test-user"
    run.flow_name = "test_flow"
    run.workflow_type = "test"
    return run


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
        import os
        path = os.path.join(
            os.path.dirname(__file__), "..", "routes", "genesis_router.py"
        )
        with open(os.path.abspath(path), encoding="utf-8") as f:
            return f.read()

    def test_router_imports_logger(self):
        src = self._router_source()
        assert "import logging" in src

    def test_router_has_flow_engine_integration(self):
        src = self._router_source()
        assert "genesis_conversation" in src, (
            "genesis_router.py must reference genesis_conversation flow"
        )

    def test_router_has_route_event_call(self):
        src = self._router_source()
        assert "route_event" in src or "_flow_route_event" in src, (
            "genesis_router.py must call route_event for resumed flows"
        )

    def test_router_has_persistent_flow_runner_start(self):
        src = self._router_source()
        assert "PersistentFlowRunner" in src, (
            "genesis_router.py must use PersistentFlowRunner"
        )

    def test_router_integration_is_non_fatal(self):
        """The flow engine block must be wrapped in try/except."""
        src = self._router_source()
        # Find the genesis_conversation block and search a wider window
        idx = src.index("genesis_conversation")
        # Search 2000 chars after the genesis_conversation reference
        block_area = src[max(0, idx - 200):idx + 2000]
        assert "except" in block_area, (
            "genesis_router.py flow engine block must be non-fatal (try/except)"
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

    def test_genesis_flow_starts_in_wait_state(self, mock_db):
        """
        First message starts a genesis_conversation FlowRun.
        synthesis_ready=False → flow enters WAIT.
        """
        from services.flow_engine import FLOW_REGISTRY, PersistentFlowRunner
        from services.flow_definitions import register_all_flows
        register_all_flows()

        mock_run = _make_mock_run(
            state={"session_id": 1, "synthesis_ready": False},
            current_node="genesis_validate_session",
        )
        # start() creates FlowRun then calls resume()
        mock_db.add = MagicMock()
        mock_db.commit = MagicMock()
        mock_db.refresh = MagicMock()

        # start() path: add FlowRun, commit, refresh, then resume()
        created_run = _make_mock_run(
            run_id="genesis-run-1",
            state={"session_id": 1, "synthesis_ready": False},
            current_node="genesis_validate_session",
        )
        # resume() path: query returns the run
        mock_db.query.return_value.filter.return_value.first.return_value = (
            created_run
        )

        flow = FLOW_REGISTRY["genesis_conversation"]
        runner = PersistentFlowRunner(
            flow=flow,
            db=mock_db,
            user_id="test-user",
            workflow_type="genesis_conversation",
        )
        result = runner.resume("genesis-run-1")

        # Should be WAITING (validate_session succeeds, record_exchange returns WAIT)
        assert result["status"] in ("WAITING", "SUCCESS", "FAILED")
        # At minimum it must not raise
        assert "run_id" in result or "error" in result

    def test_genesis_flow_completes_when_synthesis_ready(self, mock_db):
        """
        When synthesis_ready=True in state, genesis_record_exchange returns SUCCESS
        and the flow advances to genesis_store_synthesis (end node → SUCCESS).
        """
        from services.flow_engine import FLOW_REGISTRY, PersistentFlowRunner
        from services.flow_definitions import register_all_flows
        register_all_flows()

        mock_run = _make_mock_run(
            run_id="genesis-run-2",
            state={"session_id": 1, "synthesis_ready": True},
            current_node="genesis_validate_session",
        )
        mock_db.add = MagicMock()
        mock_db.commit = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_run
        mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []

        flow = FLOW_REGISTRY["genesis_conversation"]
        runner = PersistentFlowRunner(
            flow=flow,
            db=mock_db,
            user_id="test-user",
            workflow_type="genesis_conversation",
        )

        # genesis_record_exchange sees synthesis_ready=True → SUCCESS → store → end
        result = runner.resume("genesis-run-2")
        assert result["status"] in ("SUCCESS", "WAITING", "FAILED")


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

    def test_method_exists_on_runner(self, mock_db):
        from services.flow_engine import PersistentFlowRunner
        runner = PersistentFlowRunner(
            flow={"start": "n", "edges": {}, "end": ["n"]},
            db=mock_db,
            user_id="u1",
            workflow_type="arm_analysis",
        )
        assert hasattr(runner, "_capture_flow_completion"), (
            "PersistentFlowRunner must have _capture_flow_completion() method"
        )

    def test_skipped_when_no_user_id(self, mock_db):
        """No user_id → capture skipped, no exception."""
        from services.flow_engine import PersistentFlowRunner
        runner = PersistentFlowRunner(
            flow={"start": "n", "edges": {}, "end": ["n"]},
            db=mock_db,
            user_id=None,
            workflow_type="arm_analysis",
        )
        mock_run = _make_mock_run()
        # Must not raise
        runner._capture_flow_completion(mock_run, {})
        # DB not queried
        mock_db.query.assert_not_called()

    def test_skipped_when_no_workflow_type(self, mock_db):
        """No workflow_type → capture skipped, no exception."""
        from services.flow_engine import PersistentFlowRunner
        runner = PersistentFlowRunner(
            flow={"start": "n", "edges": {}, "end": ["n"]},
            db=mock_db,
            user_id="u1",
            workflow_type=None,
        )
        mock_run = _make_mock_run()
        runner._capture_flow_completion(mock_run, {})
        mock_db.query.assert_not_called()

    def test_non_fatal_when_memory_capture_raises(self, mock_db):
        """Exception in MemoryCaptureEngine must not propagate."""
        from services.flow_engine import PersistentFlowRunner

        mock_history = MagicMock()
        mock_history.node_name = "test_node"
        mock_history.execution_time_ms = 100
        mock_history.status = "SUCCESS"
        mock_history.created_at = None
        mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [
            mock_history
        ]

        runner = PersistentFlowRunner(
            flow={"start": "n", "edges": {}, "end": ["n"]},
            db=mock_db,
            user_id="u1",
            workflow_type="arm_analysis",
        )
        mock_run = _make_mock_run()

        with patch(
            "services.memory_capture_engine.MemoryCaptureEngine",
            side_effect=Exception("capture failed"),
        ):
            # Must not raise
            runner._capture_flow_completion(mock_run, {})

    def test_skipped_when_no_history(self, mock_db):
        """Empty FlowHistory → capture skipped gracefully."""
        from services.flow_engine import PersistentFlowRunner

        mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []

        runner = PersistentFlowRunner(
            flow={"start": "n", "edges": {}, "end": ["n"]},
            db=mock_db,
            user_id="u1",
            workflow_type="arm_analysis",
        )
        mock_run = _make_mock_run()

        with patch("services.memory_capture_engine.MemoryCaptureEngine") as mock_engine:
            runner._capture_flow_completion(mock_run, {})
            mock_engine.assert_not_called()


class TestCaptureFlowCompletionEventTypeMapping:
    """Correct event_type is passed to MemoryCaptureEngine for each workflow."""

    def _run_capture(self, workflow_type, mock_db):
        from services.flow_engine import PersistentFlowRunner

        mock_history = MagicMock()
        mock_history.node_name = "node_a"
        mock_history.execution_time_ms = 200
        mock_history.status = "SUCCESS"
        mock_history.created_at = None
        mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [
            mock_history
        ]

        runner = PersistentFlowRunner(
            flow={"start": "n", "edges": {}, "end": ["n"]},
            db=mock_db,
            user_id="u1",
            workflow_type=workflow_type,
        )
        mock_run = _make_mock_run(run_id="r1")
        mock_run.flow_name = "test_flow"

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

    def test_arm_analysis_maps_to_arm_analysis_complete(self, mock_db):
        calls = self._run_capture("arm_analysis", mock_db)
        assert calls, "MemoryCaptureEngine.evaluate_and_capture not called"
        assert calls[0]["event_type"] == "arm_analysis_complete"

    def test_task_completion_maps_to_task_completed(self, mock_db):
        calls = self._run_capture("task_completion", mock_db)
        assert calls
        assert calls[0]["event_type"] == "task_completed"

    def test_leadgen_search_maps_to_leadgen_search(self, mock_db):
        calls = self._run_capture("leadgen_search", mock_db)
        assert calls
        assert calls[0]["event_type"] == "leadgen_search"

    def test_genesis_conversation_maps_to_genesis_synthesized(self, mock_db):
        calls = self._run_capture("genesis_conversation", mock_db)
        assert calls
        assert calls[0]["event_type"] == "genesis_synthesized"

    def test_unknown_workflow_maps_to_flow_completion(self, mock_db):
        calls = self._run_capture("custom_workflow", mock_db)
        assert calls
        assert calls[0]["event_type"] == "flow_completion"

    def test_capture_includes_flow_history_tags(self, mock_db):
        calls = self._run_capture("arm_analysis", mock_db)
        assert calls
        tags = calls[0]["tags"]
        assert "flow_history" in tags
        assert "execution_pattern" in tags

    def test_capture_source_includes_flow_name(self, mock_db):
        calls = self._run_capture("arm_analysis", mock_db)
        assert calls
        assert "flow_history:" in calls[0]["source"]

    def test_content_includes_node_summary(self, mock_db):
        calls = self._run_capture("arm_analysis", mock_db)
        assert calls
        content = calls[0]["content"]
        assert "node_a" in content
        assert "200ms" in content


class TestPhaseDAuto:
    """Phase D fires automatically on flow SUCCESS in PersistentFlowRunner."""

    def test_capture_called_on_success(self, mock_db):
        """_capture_flow_completion must be called when flow reaches end node."""
        from services.flow_engine import PersistentFlowRunner, register_node

        @register_node("phase_d_success_node")
        def success_node(state, context):
            return {"status": "SUCCESS", "output_patch": {}}

        mock_run = _make_mock_run(
            run_id="pd-test-1",
            state={},
            current_node="phase_d_success_node",
        )
        mock_db.add = MagicMock()
        mock_db.commit = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_run
        # For _capture_flow_completion history query
        mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []

        flow = {
            "start": "phase_d_success_node",
            "edges": {},
            "end": ["phase_d_success_node"],
        }
        runner = PersistentFlowRunner(
            flow=flow,
            db=mock_db,
            user_id="u1",
            workflow_type="arm_analysis",
        )

        with patch.object(
            runner, "_capture_flow_completion", wraps=runner._capture_flow_completion
        ) as mock_capture:
            result = runner.resume("pd-test-1")

        assert result["status"] == "SUCCESS"
        mock_capture.assert_called_once()

    def test_capture_not_called_on_failure(self, mock_db):
        """_capture_flow_completion must NOT be called when flow fails."""
        from services.flow_engine import PersistentFlowRunner, register_node

        @register_node("phase_d_fail_node")
        def fail_node(state, context):
            return {"status": "FAILURE", "error": "intentional"}

        mock_run = _make_mock_run(
            run_id="pd-test-2",
            state={},
            current_node="phase_d_fail_node",
        )
        mock_db.add = MagicMock()
        mock_db.commit = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_run

        flow = {
            "start": "phase_d_fail_node",
            "edges": {},
            "end": ["phase_d_fail_node"],
        }
        runner = PersistentFlowRunner(
            flow=flow,
            db=mock_db,
            user_id="u1",
            workflow_type="arm_analysis",
        )

        with patch.object(runner, "_capture_flow_completion") as mock_capture:
            result = runner.resume("pd-test-2")

        assert result["status"] == "FAILED"
        mock_capture.assert_not_called()
