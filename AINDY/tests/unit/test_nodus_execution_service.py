from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock
from unittest.mock import patch

from runtime.nodus_runtime_adapter import NodusExecutionResult


def _memory_context():
    return SimpleNamespace(formatted={"m1": {"content": "prior"}}, ids=["m1"])


def test_build_nodus_execution_record_normalizes_runtime_metadata():
    from runtime import nodus_execution_service as service

    nodus_result = NodusExecutionResult(
        output_state={"answer": 42},
        emitted_events=[{"event_type": "done"}],
        memory_writes=[{"args": ["remembered"]}],
        status="success",
        error=None,
    )

    summary = service.build_nodus_execution_summary(nodus_result)
    record = service.build_nodus_execution_record(
        flow_status="SUCCESS",
        trace_id="trace-1",
        run_id="run-1",
        nodus_summary=summary,
        nodus_status=nodus_result.status,
        output_state=nodus_result.output_state,
        events=nodus_result.emitted_events,
        memory_writes=nodus_result.memory_writes,
        error=nodus_result.error,
    )

    assert summary == {
        "status": "success",
        "output_state": {"answer": 42},
        "events_emitted": 1,
        "memory_writes": 1,
        "error": None,
    }
    assert record["status"] == "SUCCESS"
    assert record["trace_id"] == "trace-1"
    assert record["run_id"] == "run-1"
    assert record["nodus_status"] == "success"
    assert record["events_emitted"] == 1
    assert record["memory_writes_count"] == 1
    assert record["memory_writes"] == [{"args": ["remembered"]}]


def test_execute_nodus_task_payload_delegates_to_runtime_adapter(monkeypatch):
    from runtime import nodus_execution_service as service

    adapter_instance = MagicMock()
    adapter_instance.run_script.return_value = NodusExecutionResult(
        output_state={"answer": 42},
        emitted_events=[{"event_type": "done", "payload": {"ok": True}}],
        memory_writes=[{"args": ["remembered"]}],
        status="success",
        error=None,
        raw_result={"ok": True},
    )
    adapter_cls = MagicMock(return_value=adapter_instance)
    context_cls = MagicMock(side_effect=lambda **kwargs: SimpleNamespace(**kwargs))
    orchestrator_instance = MagicMock()
    orchestrator_instance.get_context.return_value = _memory_context()
    orchestrator_cls = MagicMock(return_value=orchestrator_instance)
    feedback_engine = MagicMock()
    feedback_cls = MagicMock(return_value=feedback_engine)
    create_memory_node = MagicMock()

    monkeypatch.setattr(service, "authorize_nodus_execution", lambda **kwargs: {
        "allowed_operations": ["recall", "remember"],
        "required_capabilities": ["memory.read"],
        "restricted_operations": ["share"],
    })
    monkeypatch.setattr(service, "NodusRuntimeAdapter", adapter_cls)
    monkeypatch.setattr(service, "NodusExecutionContext", context_cls)

    with patch.dict("sys.modules", {
        "nodus": MagicMock(),
        "nodus.runtime": MagicMock(),
        "nodus.runtime.embedding": MagicMock(NodusRuntime=MagicMock()),
    }):
        with patch("runtime.memory.MemoryOrchestrator", orchestrator_cls), \
             patch("runtime.memory.memory_feedback.MemoryFeedbackEngine", feedback_cls), \
             patch("bridge.create_memory_node", create_memory_node):
            result = service.execute_nodus_task_payload(
                task_name="memory smoke",
                task_code="remember('x')",
                db=MagicMock(),
                user_id="11111111-1111-1111-1111-111111111111",
                session_tags=["pytest"],
            )

    adapter_cls.assert_called_once()
    adapter_instance.run_script.assert_called_once()
    ctx = adapter_instance.run_script.call_args.args[1]
    assert ctx.user_id == "11111111-1111-1111-1111-111111111111"
    assert ctx.input_payload["allowed_operations"] == ["recall", "remember"]
    assert ctx.state["memory_ids"] == ["m1"]

    assert result["status"] == "executed"
    assert result["memory_bridge"] == "restricted"
    assert result["allowed_operations"] == ["recall", "remember"]
    assert result["required_capabilities"] == ["memory.read"]
    assert result["restricted_operations"] == ["share"]
    assert result["result"]["ok"] is True
    assert result["result"]["nodus_status"] == "success"
    assert result["result"]["output_state"] == {"answer": 42}
    assert result["result"]["events"][0]["event_type"] == "done"
    assert result["result"]["events_emitted"] == 1
    assert result["result"]["memory_writes"] == [{"args": ["remembered"]}]
    assert result["result"]["memory_writes_count"] == 1
    create_memory_node.assert_called_once()
    feedback_engine.record_usage.assert_called_once()


def test_execute_nodus_task_payload_returns_bridge_ready_when_runtime_missing(monkeypatch):
    from runtime import nodus_execution_service as service

    monkeypatch.setattr(service, "authorize_nodus_execution", lambda **kwargs: {
        "allowed_operations": ["recall"],
        "required_capabilities": [],
        "restricted_operations": [],
    })

    real_import = __import__

    def _import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "nodus.runtime.embedding":
            raise ImportError("nodus runtime missing")
        return real_import(name, globals, locals, fromlist, level)

    with patch("builtins.__import__", side_effect=_import):
        result = service.execute_nodus_task_payload(
            task_name="missing runtime",
            task_code="let x = 1",
            db=MagicMock(),
            user_id="11111111-1111-1111-1111-111111111111",
        )

    assert result["status"] == "bridge_ready"
    assert "Nodus runtime not found" in result["message"]
    assert "POST /memory/recall/v3" in result["available_operations"]
