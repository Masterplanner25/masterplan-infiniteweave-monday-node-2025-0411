from __future__ import annotations

import json
import subprocess
import time
import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

from AINDY.runtime.nodus_runtime_adapter import (
    NodusExecutionContext,
    NodusExecutionResult,
    NodusRuntimeAdapter,
)


def _make_context(**overrides: Any) -> NodusExecutionContext:
    defaults = {
        "user_id": str(uuid.uuid4()),
        "execution_unit_id": str(uuid.uuid4()),
        "memory_context": {"mem1": {"id": "mem1", "content": "prior run", "tags": ["tag"]}},
        "input_payload": {"goal": "test"},
        "state": {"counter": 0},
    }
    defaults.update(overrides)
    return NodusExecutionContext(**defaults)


def _completed(stdout_payload: dict[str, Any], *, returncode: int = 0, stderr: str = "") -> SimpleNamespace:
    return SimpleNamespace(
        returncode=returncode,
        stdout=json.dumps(stdout_payload),
        stderr=stderr,
    )


class TestNodusExecutionContext:
    def test_defaults(self) -> None:
        ctx = NodusExecutionContext(user_id="u1", execution_unit_id="eu1")
        assert ctx.memory_context == {}
        assert ctx.input_payload == {}
        assert ctx.state == {}
        assert ctx.event_sink is None
        assert ctx.max_execution_ms is None

    def test_event_sink_callable(self) -> None:
        sink = MagicMock()
        ctx = NodusExecutionContext(user_id="u1", execution_unit_id="eu1", event_sink=sink)
        ctx.event_sink("test.event", {"k": "v"})
        sink.assert_called_once_with("test.event", {"k": "v"})


class TestNodusExecutionResult:
    def test_success_result(self) -> None:
        result = NodusExecutionResult(
            output_state={"x": 1},
            emitted_events=[{"event_type": "done"}],
            memory_writes=[{"args": ["note"]}],
            status="success",
        )
        assert result.status == "success"
        assert result.error is None


class TestNodusRuntimeAdapter:
    def _adapter(self) -> NodusRuntimeAdapter:
        return NodusRuntimeAdapter(db=MagicMock())

    @patch("AINDY.runtime.nodus_runtime_adapter.subprocess.run")
    def test_run_script_success(self, mock_run: MagicMock) -> None:
        mock_run.return_value = _completed(
            {
                "status": "success",
                "output_state": {"counter": 5},
                "emitted_events": [],
                "memory_writes": [],
                "error": None,
                "stdout_log": "",
            }
        )

        adapter = self._adapter()
        ctx = _make_context()
        result = adapter.run_script("set_state('counter', 5)", ctx)

        assert result.status == "success"
        assert result.output_state == {"counter": 5}
        assert ctx.state == {"counter": 5}
        mock_run.assert_called_once()

    @patch("AINDY.runtime.nodus_runtime_adapter.subprocess.run")
    def test_run_script_failure_from_worker(self, mock_run: MagicMock) -> None:
        mock_run.return_value = _completed(
            {
                "status": "failure",
                "output_state": {},
                "emitted_events": [],
                "memory_writes": [],
                "error": "type error",
                "stdout_log": "",
            }
        )

        result = self._adapter().run_script("bad script", _make_context())

        assert result.status == "failure"
        assert result.error == "type error"

    @patch("AINDY.runtime.nodus_runtime_adapter.subprocess.run")
    def test_run_script_worker_non_zero_status(self, mock_run: MagicMock) -> None:
        mock_run.return_value = SimpleNamespace(returncode=1, stdout="", stderr="worker exploded")

        result = self._adapter().run_script("bad script", _make_context())

        assert result.status == "failure"
        assert result.error == "worker exploded"

    @patch("AINDY.runtime.nodus_runtime_adapter.subprocess.run")
    def test_run_script_timeout_returns_failure_within_budget(self, mock_run: MagicMock) -> None:
        def _timeout(*_args: Any, **_kwargs: Any) -> None:
            raise subprocess.TimeoutExpired(cmd="python nodus_worker.py", timeout=0.2)

        mock_run.side_effect = _timeout
        adapter = self._adapter()
        ctx = _make_context(max_execution_ms=200)

        started = time.monotonic()
        result = adapter.run_script("while True:\n    pass\n", ctx)
        elapsed = time.monotonic() - started

        assert result.status == "failure"
        assert "timeout" in (result.error or "").lower()
        assert elapsed <= (ctx.max_execution_ms / 1000.0) + 1

    @patch("AINDY.runtime.nodus_runtime_adapter._apply_deferred_events")
    @patch("AINDY.runtime.nodus_runtime_adapter._apply_deferred_memory_writes")
    @patch("AINDY.runtime.nodus_runtime_adapter.subprocess.run")
    def test_emit_event_is_returned_and_replayed(
        self,
        mock_run: MagicMock,
        mock_apply_memory_writes: MagicMock,
        mock_apply_events: MagicMock,
    ) -> None:
        mock_run.return_value = _completed(
            {
                "status": "success",
                "output_state": {},
                "emitted_events": [
                    {
                        "type": "test.event",
                        "event_type": "test.event",
                        "payload": {},
                        "execution_unit_id": "eu1",
                        "user_id": "u1",
                    }
                ],
                "memory_writes": [],
                "error": None,
                "stdout_log": "",
            }
        )

        result = self._adapter().run_script("emit('test.event', {})", _make_context(user_id="u1", execution_unit_id="eu1"))

        assert result.status == "success"
        assert result.emitted_events == [
            {
                "type": "test.event",
                "event_type": "test.event",
                "payload": {},
                "execution_unit_id": "eu1",
                "user_id": "u1",
            }
        ]
        mock_apply_memory_writes.assert_called_once()
        mock_apply_events.assert_called_once()

    @patch("AINDY.runtime.nodus_runtime_adapter.subprocess.run")
    def test_wait_result_is_preserved(self, mock_run: MagicMock) -> None:
        mock_run.return_value = _completed(
            {
                "status": "waiting",
                "output_state": {"nodus_wait_event_type": "approval.received"},
                "emitted_events": [],
                "memory_writes": [],
                "error": None,
                "stdout_log": "",
                "wait_for": "approval.received",
            }
        )

        result = self._adapter().run_script("event.wait('approval.received')", _make_context())

        assert result.status == "waiting"
        assert result.output_state["nodus_wait_event_type"] == "approval.received"

    def test_run_file_missing_file_returns_failure(self) -> None:
        result = self._adapter().run_file("/nonexistent/path/script.nodus", _make_context())
        assert result.status == "failure"
        assert "Cannot read script file" in (result.error or "")

    @patch("AINDY.runtime.nodus_runtime_adapter.NodusRuntimeAdapter.run_script")
    def test_run_file_reads_and_executes(self, mock_run_script: MagicMock, tmp_path: Any) -> None:
        script_file = tmp_path / "test.nodus"
        script_file.write_text("let x = 42", encoding="utf-8")
        mock_run_script.return_value = NodusExecutionResult(
            output_state={},
            emitted_events=[],
            memory_writes=[],
            status="success",
        )

        result = self._adapter().run_file(str(script_file), _make_context())

        assert result.status == "success"
        mock_run_script.assert_called_once()
