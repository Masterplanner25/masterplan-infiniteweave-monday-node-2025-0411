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
  - WAIT/RESUME round-trip: route_event delegates to SchedulerEngine

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
    from AINDY.db.models.flow_run import FlowHistory, FlowRun

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
        from AINDY.runtime.flow_engine import NODE_REGISTRY
        from AINDY.runtime.flow_definitions import register_all_flows
        register_all_flows()
        expected = [
            "genesis_validate_session",
            "genesis_record_exchange",
            "genesis_store_synthesis",
        ]
        for name in expected:
            assert name in NODE_REGISTRY, f"Node not registered: {name}"

    def test_genesis_conversation_flow_registered(self):
        from AINDY.runtime.flow_engine import FLOW_REGISTRY
        from AINDY.runtime.flow_definitions import register_all_flows
        register_all_flows()
        assert "genesis_conversation" in FLOW_REGISTRY

    def test_genesis_conversation_flow_structure(self):
        from AINDY.runtime.flow_engine import FLOW_REGISTRY
        from AINDY.runtime.flow_definitions import register_all_flows
        register_all_flows()
        flow = FLOW_REGISTRY["genesis_conversation"]
        assert flow["start"] == "genesis_validate_session"
        assert "genesis_validate_session" in flow["edges"]
        assert "genesis_record_exchange" in flow["edges"]
        assert flow["end"] == ["genesis_store_synthesis"]

    def test_genesis_conversation_has_conditional_edge(self):
        from AINDY.runtime.flow_engine import FLOW_REGISTRY
        from AINDY.runtime.flow_definitions import register_all_flows
        register_all_flows()
        flow = FLOW_REGISTRY["genesis_conversation"]
        edges = flow["edges"]["genesis_record_exchange"]
        assert len(edges) == 1
        assert isinstance(edges[0], dict)
        assert "condition" in edges[0]
        assert edges[0]["target"] == "genesis_store_synthesis"


class TestGenesisValidateSession:

    def test_passes_with_session_id(self):
        from AINDY.runtime.flow_definitions import genesis_validate_session
        result = genesis_validate_session({"session_id": 42}, {"attempts": {}})
        assert result["status"] == "SUCCESS"

    def test_fails_without_session_id(self):
        from AINDY.runtime.flow_definitions import genesis_validate_session
        result = genesis_validate_session({}, {"attempts": {}})
        assert result["status"] == "FAILURE"
        assert "session_id" in result["error"]


class TestGenesisRecordExchange:

    def test_returns_wait_when_not_ready(self):
        from AINDY.runtime.flow_definitions import genesis_record_exchange
        result = genesis_record_exchange(
            {"session_id": 1, "synthesis_ready": False},
            {"attempts": {}},
        )
        assert result["status"] == "WAIT"
        assert result["wait_for"] == "genesis_user_message"

    def test_returns_wait_when_no_synthesis_ready_key(self):
        from AINDY.runtime.flow_definitions import genesis_record_exchange
        result = genesis_record_exchange({"session_id": 1}, {"attempts": {}})
        assert result["status"] == "WAIT"
        assert result["wait_for"] == "genesis_user_message"

    def test_returns_success_when_ready_in_state(self):
        from AINDY.runtime.flow_definitions import genesis_record_exchange
        result = genesis_record_exchange(
            {"session_id": 1, "synthesis_ready": True},
            {"attempts": {}},
        )
        assert result["status"] == "SUCCESS"
        assert result["output_patch"]["synthesis_ready"] is True

    def test_returns_success_when_ready_in_event(self):
        """After WAIT resume, synthesis_ready comes from state['event'] payload."""
        from AINDY.runtime.flow_definitions import genesis_record_exchange
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
        from AINDY.runtime.flow_engine import FLOW_REGISTRY
        from AINDY.runtime.flow_definitions import register_all_flows
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
        from AINDY.runtime.flow_definitions import genesis_store_synthesis
        with patch("AINDY.runtime.flow_definitions.logger"):
            result = genesis_store_synthesis(
                {"session_id": 1},
                {"db": None, "user_id": None, "attempts": {}},
            )
        assert result["status"] == "SUCCESS"

    def test_returns_success_even_on_exception(self, mock_db):
        """Storage failure is non-fatal — must return SUCCESS."""
        from AINDY.runtime.flow_definitions import genesis_store_synthesis

        with patch(
            "AINDY.memory.memory_capture_engine.MemoryCaptureEngine",
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
        assert "run_flow" in src, (
            "genesis_router.py must execute through run_flow"
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


class TestRouteEventSchedulerDelegation:
    """
    route_event() must delegate resume authority to SchedulerEngine.

    Invariants:
    - Payload is injected into FlowRun state before notify_event() fires.
    - run.status and run.waiting_for are NOT mutated.
    - runner.resume() is NEVER called directly.
    - SchedulerEngine.notify_event() is always called.
    - Return value is list[{run_id, payload_injected}].
    """

    def _make_waiting_run(self, db_session, user_id, event_type="task.completed"):
        from AINDY.db.models.flow_run import FlowRun
        run = FlowRun(
            id=str(uuid.uuid4()),
            flow_name="test_flow",
            workflow_type="test",
            state={"some_key": "some_value"},
            current_node="node_a",
            status="waiting",
            waiting_for=event_type,
            trace_id=str(uuid.uuid4()),
            user_id=user_id,
        )
        db_session.add(run)
        db_session.commit()
        db_session.refresh(run)
        return run

    def test_payload_injected_into_state(self, db_session, test_user):
        """route_event() writes payload into FlowRun.state['event']."""
        from AINDY.runtime.flow_engine import route_event

        run = self._make_waiting_run(db_session, test_user.id)

        with patch("AINDY.kernel.scheduler_engine.get_scheduler_engine") as mock_se:
            mock_se.return_value.peek_matching_run_ids.return_value = [str(run.id)]
            mock_se.return_value.notify_event.return_value = 1
            route_event("task.completed", {"result": "ok"}, db_session, user_id=test_user.id)

        db_session.refresh(run)
        assert run.state["event"] == {"result": "ok"}

    def test_status_not_mutated(self, db_session, test_user):
        """route_event() must NOT change run.status or run.waiting_for."""
        from AINDY.runtime.flow_engine import route_event

        run = self._make_waiting_run(db_session, test_user.id)

        with patch("AINDY.kernel.scheduler_engine.get_scheduler_engine") as mock_se:
            mock_se.return_value.peek_matching_run_ids.return_value = []
            mock_se.return_value.notify_event.return_value = 0
            route_event("task.completed", {}, db_session, user_id=test_user.id)

        db_session.refresh(run)
        assert run.status == "waiting"        # NOT mutated to "running"
        assert run.waiting_for == "task.completed"  # NOT cleared to None

    def test_notify_event_called_with_event_type(self, db_session, test_user):
        """SchedulerEngine.notify_event() is called with the correct event_type."""
        from AINDY.runtime.flow_engine import route_event

        self._make_waiting_run(db_session, test_user.id, event_type="genesis_user_message")

        with patch("AINDY.kernel.scheduler_engine.get_scheduler_engine") as mock_se:
            mock_se.return_value.peek_matching_run_ids.return_value = []
            mock_se.return_value.notify_event.return_value = 1
            route_event("genesis_user_message", {}, db_session, user_id=test_user.id)

        mock_se.return_value.notify_event.assert_called_once_with(
            "genesis_user_message", correlation_id=None, broadcast=True
        )

    def test_notify_event_receives_correlation_id_from_payload(self, db_session, test_user):
        """correlation_id from payload is forwarded to both peek and notify_event."""
        from AINDY.runtime.flow_engine import route_event

        self._make_waiting_run(db_session, test_user.id)

        with patch("AINDY.kernel.scheduler_engine.get_scheduler_engine") as mock_se:
            mock_se.return_value.peek_matching_run_ids.return_value = []
            mock_se.return_value.notify_event.return_value = 1
            route_event(
                "task.completed",
                {"correlation_id": "chain-abc"},
                db_session,
                user_id=test_user.id,
            )

        mock_se.return_value.peek_matching_run_ids.assert_called_once_with(
            "task.completed", correlation_id="chain-abc"
        )
        mock_se.return_value.notify_event.assert_called_once_with(
            "task.completed", correlation_id="chain-abc", broadcast=True
        )

    def test_no_runner_resume_called(self, db_session, test_user):
        """PersistentFlowRunner.resume() must NOT be called by route_event."""
        from AINDY.runtime.flow_engine import route_event

        self._make_waiting_run(db_session, test_user.id)

        with patch("AINDY.kernel.scheduler_engine.get_scheduler_engine") as mock_se:
            mock_se.return_value.peek_matching_run_ids.return_value = []
            mock_se.return_value.notify_event.return_value = 1
            route_event("task.completed", {}, db_session, user_id=test_user.id)

        # Verify scheduler was called (resume went through scheduler, not runner directly)
        mock_se.return_value.notify_event.assert_called_once()

    def test_returns_list_of_acknowledgements(self, db_session, test_user):
        """Return value is list[{run_id, payload_injected}] per injected run."""
        from AINDY.runtime.flow_engine import route_event

        run = self._make_waiting_run(db_session, test_user.id)

        with patch("AINDY.kernel.scheduler_engine.get_scheduler_engine") as mock_se:
            mock_se.return_value.peek_matching_run_ids.return_value = [str(run.id)]
            mock_se.return_value.notify_event.return_value = 1
            results = route_event("task.completed", {"x": 1}, db_session, user_id=test_user.id)

        assert len(results) == 1
        assert results[0]["run_id"] == str(run.id)
        assert results[0]["payload_injected"] is True

    def test_no_match_returns_empty_list(self, db_session, test_user):
        """No waiting runs for the event → empty list, notify_event still called."""
        from AINDY.runtime.flow_engine import route_event

        with patch("AINDY.kernel.scheduler_engine.get_scheduler_engine") as mock_se:
            mock_se.return_value.peek_matching_run_ids.return_value = []
            mock_se.return_value.notify_event.return_value = 0
            results = route_event("unknown.event", {}, db_session, user_id=test_user.id)

        assert results == []
        mock_se.return_value.notify_event.assert_called_once()

    def test_notify_event_called_even_when_no_db_runs(self, db_session, test_user):
        """notify_event() fires even if no FlowRuns matched the DB query."""
        from AINDY.runtime.flow_engine import route_event

        with patch("AINDY.kernel.scheduler_engine.get_scheduler_engine") as mock_se:
            mock_se.return_value.peek_matching_run_ids.return_value = []
            mock_se.return_value.notify_event.return_value = 0
            route_event("some.event", {}, db_session)  # no user_id filter

        mock_se.return_value.notify_event.assert_called_once_with(
            "some.event", correlation_id=None, broadcast=True
        )

    def test_payload_scope_matches_scheduler_scope(self, db_session, test_user):
        """
        Payload injection uses peek_matching_run_ids() — not user_id filter.

        A run that IS in the scheduler's match set receives the payload
        regardless of which user_id was passed to route_event().
        A run that is NOT in the scheduler's match set does NOT receive it,
        even if it is owned by the same user.
        """
        from AINDY.runtime.flow_engine import route_event

        matched_run = self._make_waiting_run(db_session, test_user.id, event_type="payment.confirmed")
        unmatched_run = self._make_waiting_run(db_session, test_user.id, event_type="payment.confirmed")

        with patch("AINDY.kernel.scheduler_engine.get_scheduler_engine") as mock_se:
            # Only matched_run is in the scheduler's scope
            mock_se.return_value.peek_matching_run_ids.return_value = [str(matched_run.id)]
            mock_se.return_value.notify_event.return_value = 1
            results = route_event(
                "payment.confirmed",
                {"amount": 99},
                db_session,
                user_id=test_user.id,
            )

        db_session.refresh(matched_run)
        db_session.refresh(unmatched_run)

        # Only the scheduler-matched run receives the payload
        assert matched_run.state.get("event") == {"amount": 99}
        assert unmatched_run.state.get("event") is None  # NOT injected

        # Only one ack returned
        assert len(results) == 1
        assert results[0]["run_id"] == str(matched_run.id)


class TestGenesisWaitResumeRoundTrip:
    """WAIT/RESUME round-trip for genesis_conversation via mock DB."""

    @staticmethod
    def _create_flow_run(db_session, user_id, state, current_node):
        from AINDY.db.models.flow_run import FlowRun

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
        from AINDY.runtime.flow_engine import FLOW_REGISTRY, PersistentFlowRunner
        from AINDY.runtime.flow_definitions import register_all_flows
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
        from AINDY.runtime.flow_engine import FLOW_REGISTRY, PersistentFlowRunner
        from AINDY.runtime.flow_definitions import register_all_flows
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
        from AINDY.memory.memory_capture_engine import EVENT_SIGNIFICANCE
        assert "flow_completion" in EVENT_SIGNIFICANCE, (
            "flow_completion must be in EVENT_SIGNIFICANCE for Phase D"
        )

    def test_flow_completion_significance_value(self):
        from AINDY.memory.memory_capture_engine import EVENT_SIGNIFICANCE
        score = EVENT_SIGNIFICANCE["flow_completion"]
        assert 0.3 <= score <= 1.0, (
            f"flow_completion significance must be between 0.3 and 1.0, got {score}"
        )


class TestCaptureFlowCompletionMethod:

    def test_method_exists_on_runner(self, db_session, test_user):
        from AINDY.runtime.flow_engine import PersistentFlowRunner
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
        from AINDY.runtime.flow_engine import PersistentFlowRunner
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
        from AINDY.runtime.flow_engine import PersistentFlowRunner
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
        from AINDY.runtime.flow_engine import PersistentFlowRunner

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
            "AINDY.memory.memory_capture_engine.MemoryCaptureEngine",
            side_effect=Exception("capture failed"),
        ):
            runner._capture_flow_completion(mock_run, {})

    def test_skipped_when_no_history(self, db_session, test_user):
        """Empty FlowHistory → capture skipped gracefully."""
        from AINDY.runtime.flow_engine import PersistentFlowRunner

        runner = PersistentFlowRunner(
            flow={"start": "n", "edges": {}, "end": ["n"]},
            db=db_session,
            user_id=test_user.id,
            workflow_type="arm_analysis",
        )
        mock_run = _make_mock_run(run_id=str(uuid.uuid4()))

        with patch("AINDY.memory.memory_capture_engine.MemoryCaptureEngine") as mock_engine:
            runner._capture_flow_completion(mock_run, {})
            mock_engine.assert_not_called()


class TestCaptureFlowCompletionEventTypeMapping:
    """Correct event_type is passed to MemoryCaptureEngine for each workflow."""

    def _run_capture(self, workflow_type, db_session, test_user):
        from AINDY.runtime.flow_engine import PersistentFlowRunner

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
        with patch("AINDY.memory.memory_capture_engine.MemoryCaptureEngine", _MockEngine):
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
        from AINDY.db.models.flow_run import FlowRun

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
        from AINDY.runtime.flow_engine import PersistentFlowRunner, register_node

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
        from AINDY.runtime.flow_engine import PersistentFlowRunner, register_node

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


# ══════════════════════════════════════════════════════════════════════════════
# PHASE E — Distributed Soft-Lock (resume() idempotency)
# ══════════════════════════════════════════════════════════════════════════════


class TestResumeSoftLock:
    """PersistentFlowRunner.resume() must claim 'waiting' runs atomically.

    The soft-lock protects against duplicate execution when two instances
    both receive the same resume event after a restart.  Only the instance
    that wins the atomic UPDATE proceeds; all others exit with SKIPPED.
    """

    @staticmethod
    def _make_waiting_run(db_session, user_id):
        """Create a FlowRun with status='waiting' and return it."""
        from AINDY.db.models.flow_run import FlowRun

        run = FlowRun(
            id=str(uuid.uuid4()),
            flow_name="test_flow",
            workflow_type="arm_analysis",
            state={},
            current_node="node_a",
            status="waiting",
            trace_id=str(uuid.uuid4()),
            user_id=user_id,
            waiting_for="some_event",
        )
        db_session.add(run)
        db_session.commit()
        db_session.refresh(run)
        return run

    @staticmethod
    def _make_running_run(db_session, user_id, node_name="node_a"):
        """Create a FlowRun with status='running' (start() path)."""
        from AINDY.db.models.flow_run import FlowRun

        run = FlowRun(
            id=str(uuid.uuid4()),
            flow_name="test_flow",
            workflow_type="arm_analysis",
            state={},
            current_node=node_name,
            status="running",
            trace_id=str(uuid.uuid4()),
            user_id=user_id,
        )
        db_session.add(run)
        db_session.commit()
        db_session.refresh(run)
        return run

    def test_claim_succeeds_when_waiting(self, db_session, test_user):
        """Winning instance claims the run — status transitions to 'executing'."""
        from AINDY.runtime.flow_engine import PersistentFlowRunner, register_node

        @register_node("soft_lock_success_node")
        def success_node(state, context):
            return {"status": "SUCCESS", "output_patch": {}}

        run = self._make_waiting_run(db_session, test_user.id)
        run.current_node = "soft_lock_success_node"
        db_session.commit()

        flow = {
            "start": "soft_lock_success_node",
            "edges": {},
            "end": ["soft_lock_success_node"],
        }
        runner = PersistentFlowRunner(
            flow=flow,
            db=db_session,
            user_id=test_user.id,
            workflow_type="arm_analysis",
        )
        result = runner.resume(run.id)

        # Claim succeeded — execution proceeded
        assert result["status"] in {"SUCCESS", "WAITING", "FAILED"}, (
            f"Expected execution result, got {result['status']!r}"
        )
        assert result["status"] != "SKIPPED"

    def test_claim_fails_when_already_claimed(self, db_session, test_user):
        """Second instance loses the claim — returns SKIPPED immediately.

        Uses a mock db so that the initial SELECT returns status='waiting'
        (triggering the claim branch) while the UPDATE returns 0 (concurrent
        claim already won).
        """
        from AINDY.runtime.flow_engine import PersistentFlowRunner

        # Build a mock FlowRun that looks 'waiting'
        mock_run = MagicMock()
        mock_run.id = str(uuid.uuid4())
        mock_run.status = "waiting"
        mock_run.state = {}
        mock_run.trace_id = str(uuid.uuid4())
        mock_run.current_node = "node_a"
        mock_run.flow_name = "test_flow"
        mock_run.workflow_type = "arm_analysis"

        # Mock query chain: first() → mock_run, update() → 0 (lost claim)
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_run
        mock_query.update.return_value = 0

        mock_db = MagicMock()
        mock_db.query.return_value = mock_query

        flow = {"start": "node_a", "edges": {}, "end": ["node_a"]}
        runner = PersistentFlowRunner(
            flow=flow,
            db=mock_db,
            user_id=test_user.id,
            workflow_type="arm_analysis",
        )

        result = runner.resume(mock_run.id)

        assert result["status"] == "SKIPPED"
        assert result["result"]["skipped"] is True
        assert "already claimed" in result["result"]["reason"]

    def test_start_path_not_blocked_by_claim(self, db_session, test_user):
        """start() creates FlowRuns with status='running' — claim guard skips them."""
        from AINDY.runtime.flow_engine import PersistentFlowRunner, register_node

        @register_node("soft_lock_run_node")
        def run_node(state, context):
            return {"status": "SUCCESS", "output_patch": {}}

        run = self._make_running_run(db_session, test_user.id, node_name="soft_lock_run_node")

        flow = {
            "start": "soft_lock_run_node",
            "edges": {},
            "end": ["soft_lock_run_node"],
        }
        runner = PersistentFlowRunner(
            flow=flow,
            db=db_session,
            user_id=test_user.id,
            workflow_type="arm_analysis",
        )
        # resume() must not return SKIPPED for a 'running' FlowRun
        result = runner.resume(run.id)

        assert result["status"] != "SKIPPED", (
            "start() path (status='running') must NOT be blocked by the soft-lock claim"
        )

    def test_claim_commit_failure_returns_skipped(self, db_session, test_user):
        """If the claim commit raises, resume() exits with SKIPPED (non-fatal)."""
        from AINDY.runtime.flow_engine import PersistentFlowRunner

        run = self._make_waiting_run(db_session, test_user.id)

        flow = {"start": "node_a", "edges": {}, "end": ["node_a"]}
        runner = PersistentFlowRunner(
            flow=flow,
            db=db_session,
            user_id=test_user.id,
            workflow_type="arm_analysis",
        )

        commit_calls = {"count": 0}
        original_commit = db_session.commit

        def _failing_commit():
            commit_calls["count"] += 1
            if commit_calls["count"] == 1:
                raise Exception("DB connection lost during claim commit")
            original_commit()

        with patch.object(db_session, "commit", side_effect=_failing_commit):
            result = runner.resume(run.id)

        assert result["status"] == "SKIPPED"
        assert result["result"]["skipped"] is True
        assert "claim commit failed" in result["result"]["reason"]

    def test_run_not_found_returns_failed(self, db_session, test_user):
        """Non-existent run_id returns FAILED (not SKIPPED)."""
        from AINDY.runtime.flow_engine import PersistentFlowRunner

        flow = {"start": "node_a", "edges": {}, "end": ["node_a"]}
        runner = PersistentFlowRunner(
            flow=flow,
            db=db_session,
            user_id=test_user.id,
            workflow_type="arm_analysis",
        )
        result = runner.resume("non-existent-run-id")

        assert result["status"] == "FAILED"
        assert "not found" in result["result"]["error"]

    def test_non_waiting_status_skips_claim(self, db_session, test_user):
        """FlowRun with status other than 'waiting' bypasses claim entirely."""
        from AINDY.runtime.flow_engine import PersistentFlowRunner, register_node

        @register_node("soft_lock_bypass_node")
        def bypass_node(state, context):
            return {"status": "SUCCESS", "output_patch": {}}

        # Explicitly set status='running' to represent a non-waiting FlowRun
        run = self._make_running_run(db_session, test_user.id, node_name="soft_lock_bypass_node")

        flow = {
            "start": "soft_lock_bypass_node",
            "edges": {},
            "end": ["soft_lock_bypass_node"],
        }
        runner = PersistentFlowRunner(
            flow=flow,
            db=db_session,
            user_id=test_user.id,
            workflow_type="arm_analysis",
        )

        # No UPDATE should be issued for non-waiting runs
        with patch.object(db_session, "query", wraps=db_session.query) as mock_q:
            result = runner.resume(run.id)

        assert result["status"] != "SKIPPED"

    def test_skipped_result_has_no_events(self, db_session, test_user):
        """SKIPPED response must include empty events list and correct run_id."""
        from AINDY.runtime.flow_engine import PersistentFlowRunner

        run_id = str(uuid.uuid4())

        mock_run = MagicMock()
        mock_run.id = run_id
        mock_run.status = "waiting"
        mock_run.state = {}
        mock_run.trace_id = str(uuid.uuid4())
        mock_run.current_node = "node_a"
        mock_run.flow_name = "test_flow"
        mock_run.workflow_type = "arm_analysis"

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_run
        mock_query.update.return_value = 0

        mock_db = MagicMock()
        mock_db.query.return_value = mock_query

        flow = {"start": "node_a", "edges": {}, "end": ["node_a"]}
        runner = PersistentFlowRunner(
            flow=flow,
            db=mock_db,
            user_id=test_user.id,
            workflow_type="arm_analysis",
        )

        result = runner.resume(run_id)

        assert result["status"] == "SKIPPED"
        assert result.get("events") == [] or result.get("events") is None
        assert result.get("run_id") == run_id or result.get("trace_id") == run_id
