"""
test_nodus_event_builtins.py
────────────────────────────
Unit tests for the event primitives in services/nodus_builtins.py and their
integration with NodusRuntimeAdapter and the nodus.execute flow node.

Coverage
--------
NodusWaitSignal             carries event_type, message contains it
NodusEventBuiltins.emit()   captures to _emitted, routes to event_sink,
                            falls back to queue_system_event, non-fatal on error
NodusEventBuiltins.wait()   wait path: sets state flags + raises NodusWaitSignal
                            wait path: emits nodus.event.wait_requested
                            resume path: returns payload from nodus_received_events
                            resume path: emits nodus.event.wait_resumed
                            wait_sink errors are swallowed
NodusRuntimeAdapter         event global injected, _emitted merged into result,
                            state-flag WAIT path returns status="waiting",
                            NodusWaitSignal re-raise path returns status="waiting"
nodus.execute node          WAIT path returned when adapter status=="waiting",
                            resume bridge moves state["event"] → nodus_received_events,
                            WAIT without wait_for → FAILURE
"""
from __future__ import annotations

import json
import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, call


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_event_builtins(
    *,
    event_sink=None,
    context_state=None,
    raise_on_queue=False,
):
    from AINDY.runtime.nodus_builtins import NodusEventBuiltins

    ctx_state = context_state if context_state is not None else {}
    db = MagicMock()

    builtins = NodusEventBuiltins(
        db=db,
        user_id="user-1",
        execution_unit_id="eu-1",
        trace_id="trace-1",
        event_sink=event_sink,
        context_state=ctx_state,
    )

    if raise_on_queue:
        def _failing_queue(*a, **kw):
            raise RuntimeError("queue down")
        builtins._queue = _failing_queue  # type: ignore[method-assign]

    return builtins, ctx_state


# ── NodusWaitSignal ────────────────────────────────────────────────────────────

class TestNodusWaitSignal:
    def test_carries_event_type(self):
        from AINDY.runtime.nodus_builtins import NodusWaitSignal
        sig = NodusWaitSignal("approval.received")
        assert sig.event_type == "approval.received"

    def test_message_contains_event_type(self):
        from AINDY.runtime.nodus_builtins import NodusWaitSignal
        sig = NodusWaitSignal("my.event")
        assert "my.event" in str(sig)

    def test_is_exception(self):
        from AINDY.runtime.nodus_builtins import NodusWaitSignal
        assert issubclass(NodusWaitSignal, Exception)

    def test_can_be_caught_as_exception(self):
        from AINDY.runtime.nodus_builtins import NodusWaitSignal
        caught = None
        try:
            raise NodusWaitSignal("x")
        except Exception as e:
            caught = e
        assert caught is not None
        assert isinstance(caught, NodusWaitSignal)


# ── NodusEventBuiltins.emit() ──────────────────────────────────────────────────

class TestEventEmit:
    def test_captured_in_emitted(self):
        b, _ = _make_event_builtins()
        b.emit("step.done", {"x": 1})
        assert len(b._emitted) == 1
        assert b._emitted[0]["event_type"] == "step.done"
        assert b._emitted[0]["payload"] == {"x": 1}

    def test_emitted_list_starts_empty(self):
        b, _ = _make_event_builtins()
        assert b._emitted == []

    def test_user_id_in_captured_record(self):
        b, _ = _make_event_builtins()
        b.emit("e")
        assert b._emitted[0]["user_id"] == "user-1"

    def test_execution_unit_id_in_captured_record(self):
        b, _ = _make_event_builtins()
        b.emit("e")
        assert b._emitted[0]["execution_unit_id"] == "eu-1"

    def test_routes_to_event_sink_when_provided(self):
        sink = MagicMock()
        b, _ = _make_event_builtins(event_sink=sink)
        b.emit("my.event", {"key": "val"})
        sink.assert_called_once_with("my.event", {"key": "val"})

    def test_does_not_call_queue_when_sink_provided(self):
        sink = MagicMock()
        b, _ = _make_event_builtins(event_sink=sink)
        with patch("AINDY.core.execution_signal_helper.queue_system_event") as mock_q:
            b.emit("e")
        mock_q.assert_not_called()

    def test_calls_queue_system_event_when_no_sink(self):
        b, _ = _make_event_builtins()
        with patch("AINDY.runtime.nodus_builtins.NodusEventBuiltins._queue") as mock_q:
            b.emit("event.a", {"data": 1})
        mock_q.assert_called_once()
        args = mock_q.call_args
        assert args[0][0] == "event.a"

    def test_none_payload_becomes_empty_dict(self):
        b, _ = _make_event_builtins()
        b.emit("e", None)
        assert b._emitted[0]["payload"] == {}

    def test_event_sink_failure_swallowed(self):
        sink = MagicMock(side_effect=RuntimeError("sink down"))
        b, _ = _make_event_builtins(event_sink=sink)
        b.emit("e")  # must not raise
        assert len(b._emitted) == 1

    def test_multiple_emits_all_captured(self):
        b, _ = _make_event_builtins()
        b.emit("a")
        b.emit("b")
        b.emit("c")
        types = [r["event_type"] for r in b._emitted]
        assert types == ["a", "b", "c"]


# ── NodusEventBuiltins.wait() — wait path ─────────────────────────────────────

class TestEventWaitWaitPath:
    def test_raises_nodus_wait_signal(self):
        from AINDY.runtime.nodus_builtins import NodusWaitSignal
        b, _ = _make_event_builtins()
        with pytest.raises(NodusWaitSignal) as exc_info:
            b.wait("approval.received")
        assert exc_info.value.event_type == "approval.received"

    def test_sets_wait_requested_flag(self):
        from AINDY.runtime.nodus_builtins import NodusWaitSignal
        b, ctx_state = _make_event_builtins()
        with pytest.raises(NodusWaitSignal):
            b.wait("foo.event")
        assert ctx_state.get("nodus_wait_requested") is True

    def test_sets_wait_event_type_flag(self):
        from AINDY.runtime.nodus_builtins import NodusWaitSignal
        b, ctx_state = _make_event_builtins()
        with pytest.raises(NodusWaitSignal):
            b.wait("bar.event")
        assert ctx_state.get("nodus_wait_event_type") == "bar.event"

    def test_emits_wait_requested_system_event(self):
        from AINDY.runtime.nodus_builtins import NodusWaitSignal
        emitted_types = []

        def spy_sink(event_type, payload):
            emitted_types.append(event_type)

        b, _ = _make_event_builtins(event_sink=spy_sink)
        with pytest.raises(NodusWaitSignal):
            b.wait("my.event")

        assert "nodus.event.wait_requested" in emitted_types

    def test_queue_error_during_wait_does_not_prevent_signal(self):
        from AINDY.runtime.nodus_builtins import NodusWaitSignal
        b, _ = _make_event_builtins(raise_on_queue=True)
        with pytest.raises(NodusWaitSignal):
            b.wait("x")  # _queue raises, but NodusWaitSignal still propagates


# ── NodusEventBuiltins.wait() — resume path ───────────────────────────────────

class TestEventWaitResumePath:
    def test_returns_payload_when_event_received(self):
        ctx_state = {
            "nodus_received_events": {"approval.received": {"user": "alice", "ok": True}}
        }
        b, _ = _make_event_builtins(context_state=ctx_state)
        result = b.wait("approval.received")
        assert result == {"user": "alice", "ok": True}

    def test_does_not_raise_on_resume(self):
        ctx_state = {"nodus_received_events": {"x": {}}}
        b, _ = _make_event_builtins(context_state=ctx_state)
        b.wait("x")  # must not raise

    def test_emits_wait_resumed_event(self):
        emitted_types = []

        def spy_sink(event_type, payload):
            emitted_types.append(event_type)

        ctx_state = {"nodus_received_events": {"step.done": {"data": 1}}}
        b, _ = _make_event_builtins(event_sink=spy_sink, context_state=ctx_state)
        b.wait("step.done")
        assert "nodus.event.wait_resumed" in emitted_types

    def test_different_event_still_waits(self):
        from AINDY.runtime.nodus_builtins import NodusWaitSignal
        ctx_state = {"nodus_received_events": {"other.event": {}}}
        b, _ = _make_event_builtins(context_state=ctx_state)
        with pytest.raises(NodusWaitSignal) as exc_info:
            b.wait("approval.received")
        assert exc_info.value.event_type == "approval.received"

    def test_non_dict_payload_returns_empty_dict(self):
        ctx_state = {"nodus_received_events": {"e": "not-a-dict"}}
        b, _ = _make_event_builtins(context_state=ctx_state)
        result = b.wait("e")
        assert result == {}


# ── NodusRuntimeAdapter integration ───────────────────────────────────────────

class TestAdapterEventIntegration:
    """Verify adapter subprocess payload and WAIT result handling."""

    def _run_with_flags(self, *, set_wait_flag=False, raise_wait_signal=False, event_type="foo.event"):
        """Run adapter._execute() with a mocked worker response."""
        from AINDY.runtime.nodus_runtime_adapter import NodusRuntimeAdapter, NodusExecutionContext

        captured_payload: dict = {}

        db = MagicMock()
        ctx = NodusExecutionContext(user_id="u1", execution_unit_id="eu-1")

        if set_wait_flag or raise_wait_signal:
            worker_payload = {
                "status": "waiting",
                "output_state": {"nodus_wait_event_type": event_type},
                "emitted_events": [],
                "memory_writes": [],
                "error": None,
                "stdout_log": "",
                "wait_for": event_type,
            }
        else:
            worker_payload = {
                "status": "success",
                "output_state": {},
                "emitted_events": [
                    {
                        "event_type": "injected.event",
                        "type": "injected.event",
                        "payload": {},
                        "execution_unit_id": "eu-1",
                        "user_id": "u1",
                    }
                ],
                "memory_writes": [],
                "error": None,
                "stdout_log": "",
            }

        def fake_run(*_args, **kwargs):
            captured_payload.update(json.loads(kwargs["input"]))
            return SimpleNamespace(returncode=0, stdout=json.dumps(worker_payload), stderr="")

        with patch("AINDY.runtime.nodus_runtime_adapter.subprocess.run", side_effect=fake_run):
            adapter = NodusRuntimeAdapter(db=db)
            result = adapter._execute("let x = 1", "<t>", ctx)

        return result, captured_payload

    def test_event_global_injected(self):
        _, captured = self._run_with_flags()
        assert captured["context"]["execution_unit_id"] == "eu-1"

    def test_state_flag_wait_returns_waiting_status(self):
        result, _ = self._run_with_flags(set_wait_flag=True)
        assert result.status == "waiting"

    def test_state_flag_wait_result_has_wait_for(self):
        result, _ = self._run_with_flags(set_wait_flag=True, event_type="my.event")
        assert result.raw_result["wait_for"] == "my.event"

    def test_state_flag_cleared_after_wait(self):
        from AINDY.runtime.nodus_runtime_adapter import NodusRuntimeAdapter, NodusExecutionContext
        ctx = NodusExecutionContext(user_id="u1", execution_unit_id="eu-1")
        ctx.state["nodus_wait_requested"] = True
        ctx.state["nodus_wait_event_type"] = "x"

        with patch(
            "AINDY.runtime.nodus_runtime_adapter.subprocess.run",
            return_value=SimpleNamespace(
                returncode=0,
                stdout=json.dumps(
                    {
                        "status": "waiting",
                        "output_state": {"nodus_wait_event_type": "x"},
                        "emitted_events": [],
                        "memory_writes": [],
                        "error": None,
                        "stdout_log": "",
                        "wait_for": "x",
                    }
                ),
                stderr="",
            ),
        ):
            adapter = NodusRuntimeAdapter(db=MagicMock())
            adapter._execute("x", "<t>", ctx)

        assert "nodus_wait_requested" not in ctx.state
        assert ctx.state["nodus_wait_event_type"] == "x"

    def test_emitted_merged_into_result(self):
        result, _ = self._run_with_flags()

        assert any(e["event_type"] == "injected.event" for e in result.emitted_events)

    def test_nodus_wait_signal_reraise_returns_waiting(self):
        result, _ = self._run_with_flags(raise_wait_signal=True, event_type="raised.event")
        assert result.status == "waiting"
        assert result.raw_result["wait_for"] == "raised.event"


# ── nodus.execute flow node — WAIT path ───────────────────────────────────────

class TestNodusExecuteNodeWait:
    """Test the WAIT-path additions to the nodus.execute registered flow node."""

    def _make_waiting_result(self, wait_for="approval.received"):
        """Create a NodusExecutionResult with status='waiting'."""
        from AINDY.runtime.nodus_runtime_adapter import NodusExecutionResult
        return NodusExecutionResult(
            output_state={},
            emitted_events=[],
            memory_writes=[],
            status="waiting",
            raw_result={"ok": True, "wait_for": wait_for},
        )

    def _run_node(self, state: dict, wait_for="approval.received"):
        """Call nodus_execute_node with adapter returning waiting status."""
        from AINDY.runtime.nodus_adapter import nodus_execute_node

        context = {
            "db": MagicMock(),
            "user_id": "u1",
            "run_id": "run-1",
            "trace_id": "trace-1",
            "flow_name": "test_flow",
            "memory_context": {},
            "attempts": {},
        }

        waiting_result = self._make_waiting_result(wait_for=wait_for)

        with patch("AINDY.runtime.nodus_runtime_adapter.NodusRuntimeAdapter") as MockAdapter, \
             patch("AINDY.runtime.nodus_adapter.queue_system_event"):
            mock_adapter = MagicMock()
            mock_adapter.run_script.return_value = waiting_result
            mock_adapter.run_file.return_value = waiting_result
            MockAdapter.return_value = mock_adapter

            return nodus_execute_node(state=state, context=context)

    def test_wait_status_returns_wait_node_status(self):
        result = self._run_node({"nodus_script": "event.wait('approval.received')"})
        assert result["status"] == "WAIT"

    def test_wait_for_propagated_in_result(self):
        result = self._run_node(
            {"nodus_script": "event.wait('approval.received')"},
            wait_for="approval.received",
        )
        assert result["wait_for"] == "approval.received"

    def test_wait_nodus_status_in_output_patch(self):
        result = self._run_node({"nodus_script": "event.wait('x')", "nodus_wait_event_type": None})
        assert result["output_patch"]["nodus_status"] == "waiting"

    def test_wait_type_in_output_patch(self):
        result = self._run_node({"nodus_script": "x"}, wait_for="my.event")
        assert result["output_patch"]["nodus_wait_event_type"] == "my.event"

    def test_wait_without_wait_for_returns_failure(self):
        from AINDY.runtime.nodus_runtime_adapter import NodusExecutionResult
        from AINDY.runtime.nodus_adapter import nodus_execute_node

        bad_result = NodusExecutionResult(
            output_state={},
            emitted_events=[],
            memory_writes=[],
            status="waiting",
            raw_result={"ok": True},  # no wait_for key
        )
        context = {
            "db": MagicMock(), "user_id": "u1", "run_id": "r1",
            "trace_id": "t1", "flow_name": "f", "memory_context": {}, "attempts": {},
        }
        with patch("AINDY.runtime.nodus_runtime_adapter.NodusRuntimeAdapter") as MockA, \
             patch("AINDY.runtime.nodus_adapter.queue_system_event"):
            MockA.return_value.run_script.return_value = bad_result
            result = nodus_execute_node(
                state={"nodus_script": "x"},
                context=context,
            )
        assert result["status"] == "FAILURE"


# ── Resume bridge in nodus.execute ────────────────────────────────────────────

class TestNodusExecuteResumeBridge:
    """Verify route_event() payload is bridged into nodus_received_events."""

    def _run_node_with_resume_state(self, extra_state: dict | None = None):
        """Run the node with a state that simulates route_event() injection."""
        from AINDY.runtime.nodus_adapter import nodus_execute_node
        from AINDY.runtime.nodus_runtime_adapter import NodusExecutionResult

        # Simulate the state after route_event() injects the received event
        state = {
            "nodus_script": "event.wait('approval.received')",
            "nodus_wait_event_type": "approval.received",
            "event": {"user": "alice", "approved": True},  # injected by route_event()
            **(extra_state or {}),
        }

        success_result = NodusExecutionResult(
            output_state={"nodus_received_events": {"approval.received": {"user": "alice"}}},
            emitted_events=[],
            memory_writes=[],
            status="success",
        )

        context = {
            "db": MagicMock(), "user_id": "u1", "run_id": "r1",
            "trace_id": "t1", "flow_name": "f", "memory_context": {}, "attempts": {},
        }

        captured_ctx: list = []

        with patch("AINDY.runtime.nodus_runtime_adapter.NodusRuntimeAdapter") as MockAdapter, \
             patch("AINDY.runtime.nodus_adapter.queue_system_event"):
            mock_adapter = MagicMock()
            mock_adapter.run_script.return_value = success_result

            def capture_ctx(script, nodus_ctx):
                captured_ctx.append(nodus_ctx)
                return success_result

            mock_adapter.run_script.side_effect = capture_ctx
            MockAdapter.return_value = mock_adapter

            result = nodus_execute_node(state=state, context=context)

        return result, state, captured_ctx

    def test_event_key_consumed_from_state(self):
        _, state, _ = self._run_node_with_resume_state()
        assert "event" not in state

    def test_wait_type_cleared_from_state(self):
        _, state, _ = self._run_node_with_resume_state()
        assert "nodus_wait_event_type" not in state

    def test_received_event_bridged_into_nodus_state(self):
        _, _, captured_ctx = self._run_node_with_resume_state()
        assert len(captured_ctx) == 1
        ctx = captured_ctx[0]
        received = ctx.state.get("nodus_received_events", {})
        assert "approval.received" in received
        assert received["approval.received"]["user"] == "alice"

    def test_no_bridge_when_no_pending_wait(self):
        from AINDY.runtime.nodus_adapter import nodus_execute_node
        from AINDY.runtime.nodus_runtime_adapter import NodusExecutionResult

        # State has event but no nodus_wait_event_type — should NOT bridge
        state = {
            "nodus_script": "let x = 1",
            "event": {"some": "data"},
            # no nodus_wait_event_type
        }
        success = NodusExecutionResult(
            output_state={}, emitted_events=[], memory_writes=[], status="success"
        )
        context = {
            "db": MagicMock(), "user_id": "u1", "run_id": "r1",
            "trace_id": "t1", "flow_name": "f", "memory_context": {}, "attempts": {},
        }
        captured_ctx: list = []

        with patch("AINDY.runtime.nodus_runtime_adapter.NodusRuntimeAdapter") as MockA, \
             patch("AINDY.runtime.nodus_adapter.queue_system_event"):
            def cap(script, ctx):
                captured_ctx.append(ctx)
                return success
            MockA.return_value.run_script.side_effect = cap

            nodus_execute_node(state=state, context=context)

        ctx = captured_ctx[0]
        assert ctx.state.get("nodus_received_events", {}) == {}

