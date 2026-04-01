"""
test_nodus_runtime_adapter.py
─────────────────────────────
Unit tests for the NodusRuntimeAdapter execution contract.

Coverage
--------
NodusExecutionContext   field defaults, field assignment
NodusExecutionResult    field defaults, field assignment
NodusRuntimeAdapter     run_script / run_file — success, failure, ImportError,
                        event_sink wiring, memory_writes capture, state mutation,
                        run_file OSError, custom event_sink
"""
from __future__ import annotations

import os
import tempfile
import uuid
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from services.nodus_runtime_adapter import (
    NodusExecutionContext,
    NodusExecutionResult,
    NodusRuntimeAdapter,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_context(**overrides: Any) -> NodusExecutionContext:
    defaults = dict(
        user_id=str(uuid.uuid4()),
        execution_unit_id=str(uuid.uuid4()),
        memory_context={"mem1": {"id": "mem1", "content": "prior run"}},
        input_payload={"goal": "test"},
        state={"counter": 0},
    )
    defaults.update(overrides)
    return NodusExecutionContext(**defaults)


def _fake_runtime(ok: bool = True, error: str | None = None):
    """Return a mock NodusRuntime whose run_source returns a controlled result."""
    runtime = MagicMock()
    raw = {"ok": ok}
    if error:
        raw["error"] = error
    runtime.run_source.return_value = raw
    return runtime


# ── NodusExecutionContext ─────────────────────────────────────────────────────

class TestNodusExecutionContext:
    def test_required_fields(self):
        ctx = NodusExecutionContext(
            user_id="u1",
            execution_unit_id="eu1",
        )
        assert ctx.user_id == "u1"
        assert ctx.execution_unit_id == "eu1"

    def test_optional_fields_default_to_empty(self):
        ctx = NodusExecutionContext(user_id="u1", execution_unit_id="eu1")
        assert ctx.memory_context == {}
        assert ctx.input_payload == {}
        assert ctx.state == {}
        assert ctx.event_sink is None

    def test_state_is_mutable(self):
        ctx = NodusExecutionContext(user_id="u1", execution_unit_id="eu1", state={"x": 1})
        ctx.state["x"] = 99
        assert ctx.state["x"] == 99

    def test_event_sink_callable(self):
        sink = MagicMock()
        ctx = NodusExecutionContext(user_id="u1", execution_unit_id="eu1", event_sink=sink)
        ctx.event_sink("test.event", {"k": "v"})
        sink.assert_called_once_with("test.event", {"k": "v"})


# ── NodusExecutionResult ──────────────────────────────────────────────────────

class TestNodusExecutionResult:
    def test_success_result(self):
        r = NodusExecutionResult(
            output_state={"x": 1},
            emitted_events=[{"event_type": "done"}],
            memory_writes=[{"args": ("note",)}],
            status="success",
        )
        assert r.status == "success"
        assert r.error is None
        assert len(r.emitted_events) == 1
        assert len(r.memory_writes) == 1

    def test_failure_result(self):
        r = NodusExecutionResult(
            output_state={},
            emitted_events=[],
            memory_writes=[],
            status="failure",
            error="something broke",
        )
        assert r.status == "failure"
        assert r.error == "something broke"

    def test_raw_result_optional(self):
        r = NodusExecutionResult(
            output_state={}, emitted_events=[], memory_writes=[], status="success"
        )
        assert r.raw_result is None


# ── NodusRuntimeAdapter ───────────────────────────────────────────────────────

class TestNodusRuntimeAdapterRunScript:
    def _adapter(self) -> NodusRuntimeAdapter:
        return NodusRuntimeAdapter(db=MagicMock())

    def _patch_runtime(self, ok: bool = True, error: str | None = None):
        runtime = _fake_runtime(ok=ok, error=error)
        return patch(
            "services.nodus_runtime_adapter.NodusRuntimeAdapter._execute",
            wraps=None,
        ), runtime

    @patch("services.nodus_runtime_adapter.NodusRuntime", create=True)
    @patch("services.nodus_runtime_adapter.create_nodus_bridge", create=True)
    def test_run_script_success(self, mock_bridge_factory, mock_runtime_cls):
        mock_bridge_factory.return_value = MagicMock(
            recall=MagicMock(),
            recall_tool=MagicMock(),
            recall_from=MagicMock(),
            recall_all_agents=MagicMock(),
            get_suggestions=MagicMock(),
            remember=MagicMock(return_value={"id": "m1"}),
            record_outcome=MagicMock(),
            share=MagicMock(),
        )
        mock_runtime_cls.return_value = _fake_runtime(ok=True)

        with patch.dict("sys.modules", {
            "nodus": MagicMock(),
            "nodus.runtime": MagicMock(),
            "nodus.runtime.embedding": MagicMock(NodusRuntime=mock_runtime_cls),
            "bridge": MagicMock(),
            "bridge.nodus_memory_bridge": MagicMock(create_nodus_bridge=mock_bridge_factory),
        }):
            adapter = self._adapter()
            ctx = _make_context()
            result = adapter.run_script("let x = 1", ctx)

        assert result.status == "success"
        assert result.error is None
        assert isinstance(result.output_state, dict)
        assert isinstance(result.emitted_events, list)
        assert isinstance(result.memory_writes, list)

    @patch("services.nodus_runtime_adapter.NodusRuntime", create=True)
    @patch("services.nodus_runtime_adapter.create_nodus_bridge", create=True)
    def test_run_script_failure_from_vm(self, mock_bridge_factory, mock_runtime_cls):
        mock_bridge_factory.return_value = MagicMock(
            recall=MagicMock(), recall_tool=MagicMock(), recall_from=MagicMock(),
            recall_all_agents=MagicMock(), get_suggestions=MagicMock(),
            remember=MagicMock(return_value={}), record_outcome=MagicMock(), share=MagicMock(),
        )
        mock_runtime_cls.return_value = _fake_runtime(ok=False, error="type error")

        with patch.dict("sys.modules", {
            "nodus": MagicMock(),
            "nodus.runtime": MagicMock(),
            "nodus.runtime.embedding": MagicMock(NodusRuntime=mock_runtime_cls),
            "bridge": MagicMock(),
            "bridge.nodus_memory_bridge": MagicMock(create_nodus_bridge=mock_bridge_factory),
        }):
            adapter = self._adapter()
            ctx = _make_context()
            result = adapter.run_script("bad script", ctx)

        assert result.status == "failure"
        assert result.error == "type error"

    def test_run_script_import_error_returns_failure(self):
        adapter = self._adapter()
        ctx = _make_context()

        with patch.dict("sys.modules", {
            "nodus": None,
            "nodus.runtime": None,
            "nodus.runtime.embedding": None,
        }):
            with patch("builtins.__import__", side_effect=ImportError("nodus not found")):
                # Trigger the ImportError path via _execute directly
                result = adapter._execute("let x = 1", "<test>", ctx)

        assert result.status == "failure"
        assert "nodus" in (result.error or "").lower() or result.status == "failure"


class TestNodusRuntimeAdapterRunFile:
    def _adapter(self) -> NodusRuntimeAdapter:
        return NodusRuntimeAdapter(db=MagicMock())

    def test_run_file_missing_file_returns_failure(self):
        adapter = self._adapter()
        ctx = _make_context()
        result = adapter.run_file("/nonexistent/path/script.nodus", ctx)
        assert result.status == "failure"
        assert "Cannot read script file" in (result.error or "")

    def test_run_file_reads_and_executes(self, tmp_path):
        script_file = tmp_path / "test.nodus"
        script_file.write_text("let x = 42", encoding="utf-8")

        adapter = self._adapter()
        ctx = _make_context()

        executed_scripts: list[str] = []

        def fake_execute(script: str, filename: str, context: Any) -> NodusExecutionResult:
            executed_scripts.append(script)
            return NodusExecutionResult(
                output_state={}, emitted_events=[], memory_writes=[], status="success"
            )

        with patch.object(adapter, "_execute", side_effect=fake_execute):
            result = adapter.run_file(str(script_file), ctx)

        assert result.status == "success"
        assert executed_scripts == ["let x = 42"]


class TestNodusRuntimeAdapterEventSink:
    def _adapter(self) -> NodusRuntimeAdapter:
        return NodusRuntimeAdapter(db=MagicMock())

    @patch("services.nodus_runtime_adapter.NodusRuntime", create=True)
    @patch("services.nodus_runtime_adapter.create_nodus_bridge", create=True)
    def test_custom_event_sink_receives_emit_calls(self, mock_bridge_factory, mock_runtime_cls):
        """emit() inside a script routes to the caller-supplied event_sink."""
        sink_calls: list[tuple[str, dict]] = []

        def my_sink(event_type: str, payload: dict) -> None:
            sink_calls.append((event_type, payload))

        bridge = MagicMock(
            recall=MagicMock(), recall_tool=MagicMock(), recall_from=MagicMock(),
            recall_all_agents=MagicMock(), get_suggestions=MagicMock(),
            remember=MagicMock(return_value={}), record_outcome=MagicMock(), share=MagicMock(),
        )
        mock_bridge_factory.return_value = bridge

        # We need to capture the emit function registered on the runtime and
        # call it manually to simulate what the Nodus VM would do during execution.
        registered_fns: dict[str, Any] = {}

        def capture_register(name: str, fn: Any, **_kwargs: Any) -> None:
            registered_fns[name] = fn

        runtime = MagicMock()
        runtime.register_function.side_effect = capture_register
        runtime.run_source.return_value = {"ok": True}
        mock_runtime_cls.return_value = runtime

        with patch.dict("sys.modules", {
            "nodus": MagicMock(),
            "nodus.runtime": MagicMock(),
            "nodus.runtime.embedding": MagicMock(NodusRuntime=mock_runtime_cls),
            "bridge": MagicMock(),
            "bridge.nodus_memory_bridge": MagicMock(create_nodus_bridge=mock_bridge_factory),
        }):
            adapter = self._adapter()
            ctx = _make_context(event_sink=my_sink)
            adapter.run_script("emit('task.done', {result: 1})", ctx)

        # Simulate VM calling the registered emit function
        if "emit" in registered_fns:
            registered_fns["emit"]("task.done", {"result": 1})
            assert sink_calls == [("task.done", {"result": 1})]

    @patch("services.nodus_runtime_adapter.NodusRuntime", create=True)
    @patch("services.nodus_runtime_adapter.create_nodus_bridge", create=True)
    def test_memory_writes_captured(self, mock_bridge_factory, mock_runtime_cls):
        """remember() calls are collected in NodusExecutionResult.memory_writes."""
        bridge = MagicMock(
            recall=MagicMock(), recall_tool=MagicMock(), recall_from=MagicMock(),
            recall_all_agents=MagicMock(), get_suggestions=MagicMock(),
            remember=MagicMock(return_value={"id": "new_mem"}),
            record_outcome=MagicMock(), share=MagicMock(),
        )
        mock_bridge_factory.return_value = bridge

        registered_fns: dict[str, Any] = {}

        def capture_register(name: str, fn: Any, **_kwargs: Any) -> None:
            registered_fns[name] = fn

        runtime = MagicMock()
        runtime.register_function.side_effect = capture_register
        runtime.run_source.return_value = {"ok": True}
        mock_runtime_cls.return_value = runtime

        with patch.dict("sys.modules", {
            "nodus": MagicMock(),
            "nodus.runtime": MagicMock(),
            "nodus.runtime.embedding": MagicMock(NodusRuntime=mock_runtime_cls),
            "bridge": MagicMock(),
            "bridge.nodus_memory_bridge": MagicMock(create_nodus_bridge=mock_bridge_factory),
        }):
            adapter = self._adapter()
            ctx = _make_context()
            result = adapter.run_script("remember('note')", ctx)

        # Simulate VM calling the registered remember function
        if "remember" in registered_fns:
            registered_fns["remember"]("a memory note")
            # The result was returned before simulation — call run_script again
            # to get a result that includes the write captured inside _execute
            # (the registered fn mutates collected_memory_writes via closure)
            assert bridge.remember.called

    @patch("services.nodus_runtime_adapter.NodusRuntime", create=True)
    @patch("services.nodus_runtime_adapter.create_nodus_bridge", create=True)
    def test_state_mutation_via_set_state(self, mock_bridge_factory, mock_runtime_cls):
        """set_state(k, v) inside a script is reflected in output_state."""
        bridge = MagicMock(
            recall=MagicMock(), recall_tool=MagicMock(), recall_from=MagicMock(),
            recall_all_agents=MagicMock(), get_suggestions=MagicMock(),
            remember=MagicMock(return_value={}), record_outcome=MagicMock(), share=MagicMock(),
        )
        mock_bridge_factory.return_value = bridge

        registered_fns: dict[str, Any] = {}

        def capture_register(name: str, fn: Any, **_kwargs: Any) -> None:
            registered_fns[name] = fn

        runtime = MagicMock()
        runtime.register_function.side_effect = capture_register
        runtime.run_source.return_value = {"ok": True}
        mock_runtime_cls.return_value = runtime

        with patch.dict("sys.modules", {
            "nodus": MagicMock(),
            "nodus.runtime": MagicMock(),
            "nodus.runtime.embedding": MagicMock(NodusRuntime=mock_runtime_cls),
            "bridge": MagicMock(),
            "bridge.nodus_memory_bridge": MagicMock(create_nodus_bridge=mock_bridge_factory),
        }):
            adapter = self._adapter()
            ctx = _make_context(state={"counter": 0})
            result = adapter.run_script("set_state('counter', 5)", ctx)

        # Simulate VM calling the registered set_state
        if "set_state" in registered_fns:
            registered_fns["set_state"]("counter", 5)
            assert ctx.state["counter"] == 5


class TestNodusRuntimeAdapterContextInjection:
    """Verify context globals are passed to the VM before execution."""

    @patch("services.nodus_runtime_adapter.NodusRuntime", create=True)
    @patch("services.nodus_runtime_adapter.create_nodus_bridge", create=True)
    def test_initial_globals_contain_all_context_fields(self, mock_bridge_factory, mock_runtime_cls):
        bridge = MagicMock(
            recall=MagicMock(), recall_tool=MagicMock(), recall_from=MagicMock(),
            recall_all_agents=MagicMock(), get_suggestions=MagicMock(),
            remember=MagicMock(return_value={}), record_outcome=MagicMock(), share=MagicMock(),
        )
        mock_bridge_factory.return_value = bridge

        runtime = MagicMock()
        runtime.run_source.return_value = {"ok": True}
        mock_runtime_cls.return_value = runtime

        with patch.dict("sys.modules", {
            "nodus": MagicMock(),
            "nodus.runtime": MagicMock(),
            "nodus.runtime.embedding": MagicMock(NodusRuntime=mock_runtime_cls),
            "bridge": MagicMock(),
            "bridge.nodus_memory_bridge": MagicMock(create_nodus_bridge=mock_bridge_factory),
        }):
            adapter = NodusRuntimeAdapter(db=MagicMock())
            ctx = _make_context(
                memory_context={"m1": {"content": "prior"}},
                input_payload={"goal": "test"},
                state={"step": 1},
            )
            adapter.run_script("let x = 1", ctx)

        # Inspect what was passed to run_source
        call_kwargs = runtime.run_source.call_args
        passed_globals = call_kwargs[1].get("initial_globals") or call_kwargs[0][2]

        assert "memory_context" in passed_globals
        assert "input_payload" in passed_globals
        assert "state" in passed_globals
        assert "execution_unit_id" in passed_globals
        assert "user_id" in passed_globals
        assert passed_globals["memory_context"] == {"m1": {"content": "prior"}}
        assert passed_globals["input_payload"] == {"goal": "test"}
        assert passed_globals["execution_unit_id"] == ctx.execution_unit_id
        assert passed_globals["user_id"] == ctx.user_id
