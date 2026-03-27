from __future__ import annotations

import importlib
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def _reset_trace_context():
    from utils.trace_context import _trace_id_ctx

    token = _trace_id_ctx.set("-")
    try:
        yield
    finally:
        _trace_id_ctx.reset(token)
        _trace_id_ctx.set("-")


class _FakeQuery:
    def __init__(self, db, model):
        self.db = db
        self.model = model

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def all(self):
        name = getattr(self.model, "__name__", str(self.model))
        if name == "FlowHistory":
            return list(self.db.flow_history)
        return []

    def first(self):
        name = getattr(self.model, "__name__", str(self.model))
        if name == "FlowRun":
            return self.db.flow_run
        if name == "AgentRun":
            return self.db.agent_run
        return None


class _FakeDB:
    def __init__(self):
        self.flow_run = None
        self.flow_history = []
        self.agent_run = None
        self.automation_logs = {}
        self.system_events = []

    def add(self, obj):
        name = obj.__class__.__name__
        if name == "FlowRun":
            if getattr(obj, "id", None) is None:
                obj.id = str(uuid.uuid4())
            self.flow_run = obj
        elif name == "FlowHistory":
            if getattr(obj, "id", None) is None:
                obj.id = str(uuid.uuid4())
            if getattr(obj, "created_at", None) is None:
                obj.created_at = datetime.now(timezone.utc)
            self.flow_history.append(obj)
        elif name == "AutomationLog":
            if getattr(obj, "id", None) is None:
                obj.id = str(uuid.uuid4())
            if getattr(obj, "attempt_count", None) is None:
                obj.attempt_count = 0
            self.automation_logs[str(obj.id)] = obj
        elif name == "SystemEvent":
            if getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()
            if getattr(obj, "timestamp", None) is None:
                obj.timestamp = datetime.now(timezone.utc)
            self.system_events.append(obj)

    def commit(self):
        return None

    def flush(self):
        return None

    def refresh(self, obj):
        return None

    def query(self, model):
        name = getattr(model, "__name__", str(model))
        if name == "AutomationLog":
            class _AutomationLogQuery:
                def __init__(self, db):
                    self.db = db
                    self.log_id = None

                def filter(self_inner, criterion):
                    self_inner.log_id = str(getattr(getattr(criterion, "right", None), "value", criterion))
                    return self_inner

                def first(self_inner):
                    return self_inner.db.automation_logs.get(self_inner.log_id)

            return _AutomationLogQuery(self)
        return _FakeQuery(self, model)

    def close(self):
        return None


def test_flow_success_emits_start_and_end_events(monkeypatch):
    from services.flow_engine import PersistentFlowRunner

    events = []

    def _capture(**kwargs):
        events.append(kwargs["event_type"])

    monkeypatch.setattr("services.flow_engine.emit_system_event", _capture)
    monkeypatch.setattr("services.flow_engine.emit_error_event", lambda **kwargs: None)
    monkeypatch.setattr(
        "services.flow_engine.execute_node",
        lambda node_name, state, context: {"status": "SUCCESS", "output_patch": {"done": True}},
    )
    monkeypatch.setattr(PersistentFlowRunner, "_capture_flow_completion", lambda *args, **kwargs: None)

    db = _FakeDB()
    flow = {"start": "only", "edges": {}, "end": ["only"]}
    runner = PersistentFlowRunner(flow=flow, db=db, user_id=str(uuid.uuid4()), workflow_type="test_flow")

    result = runner.start({"input": "x"}, flow_name="test_flow")

    assert result["status"] == "SUCCESS"
    assert events == ["execution.started", "execution.completed"]


def test_flow_failure_emits_failure_and_error_events(monkeypatch):
    from services.flow_engine import PersistentFlowRunner

    events = []

    def _capture_event(**kwargs):
        events.append(kwargs["event_type"])

    def _capture_error(**kwargs):
        events.append(f"error.{kwargs['error_type']}")

    monkeypatch.setattr("services.flow_engine.emit_system_event", _capture_event)
    monkeypatch.setattr("services.flow_engine.emit_error_event", _capture_error)
    monkeypatch.setattr(
        "services.flow_engine.execute_node",
        lambda node_name, state, context: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    db = _FakeDB()
    flow = {"start": "explode", "edges": {}, "end": ["explode"]}
    runner = PersistentFlowRunner(flow=flow, db=db, user_id=str(uuid.uuid4()), workflow_type="test_flow")

    result = runner.start({"input": "x"}, flow_name="test_flow")

    assert result["status"] == "FAILED"
    assert "execution.started" in events
    assert "execution.failed" in events
    assert "error.execution" in events


def test_loop_execution_emits_started_and_decision_events(monkeypatch):
    from services.infinity_orchestrator import execute

    events = []

    def _capture(**kwargs):
        events.append((kwargs["event_type"], kwargs.get("payload", {})))

    monkeypatch.setattr("services.infinity_orchestrator.emit_system_event", _capture)
    monkeypatch.setattr(
        "services.infinity_orchestrator.calculate_infinity_score",
        lambda **kwargs: {
            "master_score": 71.0,
            "kpis": {
                "execution_speed": 72.0,
                "decision_efficiency": 74.0,
                "ai_productivity_boost": 65.0,
                "focus_quality": 61.0,
                "masterplan_progress": 70.0,
            },
            "metadata": {"confidence": "high"},
        },
    )
    monkeypatch.setattr(
        "services.infinity_orchestrator.run_loop",
        lambda **kwargs: SimpleNamespace(
            id=uuid.uuid4(),
            trace_id="trace-loop",
            decision_type="review_plan",
            applied_at=datetime.now(timezone.utc),
            adjustment_payload={"next_action": {"type": "review_plan", "title": "Review plan"}},
        ),
    )
    monkeypatch.setattr(
        "services.infinity_orchestrator.serialize_adjustment",
        lambda adjustment: {
            "id": str(adjustment.id),
            "trace_id": adjustment.trace_id,
            "decision_type": adjustment.decision_type,
            "adjustment_payload": adjustment.adjustment_payload,
        },
    )

    result = execute(user_id=str(uuid.uuid4()), trigger_event="task_completed", db=MagicMock())

    assert result["next_action"]["type"] == "review_plan"
    assert events[0][0] == "loop.started"
    assert events[1][0] == "loop.decision"
    assert events[1][1]["next_action"]["type"] == "review_plan"


def test_agent_step_success_emits_system_event(monkeypatch):
    from services.nodus_adapter import agent_execute_step

    events = []
    agent_run = SimpleNamespace(id=uuid.uuid4(), steps_completed=0, current_step=0)

    class _AgentDB:
        def __init__(self):
            self.agent_run = agent_run

        def add(self, obj):
            return None

        def commit(self):
            return None

        def query(self, model):
            class _Query:
                def filter(self_inner, *args, **kwargs):
                    return self_inner

                def first(self_inner):
                    return agent_run

            return _Query()

    monkeypatch.setattr("services.nodus_adapter.check_tool_capability", lambda **kwargs: {"ok": True})
    monkeypatch.setattr("services.nodus_adapter.execute_tool", lambda **kwargs: {"success": True, "result": {"ok": True}, "error": None})
    monkeypatch.setattr("services.nodus_adapter.emit_system_event", lambda **kwargs: events.append(kwargs["event_type"]))

    state = {
        "steps": [{"tool": "task.create", "args": {}, "risk_level": "low", "description": "d"}],
        "current_step_index": 0,
        "agent_run_id": str(agent_run.id),
        "user_id": str(uuid.uuid4()),
        "correlation_id": "run_trace",
        "execution_token": {"granted_tools": ["task.create"]},
        "step_results": [],
    }
    context = {"db": _AgentDB(), "trace_id": "run_trace"}

    result = agent_execute_step(state, context)

    assert result["status"] == "SUCCESS"
    assert "agent.step.completed" in events


def test_memory_write_requires_system_event(monkeypatch):
    from services.memory_capture_engine import MemoryCaptureEngine
    from services.system_event_service import SystemEventEmissionError

    class _Dao:
        def save(self, **kwargs):
            return {"id": str(uuid.uuid4())}

        def _get_model_by_id(self, *args, **kwargs):
            return None

    engine = MemoryCaptureEngine(db=MagicMock(), user_id=str(uuid.uuid4()))
    engine._dao = _Dao()
    monkeypatch.setattr(engine, "_is_duplicate", lambda content: False)
    monkeypatch.setattr(engine, "_auto_link", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "services.memory_capture_engine.emit_system_event",
        lambda **kwargs: (_ for _ in ()).throw(SystemEventEmissionError("missing memory event")),
    )
    emitted_errors = []
    monkeypatch.setattr(
        "services.memory_capture_engine.emit_error_event",
        lambda **kwargs: emitted_errors.append(f"error.{kwargs['error_type']}"),
    )

    with pytest.raises(SystemEventEmissionError):
        engine.evaluate_and_capture(
            event_type="task_completed",
            content="completed task",
            source="test",
            force=True,
        )

    assert emitted_errors == ["error.memory_write"]


def test_async_job_success_persists_execution_events(monkeypatch):
    from db.models.automation_log import AutomationLog
    from services.async_job_service import _execute_job

    db = _FakeDB()
    log = AutomationLog(
        source="test",
        task_name="test.job",
        payload={"value": 1},
        status="pending",
        max_attempts=1,
        user_id=uuid.uuid4(),
    )
    db.add(log)

    monkeypatch.setattr("services.async_job_service.SessionLocal", lambda: db)
    monkeypatch.setitem(
        __import__("services.async_job_service", fromlist=["_JOB_REGISTRY"])._JOB_REGISTRY,
        "test.job",
        lambda payload, session: {"ok": True, "payload": payload},
    )

    _execute_job(log.id, "test.job", {"value": 1})

    assert db.automation_logs[str(log.id)].status == "success"
    assert len(db.system_events) >= 2
    assert [event.type for event in db.system_events[:2]] == [
        "execution.started",
        "execution.completed",
    ]


def test_auth_success_routes_emit_system_events(monkeypatch):
    auth_router = importlib.import_module("routes.auth_router")
    from schemas.auth_schemas import LoginRequest, RegisterRequest

    events = []
    user = SimpleNamespace(
        id=uuid.uuid4(),
        email="user@example.com",
        username="user_example",
    )

    monkeypatch.setattr(auth_router, "register_user", lambda **kwargs: user)
    monkeypatch.setattr(auth_router, "authenticate_user", lambda **kwargs: user)
    monkeypatch.setattr(auth_router, "create_access_token", lambda payload: "token")
    monkeypatch.setattr(auth_router, "emit_system_event", lambda **kwargs: events.append(kwargs["event_type"]))

    register_response = auth_router.register(RegisterRequest(email=user.email, username=user.username, password="Passw0rd!123"), db=MagicMock())
    login_response = auth_router.login(LoginRequest(email=user.email, password="Passw0rd!123"), db=MagicMock())

    assert register_response["access_token"] == "token"
    assert login_response["access_token"] == "token"
    assert events == ["auth.register.completed", "auth.login.completed"]


def test_health_success_routes_emit_system_events(monkeypatch):
    health_router = importlib.import_module("routes.health_router")

    events = []

    monkeypatch.setattr(health_router, "SessionLocal", lambda: _FakeDB())
    monkeypatch.setattr(health_router, "emit_system_event", lambda **kwargs: events.append(kwargs["event_type"]))

    assert health_router.liveness()["status"] == "ok"
    assert health_router.liveness_legacy_alias()["status"] == "ok"
    assert events == ["health.liveness.completed", "health.liveness.completed"]
