from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock
from unittest.mock import patch

from AINDY.runtime.nodus_runtime_adapter import NodusExecutionResult


def _memory_context():
    return SimpleNamespace(formatted={"m1": {"content": "prior"}}, ids=["m1"])


def test_build_nodus_execution_record_normalizes_runtime_metadata():
    from AINDY.runtime import nodus_execution_service as service

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
    from AINDY.runtime import nodus_execution_service as service

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
        with patch("AINDY.runtime.memory.MemoryOrchestrator", orchestrator_cls), \
             patch("AINDY.runtime.memory.memory_feedback.MemoryFeedbackEngine", feedback_cls), \
             patch("AINDY.bridge.create_memory_node", create_memory_node):
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
    from AINDY.runtime import nodus_execution_service as service

    monkeypatch.setattr(service, "authorize_nodus_execution", lambda **kwargs: {
        "allowed_operations": ["recall"],
        "required_capabilities": [],
        "restricted_operations": [],
    })

    import sys

    # Remove both bare and AINDY-prefixed module from cache so the lazy import triggers
    _saved = {}
    for key in list(sys.modules.keys()):
        if "nodus.runtime.embedding" in key:
            _saved[key] = sys.modules.pop(key)

    real_import = __import__

    def _import(name, globals=None, locals=None, fromlist=(), level=0):
        if "nodus.runtime.embedding" in name:
            raise ImportError("nodus runtime missing")
        return real_import(name, globals, locals, fromlist, level)

    try:
        with patch("builtins.__import__", side_effect=_import):
            result = service.execute_nodus_task_payload(
                task_name="missing runtime",
                task_code="let x = 1",
                db=MagicMock(),
                user_id="11111111-1111-1111-1111-111111111111",
            )
    finally:
        sys.modules.update(_saved)

    assert result["status"] == "bridge_ready"
    assert "Nodus runtime not found" in result["message"]
    assert "POST /memory/recall/v3" in result["available_operations"]


def test_run_nodus_script_via_flow_uses_canonical_flow_runner(monkeypatch):
    from AINDY.runtime import nodus_execution_service as service

    mock_runner = MagicMock()
    mock_runner.start.return_value = {"status": "SUCCESS", "run_id": "run-1", "trace_id": "trace-1"}
    runner_cls = MagicMock(return_value=mock_runner)

    monkeypatch.setattr(service, "ensure_nodus_script_flow_registered", lambda: None)

    with patch("AINDY.runtime.flow_engine.FLOW_REGISTRY", {"nodus_execute": {"start": "nodus.execute"}}), \
         patch("AINDY.runtime.flow_engine.PersistentFlowRunner", runner_cls), \
         patch("AINDY.utils.uuid_utils.normalize_uuid", return_value="user-1"):
        result = service.run_nodus_script_via_flow(
            script="let x = 1",
            input_payload={"value": 1},
            error_policy="fail",
            db=MagicMock(),
            user_id="user-1",
            workflow_type="nodus_schedule",
            trace_id="trace-9",
            extra_initial_state={"schedule_id": "job-1"},
        )

    runner_cls.assert_called_once()
    mock_runner.start.assert_called_once_with(
        initial_state={
            "nodus_script": "let x = 1",
            "nodus_input_payload": {"value": 1},
            "nodus_error_policy": "fail",
            "trace_id": "trace-9",
            "schedule_id": "job-1",
        },
        flow_name="nodus_execute",
    )
    assert result["status"] == "SUCCESS"


def test_format_nodus_flow_result_uses_shared_execution_record_shape():
    from AINDY.runtime import nodus_execution_service as service

    result = service.format_nodus_flow_result(
        {
            "status": "SUCCESS",
            "trace_id": "trace-1",
            "run_id": "run-1",
            "state": {
                "nodus_status": "success",
                "nodus_output_state": {"value": 2},
                "nodus_events": [{"event_type": "done"}],
                "nodus_memory_writes": [{"args": ["memo"]}],
                "nodus_execute_result": {
                    "status": "success",
                    "output_state": {"value": 2},
                    "events_emitted": 1,
                    "memory_writes": 1,
                    "error": None,
                },
            },
            "data": {},
        }
    )

    assert result["status"] == "SUCCESS"
    assert result["nodus_status"] == "success"
    assert result["execution_record"]["workflow_type"] == "nodus_execute"
    assert result["execution_record"]["trace_id"] == "trace-1"


def test_execute_agent_run_via_nodus_delegates_to_canonical_agent_flow_helper():
    from AINDY.runtime import nodus_execution_service as service

    with patch("AINDY.runtime.nodus_execution_service.execute_agent_flow_orchestration", return_value={"status": "SUCCESS"}) as mock_execute:
        result = service.execute_agent_run_via_nodus(
            run_id="run-1",
            plan={"steps": []},
            user_id="user-1",
            db=MagicMock(),
            correlation_id="corr-1",
            execution_token={"execution_token": "token"},
        )

    mock_execute.assert_called_once_with(
        run_id="run-1",
        plan={"steps": []},
        user_id="user-1",
        db=mock_execute.call_args.kwargs["db"],
        correlation_id="corr-1",
        execution_token={"execution_token": "token"},
        capability_token=None,
    )
    assert result["status"] == "SUCCESS"


def test_adapter_execute_with_flow_is_compatibility_wrapper():
    from AINDY.runtime.nodus_adapter import NodusAgentAdapter

    with patch("AINDY.runtime.nodus_execution_service.execute_agent_flow_orchestration", return_value={"status": "SUCCESS"}) as mock_execute:
        result = NodusAgentAdapter.execute_with_flow(
            run_id="run-2",
            plan={"steps": [{"tool": "task.create"}]},
            user_id="user-2",
            db=MagicMock(),
            correlation_id="corr-2",
            capability_token={"capability_token": "token"},
        )

    mock_execute.assert_called_once_with(
        run_id="run-2",
        plan={"steps": [{"tool": "task.create"}]},
        user_id="user-2",
        db=mock_execute.call_args.kwargs["db"],
        correlation_id="corr-2",
        execution_token=None,
        capability_token={"capability_token": "token"},
    )
    assert result["status"] == "SUCCESS"


def test_execute_agent_run_via_nodus_honors_patched_adapter_entrypoint():
    from AINDY.runtime import nodus_execution_service as service

    with patch("AINDY.runtime.nodus_adapter.NodusAgentAdapter.execute_with_flow", return_value={"status": "SUCCESS", "patched": True}) as mock_execute:
        result = service.execute_agent_run_via_nodus(
            run_id="run-3",
            plan={"steps": [{"tool": "task.create"}]},
            user_id="user-3",
            db=MagicMock(),
            correlation_id="corr-3",
            capability_token={"capability_token": "token"},
        )

    mock_execute.assert_called_once_with(
        run_id="run-3",
        plan={"steps": [{"tool": "task.create"}]},
        user_id="user-3",
        db=mock_execute.call_args.kwargs["db"],
        correlation_id="corr-3",
        execution_token=None,
        capability_token={"capability_token": "token"},
    )
    assert result == {"status": "SUCCESS", "patched": True}
