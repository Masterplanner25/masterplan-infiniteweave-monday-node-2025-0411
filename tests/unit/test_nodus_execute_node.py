"""
test_nodus_execute_node.py
──────────────────────────
Unit tests for the "nodus.execute" flow node and its companion nodes
(nodus_record_outcome, nodus_handle_error) registered in nodus_adapter.py.

Coverage
--------
nodus.execute           missing source → FAILURE
                        script success → SUCCESS + full output_patch
                        script failure + "fail" policy → FAILURE
                        script failure + "retry" policy → RETRY
                        file_path used when no script provided
                        execution_unit_id from state override
                        execution_unit_id defaults to run_id
                        memory_context passed from flow context
                        event emits: started + completed/failed
                        memory writes flushed after execution
nodus_record_outcome    patches nodus_execute_result into state
nodus_handle_error      patches nodus_handled_error + result into state
NODUS_SCRIPT_FLOW       flow definition structure sanity check
"""
from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# Importing nodus_adapter triggers node registration in NODE_REGISTRY
import AINDY.runtime.nodus_adapter  # noqa: F401  — side-effect: registers nodes
from AINDY.runtime.flow_engine import NODE_REGISTRY
from AINDY.runtime.nodus_runtime_adapter import (
    NODUS_SCRIPT_FLOW,
    NodusExecutionResult,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_context(**overrides: Any) -> dict:
    defaults = dict(
        db=MagicMock(),
        user_id=str(uuid.uuid4()),
        run_id=str(uuid.uuid4()),
        trace_id="trace-abc",
        flow_name="test_flow",
        workflow_type="nodus_execute",
        attempts={"nodus.execute": 0},
        memory_context={"m1": {"content": "prior run"}},
    )
    defaults.update(overrides)
    return defaults


def _make_nodus_result(
    status: str = "success",
    output_state: dict | None = None,
    emitted_events: list | None = None,
    memory_writes: list | None = None,
    error: str | None = None,
) -> NodusExecutionResult:
    return NodusExecutionResult(
        output_state=output_state or {},
        emitted_events=emitted_events or [],
        memory_writes=memory_writes or [],
        status=status,
        error=error,
        raw_result={"ok": status == "success"},
    )


# ── Node registration ─────────────────────────────────────────────────────────

class TestNodeRegistration:
    def test_nodus_execute_registered(self):
        assert "nodus.execute" in NODE_REGISTRY

    def test_nodus_record_outcome_registered(self):
        assert "nodus_record_outcome" in NODE_REGISTRY

    def test_nodus_handle_error_registered(self):
        assert "nodus_handle_error" in NODE_REGISTRY

    def test_all_nodes_callable(self):
        for name in ("nodus.execute", "nodus_record_outcome", "nodus_handle_error"):
            assert callable(NODE_REGISTRY[name])


# ── nodus.execute — source validation ─────────────────────────────────────────

# The node uses lazy imports so patches must target the source modules, not nodus_adapter.
_ADAPTER_PATH = "AINDY.runtime.nodus_runtime_adapter.NodusRuntimeAdapter"
_SINK_PATH = "AINDY.runtime.nodus_runtime_adapter._build_event_sink"
_FLUSH_PATH = "AINDY.runtime.nodus_runtime_adapter._flush_memory_writes"
_EVENT_PATH = "AINDY.core.execution_signal_helper.queue_system_event"


class TestNodusExecuteSourceValidation:
    def _run(self, state: dict, context: dict | None = None) -> dict:
        return NODE_REGISTRY["nodus.execute"](state, context or _make_context())

    def test_missing_source_returns_failure(self):
        result = self._run({})
        assert result["status"] == "FAILURE"
        assert "nodus_script" in result["error"]
        assert "nodus_file_path" in result["error"]

    def test_empty_script_string_treated_as_missing(self):
        result = self._run({"nodus_script": ""})
        assert result["status"] == "FAILURE"

    def test_none_both_treated_as_missing(self):
        result = self._run({"nodus_script": None, "nodus_file_path": None})
        assert result["status"] == "FAILURE"


# ── nodus.execute — success path ──────────────────────────────────────────────

class TestNodusExecuteSuccess:
    def _patched_run(self, state: dict, context: dict, nodus_result: NodusExecutionResult) -> dict:
        with patch(_ADAPTER_PATH) as MockAdapter, \
             patch(_EVENT_PATH), \
             patch(_FLUSH_PATH):
            instance = MockAdapter.return_value
            instance.run_script.return_value = nodus_result
            instance.run_file.return_value = nodus_result
            return NODE_REGISTRY["nodus.execute"](state, context)

    def test_script_success_returns_success_status(self):
        result = self._patched_run(
            {"nodus_script": "let x = 1"},
            _make_context(),
            _make_nodus_result(status="success", output_state={"x": 1}),
        )
        assert result["status"] == "SUCCESS"

    def test_output_patch_contains_required_keys(self):
        nodus_result = _make_nodus_result(
            status="success",
            output_state={"key": "value"},
            emitted_events=[{"event_type": "done"}],
            memory_writes=[{"args": ["note"]}],
        )
        result = self._patched_run(
            {"nodus_script": "let x = 1"},
            _make_context(),
            nodus_result,
        )
        patch_keys = result["output_patch"].keys()
        assert "nodus_status" in patch_keys
        assert "nodus_output_state" in patch_keys
        assert "nodus_events" in patch_keys
        assert "nodus_memory_writes" in patch_keys
        assert "nodus_execute_result" in patch_keys

    def test_output_patch_values_match_nodus_result(self):
        nodus_result = _make_nodus_result(
            status="success",
            output_state={"processed": True},
            emitted_events=[{"event_type": "task.done"}],
            memory_writes=[{"args": ["content"]}],
        )
        result = self._patched_run(
            {"nodus_script": "..."},
            _make_context(),
            nodus_result,
        )
        patch = result["output_patch"]
        assert patch["nodus_status"] == "success"
        assert patch["nodus_output_state"] == {"processed": True}
        assert len(patch["nodus_events"]) == 1
        assert len(patch["nodus_memory_writes"]) == 1

    def test_nodus_execute_result_summary_has_counts(self):
        nodus_result = _make_nodus_result(
            status="success",
            emitted_events=[{"event_type": "a"}, {"event_type": "b"}],
            memory_writes=[{"args": ["x"]}],
        )
        result = self._patched_run(
            {"nodus_script": "..."},
            _make_context(),
            nodus_result,
        )
        summary = result["output_patch"]["nodus_execute_result"]
        assert summary["events_emitted"] == 2
        assert summary["memory_writes"] == 1
        assert summary["status"] == "success"
        assert summary["error"] is None

    def test_file_path_used_when_no_script(self):
        nodus_result = _make_nodus_result(status="success")
        with patch(_ADAPTER_PATH) as MockAdapter, \
             patch(_EVENT_PATH), \
             patch(_FLUSH_PATH):
            instance = MockAdapter.return_value
            instance.run_file.return_value = nodus_result
            state = {"nodus_file_path": "/scripts/goal.nodus"}
            NODE_REGISTRY["nodus.execute"](state, _make_context())
            instance.run_file.assert_called_once_with("/scripts/goal.nodus", instance.run_file.call_args[0][1])
            instance.run_script.assert_not_called()


# ── nodus.execute — failure path ──────────────────────────────────────────────

class TestNodusExecuteFailure:
    def _patched_run(self, state: dict, nodus_result: NodusExecutionResult) -> dict:
        with patch(_ADAPTER_PATH) as MockAdapter, \
             patch(_EVENT_PATH), \
             patch(_FLUSH_PATH):
            instance = MockAdapter.return_value
            instance.run_script.return_value = nodus_result
            return NODE_REGISTRY["nodus.execute"](state, _make_context())

    def test_failure_default_policy_returns_failure(self):
        nodus_result = _make_nodus_result(status="failure", error="type error")
        result = self._patched_run({"nodus_script": "bad"}, nodus_result)
        assert result["status"] == "FAILURE"
        assert result["error"] == "type error"

    def test_failure_explicit_fail_policy_returns_failure(self):
        nodus_result = _make_nodus_result(status="failure", error="err")
        result = self._patched_run(
            {"nodus_script": "bad", "nodus_error_policy": "fail"},
            nodus_result,
        )
        assert result["status"] == "FAILURE"

    def test_failure_retry_policy_returns_retry(self):
        nodus_result = _make_nodus_result(status="failure", error="transient")
        result = self._patched_run(
            {"nodus_script": "bad", "nodus_error_policy": "retry"},
            nodus_result,
        )
        assert result["status"] == "RETRY"
        assert result["error"] == "transient"

    def test_failure_output_patch_contains_nodus_error(self):
        nodus_result = _make_nodus_result(status="failure", error="script crashed")
        result = self._patched_run({"nodus_script": "bad"}, nodus_result)
        assert result["output_patch"]["nodus_error"] == "script crashed"


# ── nodus.execute — context injection ─────────────────────────────────────────

_CTX_PATH = "AINDY.runtime.nodus_runtime_adapter.NodusExecutionContext"
_CANONICAL_EXEC_PATH = "AINDY.runtime.nodus_adapter.execute_nodus_runtime"


class TestNodusExecuteContextInjection:
    def test_delegates_to_canonical_runtime_helper(self):
        nodus_result = _make_nodus_result(status="success")

        with patch(_CANONICAL_EXEC_PATH, return_value=nodus_result) as mock_execute, \
             patch(_EVENT_PATH), \
             patch(_FLUSH_PATH):
            NODE_REGISTRY["nodus.execute"]({"nodus_script": "let x = 1"}, _make_context())

        mock_execute.assert_called_once()

    def test_execution_unit_id_from_state_override(self):
        custom_eu = "custom-eu-id"
        captured_ctx: list = []

        with patch(_ADAPTER_PATH) as MockAdapter, \
             patch(_CTX_PATH, side_effect=lambda **kw: (captured_ctx.append(kw), MagicMock())[1]), \
             patch(_EVENT_PATH), \
             patch(_FLUSH_PATH), \
             patch(_SINK_PATH, return_value=MagicMock()):
            instance = MockAdapter.return_value
            instance.run_script.return_value = _make_nodus_result(status="success")
            state = {"nodus_script": "x", "execution_unit_id": custom_eu}
            NODE_REGISTRY["nodus.execute"](state, _make_context())

        assert any(kw.get("execution_unit_id") == custom_eu for kw in captured_ctx)

    def test_execution_unit_id_defaults_to_run_id(self):
        run_id = "flow-run-xyz"
        captured_ctx: list = []

        with patch(_ADAPTER_PATH) as MockAdapter, \
             patch(_CTX_PATH, side_effect=lambda **kw: (captured_ctx.append(kw), MagicMock())[1]), \
             patch(_EVENT_PATH), \
             patch(_FLUSH_PATH), \
             patch(_SINK_PATH, return_value=MagicMock()):
            instance = MockAdapter.return_value
            instance.run_script.return_value = _make_nodus_result(status="success")
            state = {"nodus_script": "x"}
            NODE_REGISTRY["nodus.execute"](state, _make_context(run_id=run_id))

        assert any(kw.get("execution_unit_id") == run_id for kw in captured_ctx)

    def test_memory_context_passed_from_flow_context(self):
        memory = {"m1": {"content": "recall data"}}
        captured_ctx: list = []

        with patch(_ADAPTER_PATH) as MockAdapter, \
             patch(_CTX_PATH, side_effect=lambda **kw: (captured_ctx.append(kw), MagicMock())[1]), \
             patch(_EVENT_PATH), \
             patch(_FLUSH_PATH), \
             patch(_SINK_PATH, return_value=MagicMock()):
            instance = MockAdapter.return_value
            instance.run_script.return_value = _make_nodus_result(status="success")
            state = {"nodus_script": "x"}
            ctx = _make_context(memory_context=memory)
            NODE_REGISTRY["nodus.execute"](state, ctx)

        assert any(kw.get("memory_context") == memory for kw in captured_ctx)


# ── nodus.execute — event emission ────────────────────────────────────────────

class TestNodusExecuteEvents:
    def test_started_and_completed_events_queued_on_success(self):
        queued: list[str] = []

        def fake_queue(*, db, event_type, **_kw):
            queued.append(event_type)

        with patch(_ADAPTER_PATH) as MockAdapter, \
             patch(_EVENT_PATH, side_effect=fake_queue), \
             patch(_FLUSH_PATH):
            instance = MockAdapter.return_value
            instance.run_script.return_value = _make_nodus_result(status="success")
            NODE_REGISTRY["nodus.execute"]({"nodus_script": "x"}, _make_context())

        assert "nodus.execute.started" in queued
        assert "nodus.execute.completed" in queued
        assert "nodus.execute.failed" not in queued

    def test_started_and_failed_events_queued_on_failure(self):
        queued: list[str] = []

        def fake_queue(*, db, event_type, **_kw):
            queued.append(event_type)

        with patch(_ADAPTER_PATH) as MockAdapter, \
             patch(_EVENT_PATH, side_effect=fake_queue), \
             patch(_FLUSH_PATH):
            instance = MockAdapter.return_value
            instance.run_script.return_value = _make_nodus_result(status="failure", error="err")
            NODE_REGISTRY["nodus.execute"]({"nodus_script": "x"}, _make_context())

        assert "nodus.execute.started" in queued
        assert "nodus.execute.failed" in queued
        assert "nodus.execute.completed" not in queued


# ── nodus.execute — memory flush ──────────────────────────────────────────────

class TestNodusExecuteMemoryFlush:
    def test_memory_writes_flushed_on_success(self):
        flush_calls: list[dict] = []

        def fake_flush(*, db, user_id, run_id, memory_writes, flow_name):
            flush_calls.append({"memory_writes": memory_writes})

        with patch(_ADAPTER_PATH) as MockAdapter, \
             patch(_EVENT_PATH), \
             patch(_FLUSH_PATH, side_effect=fake_flush):
            instance = MockAdapter.return_value
            instance.run_script.return_value = _make_nodus_result(
                status="success",
                memory_writes=[{"args": ["a note"]}],
            )
            NODE_REGISTRY["nodus.execute"]({"nodus_script": "x"}, _make_context())

        assert len(flush_calls) == 1
        assert flush_calls[0]["memory_writes"] == [{"args": ["a note"]}]

    def test_no_flush_when_no_memory_writes(self):
        flush_calls: list = []

        def noop_flush(**_kw):
            flush_calls.append(True)

        with patch(_ADAPTER_PATH) as MockAdapter, \
             patch(_EVENT_PATH), \
             patch(_FLUSH_PATH, side_effect=noop_flush):
            instance = MockAdapter.return_value
            instance.run_script.return_value = _make_nodus_result(status="success", memory_writes=[])
            NODE_REGISTRY["nodus.execute"]({"nodus_script": "x"}, _make_context())

        assert flush_calls == []


# ── nodus_record_outcome ──────────────────────────────────────────────────────

class TestNodusRecordOutcome:
    def _run(self, state: dict) -> dict:
        return NODE_REGISTRY["nodus_record_outcome"](state, _make_context())

    def test_returns_success(self):
        result = self._run({"nodus_execute_result": {"status": "success"}})
        assert result["status"] == "SUCCESS"

    def test_patches_nodus_execute_result(self):
        summary = {"status": "success", "events_emitted": 2}
        result = self._run({"nodus_execute_result": summary})
        assert result["output_patch"]["nodus_execute_result"] == summary

    def test_missing_result_defaults_to_empty(self):
        result = self._run({})
        assert result["output_patch"]["nodus_execute_result"] == {}


# ── nodus_handle_error ────────────────────────────────────────────────────────

class TestNodusHandleError:
    def _run(self, state: dict) -> dict:
        return NODE_REGISTRY["nodus_handle_error"](state, _make_context())

    def test_returns_success(self):
        result = self._run({"nodus_error": "script crashed"})
        assert result["status"] == "SUCCESS"

    def test_patches_nodus_handled_error(self):
        result = self._run({"nodus_error": "oops"})
        assert result["output_patch"]["nodus_handled_error"] == "oops"

    def test_default_error_when_none(self):
        result = self._run({})
        assert result["output_patch"]["nodus_handled_error"] == "Nodus script failed"

    def test_patches_nodus_execute_result(self):
        summary = {"status": "failure", "error": "oops"}
        result = self._run({"nodus_error": "oops", "nodus_execute_result": summary})
        assert result["output_patch"]["nodus_execute_result"] == summary


# ── NODUS_SCRIPT_FLOW structure ───────────────────────────────────────────────

class TestNodusScriptFlow:
    def test_flow_has_required_keys(self):
        assert "start" in NODUS_SCRIPT_FLOW
        assert "edges" in NODUS_SCRIPT_FLOW
        assert "end" in NODUS_SCRIPT_FLOW

    def test_start_node_is_nodus_execute(self):
        assert NODUS_SCRIPT_FLOW["start"] == "nodus.execute"

    def test_end_nodes_include_both_branches(self):
        assert "nodus_record_outcome" in NODUS_SCRIPT_FLOW["end"]
        assert "nodus_handle_error" in NODUS_SCRIPT_FLOW["end"]

    def test_success_condition_routes_to_record_outcome(self):
        success_state = {"nodus_status": "success"}
        edges = NODUS_SCRIPT_FLOW["edges"]["nodus.execute"]
        matched = next(
            e["target"] for e in edges if e["condition"](success_state)
        )
        assert matched == "nodus_record_outcome"

    def test_failure_condition_routes_to_handle_error(self):
        failure_state = {"nodus_status": "failure"}
        edges = NODUS_SCRIPT_FLOW["edges"]["nodus.execute"]
        targets = [e["target"] for e in edges if e["condition"](failure_state)]
        assert "nodus_handle_error" in targets

    def test_all_flow_nodes_are_registered(self):
        all_nodes = set()
        all_nodes.add(NODUS_SCRIPT_FLOW["start"])
        all_nodes.update(NODUS_SCRIPT_FLOW["end"])
        for edges in NODUS_SCRIPT_FLOW["edges"].values():
            for edge in edges:
                if isinstance(edge, dict):
                    all_nodes.add(edge["target"])
        for name in all_nodes:
            assert name in NODE_REGISTRY, f"Node '{name}' not in NODE_REGISTRY"

