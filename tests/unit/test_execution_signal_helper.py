from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import AINDY.core.execution_signal_helper as helper


def test_queue_system_event_queues_during_pipeline(monkeypatch):
    ctx = SimpleNamespace(metadata={})

    monkeypatch.setattr(helper, "is_pipeline_active", lambda: True)
    monkeypatch.setattr(helper, "get_current_execution_context", lambda: ctx)
    monkeypatch.setattr(helper.uuid, "uuid4", lambda: "event-123")

    event_id = helper.queue_system_event(
        db=MagicMock(),
        event_type="execution.started",
        user_id="user-1",
        trace_id="trace-1",
        payload={"status": "queued"},
        required=True,
    )

    assert event_id == "event-123"
    queued = ctx.metadata["queued_execution_signals"]
    assert queued["memory"] == []
    assert queued["events"] == [
        {
            "id": "event-123",
            "type": "execution.started",
            "event_type": "execution.started",
            "payload": {"status": "queued"},
            "parent_event_id": None,
            "source": None,
            "agent_id": None,
            "required": True,
            "trace_id": "trace-1",
            "user_id": "user-1",
        }
    ]


def test_queue_system_event_emits_immediately_outside_pipeline(monkeypatch):
    import AINDY.core.system_event_service as event_service

    emit = MagicMock(return_value="persisted-id")
    monkeypatch.setattr(helper, "is_pipeline_active", lambda: False)
    monkeypatch.setattr(helper, "get_current_execution_context", lambda: None)
    monkeypatch.setattr(event_service, "emit_system_event", emit)

    result = helper.queue_system_event(
        db="db-session",
        event_type="execution.completed",
        user_id="user-2",
        trace_id="trace-2",
        payload={"ok": True},
    )

    assert result == "persisted-id"
    emit.assert_called_once_with(
        db="db-session",
        event_type="execution.completed",
        user_id="user-2",
        trace_id="trace-2",
        parent_event_id=None,
        source=None,
        agent_id=None,
        payload={"ok": True},
        required=False,
    )


def test_queue_memory_capture_queues_during_pipeline(monkeypatch):
    ctx = SimpleNamespace(metadata={})

    monkeypatch.setattr(helper, "is_pipeline_active", lambda: True)
    monkeypatch.setattr(helper, "get_current_execution_context", lambda: ctx)

    result = helper.queue_memory_capture(
        db=MagicMock(),
        user_id="user-1",
        agent_namespace="agent.loop",
        event_type="task.completed",
        content="Task finished",
        source="task.worker",
        tags=["task", "done"],
        node_type="outcome",
        context={"task_id": "t-1"},
        extra={"score": 0.9},
        force=True,
    )

    assert result == {
        "queued": True,
        "event_type": "task.completed",
        "content": "Task finished",
        "source": "task.worker",
    }
    assert ctx.metadata["queued_execution_signals"]["events"] == []
    assert ctx.metadata["queued_execution_signals"]["memory"] == [
        {
            "event_type": "task.completed",
            "content": "Task finished",
            "source": "task.worker",
            "tags": ["task", "done"],
            "node_type": "outcome",
            "extra": {"score": 0.9},
            "force": True,
            "user_id": "user-1",
            "agent_namespace": "agent.loop",
            "context": {"task_id": "t-1"},
        }
    ]


def test_queue_memory_capture_executes_engine_when_allowed(monkeypatch):
    import AINDY.memory.memory_capture_engine as capture_engine_module

    ctx = SimpleNamespace(metadata={})
    engine = MagicMock()
    engine.evaluate_and_capture.return_value = {"captured": True}
    engine_cls = MagicMock(return_value=engine)

    monkeypatch.setattr(helper, "is_pipeline_active", lambda: True)
    monkeypatch.setattr(helper, "get_current_execution_context", lambda: ctx)
    monkeypatch.setattr(capture_engine_module, "MemoryCaptureEngine", engine_cls)

    result = helper.queue_memory_capture(
        db="db-session",
        user_id="user-3",
        agent_namespace="agent.memory",
        event_type="feedback.latency_spike",
        content="Latency spike detected",
        source="feedback.loop",
        allow_when_pipeline_active=True,
    )

    assert result == {"captured": True}
    engine_cls.assert_called_once_with(
        db="db-session",
        user_id="user-3",
        agent_namespace="agent.memory",
    )
    engine.evaluate_and_capture.assert_called_once_with(
        event_type="feedback.latency_spike",
        content="Latency spike detected",
        source="feedback.loop",
        tags=None,
        node_type=None,
        context={},
        extra=None,
        force=False,
        allow_when_pipeline_active=True,
    )


def test_record_agent_event_delegates(monkeypatch):
    import AINDY.agents.agent_event_service as agent_event_service

    emit = MagicMock(return_value={"ok": True})
    monkeypatch.setattr(agent_event_service, "emit_event", emit)

    result = helper.record_agent_event("agent.started", agent_id="agent-1")

    assert result == {"ok": True}
    emit.assert_called_once_with("agent.started", agent_id="agent-1")
