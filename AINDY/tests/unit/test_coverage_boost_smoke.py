from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
import uuid

import pytest


def test_execution_service_run_execution_success(monkeypatch):
    from core.execution_service import ExecutionContext, run_execution

    captured = {}

    def fake_execute_with_pipeline_sync(**kwargs):
        captured["route_name"] = kwargs["route_name"]
        result = kwargs["handler"](None)
        return {"result": result}

    monkeypatch.setattr(
        "core.execution_service.execute_with_pipeline_sync",
        fake_execute_with_pipeline_sync,
    )
    monkeypatch.setattr(
        "core.execution_service.adapt_pipeline_result",
        lambda pipeline_result, next_action=None: {
            "pipeline_result": pipeline_result,
            "next_action": next_action,
        },
    )

    payloads = []
    context = ExecutionContext(
        db=MagicMock(),
        user_id="user-1",
        source="test",
        operation="coverage.execution",
        trace_id="trace-1",
        start_payload={"x": 1},
    )

    result = run_execution(
        context,
        lambda: {"ok": True},
        completed_payload_builder=lambda value: payloads.append(value),
        next_action_builder=lambda value: "done" if value["ok"] else "retry",
    )

    assert captured["route_name"] == "coverage.execution"
    assert payloads == [{"ok": True}]
    assert result["pipeline_result"]["result"] == {"ok": True}
    assert result["next_action"] == "done"


def test_execution_service_run_execution_maps_exception(monkeypatch):
    from fastapi import HTTPException

    from core.execution_service import ExecutionContext, ExecutionErrorConfig, run_execution

    def fake_execute_with_pipeline_sync(**kwargs):
        return kwargs["handler"](None)

    monkeypatch.setattr(
        "core.execution_service.execute_with_pipeline_sync",
        fake_execute_with_pipeline_sync,
    )
    monkeypatch.setattr(
        "core.execution_service.adapt_pipeline_result",
        lambda pipeline_result, next_action=None: pipeline_result,
    )

    context = ExecutionContext(
        db=MagicMock(),
        user_id=None,
        source="test",
        operation="coverage.error",
    )

    with pytest.raises(HTTPException) as exc_info:
        run_execution(
            context,
            lambda: (_ for _ in ()).throw(ValueError("boom")),
            handled_exceptions={
                ValueError: ExecutionErrorConfig(status_code=422, message="mapped")
            },
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["message"] == "mapped"


def test_router_guard_scan_and_validate(tmp_path):
    from core.router_guard import RouterBoundaryViolation, _scan_file, validate_router_boundary

    bad_router = tmp_path / "bad_router.py"
    bad_router.write_text(
        "from domain.task_services import create_task\n",
        encoding="utf-8",
    )
    violations = _scan_file(bad_router)
    assert violations
    assert violations[0].module == "domain.task_services"

    with pytest.raises(RouterBoundaryViolation):
        validate_router_boundary(tmp_path)

    clean_dir = tmp_path / "clean"
    clean_dir.mkdir()
    (clean_dir / "good_router.py").write_text(
        "from services.auth_service import get_current_user\n",
        encoding="utf-8",
    )
    validate_router_boundary(clean_dir)


def test_masterplan_execution_service_sync_skip_and_status():
    from domain.masterplan_execution_service import (
        get_masterplan_execution_status,
        sync_masterplan_tasks,
    )

    owner_id = uuid.uuid4()
    task = SimpleNamespace(
        id=1,
        status="completed",
        name="Task 1",
        priority="high",
        parent_task_id=None,
        depends_on=[],
        automation_type=None,
        automation_config=None,
    )
    log = SimpleNamespace(
        id=10,
        user_id=owner_id,
        status="failed",
        task_name="Task 1",
        error_message="broken",
        created_at=datetime.utcnow(),
        payload={"masterplan_id": 7, "task_id": 1},
    )

    task_query = MagicMock()
    task_query.filter.return_value = task_query
    task_query.order_by.return_value = task_query
    task_query.all.return_value = [task]
    task_query.count.return_value = 1

    log_query = MagicMock()
    log_query.filter.return_value = log_query
    log_query.order_by.return_value = log_query
    log_query.limit.return_value = log_query
    log_query.all.return_value = [log]

    db = MagicMock()
    db.query.side_effect = [task_query, task_query, log_query]

    masterplan = SimpleNamespace(id=7, structure_json={})
    sync_result = sync_masterplan_tasks(db=db, masterplan=masterplan, user_id=owner_id)
    status_result = get_masterplan_execution_status(db=db, masterplan_id=7, user_id=owner_id)

    assert sync_result["skipped"] is True
    assert sync_result["generated"] == 0
    assert status_result["tasks"]["completed"] == 1
    assert status_result["automations"]["failed"] == 1


def test_masterplan_execution_service_replace_protects_completed_tasks():
    from domain.masterplan_execution_service import sync_masterplan_tasks

    completed_task = SimpleNamespace(id=1, status="completed")
    query = MagicMock()
    query.filter.return_value = query
    query.order_by.return_value = query
    query.all.return_value = [completed_task]

    db = MagicMock()
    db.query.return_value = query
    masterplan = SimpleNamespace(id=5, structure_json={})

    with pytest.raises(ValueError, match="masterplan_tasks_completed_cannot_replace"):
        sync_masterplan_tasks(
            db=db,
            masterplan=masterplan,
            user_id=uuid.uuid4(),
            replace_existing=True,
        )


def test_masterplan_execution_service_helper_paths(monkeypatch):
    from domain import masterplan_execution_service as service

    assert service._extract_root_items({"phases": ["A"]}) == ["A"]
    assert service._extract_root_items(["bad"]) == []
    assert service._extract_children({"steps": ["B"]}) == ["B"]
    assert service._extract_children("bad") == []
    assert service._task_name_from_item({"title": " Plan "}, "fallback") == "Plan"
    assert service._task_name_from_item("  ", "fallback") == "fallback"
    assert service._category_from_item({"category": "ops"}, "masterplan") == "ops"
    assert service._priority_from_item({"priority": "high"}) == "high"
    assert service._priority_from_item({}) == "medium"
    assert service._automation_from_item(
        {"automation": {"type": "email", "template": "welcome"}}
    ) == ("email", {"type": "email", "template": "welcome"})
    assert service._automation_from_item(
        {"automation_type": "webhook", "automation_config": {"url": "https://example.com"}}
    ) == ("webhook", {"url": "https://example.com"})
    assert service._automation_from_item("bad") == (None, None)

    created = []

    def fake_create_task(**kwargs):
        task_id = len(created) + 1
        created.append(kwargs)
        return SimpleNamespace(id=task_id)

    monkeypatch.setattr(service, "create_task", fake_create_task)

    branch = service._create_task_branch(
        db=MagicMock(),
        owner_user_id=uuid.uuid4(),
        masterplan_id=42,
        item={
            "name": "Root",
            "category": "strategy",
            "priority": "high",
            "automation_type": "webhook",
            "automation_config": {"endpoint": "/x"},
            "steps": [{"name": "Child 1"}, {"name": "Child 2"}],
        },
        fallback_name="Fallback",
        parent_task_id=None,
        sibling_dependency_id=99,
    )

    assert branch == {"root_task_id": 1, "task_ids": [1, 2, 3]}
    assert created[0]["dependencies"] == [{"task_id": 99, "dependency_type": "hard"}]
    assert created[1]["parent_task_id"] == 1
    assert created[2]["dependencies"] == [{"task_id": 2, "dependency_type": "hard"}]


def test_projection_service_smoke():
    from analytics.projection_service import evaluate_phase, project_completion

    masterplan = SimpleNamespace(target_date=datetime.utcnow() + timedelta(days=30))
    projection = project_completion(masterplan, [50, 100, 150])

    plan = SimpleNamespace(
        start_date=datetime.utcnow() - timedelta(days=30),
        duration_years=1,
        total_wcu=10,
        wcu_target=5,
        gross_revenue=1000,
        revenue_target=500,
        books_published=2,
        books_required=1,
        platform_required=False,
        platform_live=False,
        studio_required=False,
        studio_ready=False,
        active_playbooks=2,
        playbooks_required=1,
    )

    assert set(projection) == {"conservative_eta", "aggressive_eta", "optimal_eta"}
    assert evaluate_phase(plan) == 2


def test_worker_schema_helpers_and_main(monkeypatch):
    import worker

    session = MagicMock()
    session.bind = object()
    monkeypatch.setattr(worker, "SessionLocal", lambda: session)

    inspector = MagicMock()
    inspector.has_table.return_value = True
    monkeypatch.setattr(worker, "inspect", lambda bind: inspector)
    assert worker._background_schema_ready() is True
    session.close.assert_called_once()

    start_calls = []
    stop_calls = []
    monkeypatch.setattr(worker.signal, "signal", lambda *args: None)
    monkeypatch.setattr(worker, "_wait_for_background_schema", lambda timeout_seconds=60: True)
    monkeypatch.setattr(
        worker.task_services,
        "start_background_tasks",
        lambda enable, log: start_calls.append(enable) or True,
    )
    monkeypatch.setattr(worker.scheduler_service, "start", lambda: start_calls.append("scheduler"))
    monkeypatch.setattr(worker.scheduler_service, "stop", lambda: stop_calls.append("scheduler"))
    monkeypatch.setattr(
        worker.task_services,
        "stop_background_tasks",
        lambda log: stop_calls.append("tasks"),
    )

    worker._RUNNING = True

    def fake_sleep(_seconds):
        worker._RUNNING = False

    monkeypatch.setattr(worker.time, "sleep", fake_sleep)
    worker.main()

    assert start_calls == [True, "scheduler"]
    assert stop_calls == ["scheduler", "tasks"]


def test_system_event_service_emit_smoke(monkeypatch):
    from core.system_event_service import emit_system_event

    event_id = uuid.uuid4()
    monkeypatch.setattr("core.system_event_service._persist_system_event", lambda **kwargs: event_id)
    monkeypatch.setattr("core.system_event_service._detect_behavioral_feedback_signals", lambda **kwargs: None)
    monkeypatch.setattr("core.system_event_service.get_trace_id", lambda: "trace-1")
    monkeypatch.setattr("core.system_event_service.get_parent_event_id", lambda: None)
    monkeypatch.setattr("core.system_event_service.is_pipeline_active", lambda: True)
    monkeypatch.setattr("core.system_event_service.capture_system_event_as_memory", lambda db, event: None, raising=False)

    fake_dispatch = []
    monkeypatch.setattr(
        "platform_layer.event_service.dispatch_webhooks_async",
        lambda **kwargs: fake_dispatch.append(kwargs),
    )

    fake_event = SimpleNamespace(id=event_id)
    query = MagicMock()
    query.filter.return_value = query
    query.first.return_value = fake_event
    db = MagicMock()
    db.query.return_value = query

    result = emit_system_event(db=db, event_type="custom.event", user_id="user-1", payload={"x": 1})

    assert result == event_id
    assert fake_dispatch[0]["event_type"] == "custom.event"


def test_scheduler_service_lifecycle_and_registration(monkeypatch):
    from platform_layer import scheduler_service

    class FakeScheduler:
        def __init__(self, job_defaults=None):
            self.job_defaults = job_defaults or {}
            self.running = False
            self.jobs = []

        def add_job(self, func, trigger=None, id=None, name=None, replace_existing=False, **kwargs):
            self.jobs.append(
                {
                    "func": func,
                    "trigger": trigger,
                    "id": id,
                    "name": name,
                    "replace_existing": replace_existing,
                }
            )

        def start(self):
            self.running = True

        def shutdown(self, wait=True):
            self.running = False

    restore_calls = []

    monkeypatch.setattr(scheduler_service, "_scheduler", None)
    monkeypatch.setattr(scheduler_service, "BackgroundScheduler", FakeScheduler)
    monkeypatch.setattr(
        scheduler_service,
        "_register_system_jobs",
        lambda sched: sched.add_job(lambda: None, id="job-1", name="job-1"),
    )

    assert scheduler_service.get_scheduler.__name__ == "get_scheduler"
    with pytest.raises(RuntimeError):
        scheduler_service.get_scheduler()

    scheduler_service.start()
    scheduler = scheduler_service.get_scheduler()
    assert scheduler.running is True
    assert scheduler.jobs[0]["id"] == "job-1"

    scheduler_service.stop()
    assert scheduler_service._scheduler is None


def test_scheduler_service_run_task_now_and_replay(monkeypatch):
    from platform_layer import scheduler_service
    import db.database as database
    import db.models.automation_log as automation_log_module

    class FakeAutomationLog:
        id = object()

        def __init__(self, **kwargs):
            self.id = kwargs.pop("id", "log-1")
            self.attempt_count = kwargs.pop("attempt_count", 0)
            self.error_message = kwargs.pop("error_message", None)
            self.started_at = kwargs.pop("started_at", None)
            self.completed_at = kwargs.pop("completed_at", None)
            for key, value in kwargs.items():
                setattr(self, key, value)

    class FakeSession:
        def __init__(self, existing_log=None):
            self.log = existing_log
            self.added = []
            self.commits = 0
            self.closed = False

        def add(self, log):
            self.log = log
            self.added.append(log)

        def commit(self):
            self.commits += 1

        def close(self):
            self.closed = True

        def query(self, model):
            return self

        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return self.log

    class FakeScheduler:
        def __init__(self):
            self.jobs = []
            self.running = True

        def add_job(self, func, args=None, id=None, name=None, replace_existing=False, **kwargs):
            self.jobs.append(
                {
                    "func": func,
                    "args": args or [],
                    "id": id,
                    "name": name,
                    "replace_existing": replace_existing,
                }
            )

    fake_scheduler = FakeScheduler()
    monkeypatch.setattr(scheduler_service, "_scheduler", fake_scheduler)
    monkeypatch.setattr(automation_log_module, "AutomationLog", FakeAutomationLog)

    run_session = FakeSession()
    monkeypatch.setattr(database, "SessionLocal", lambda: run_session)
    log_id = scheduler_service.run_task_now(
        lambda payload: payload,
        "coverage.task",
        payload={"x": 1},
        user_id="user-1",
    )

    assert log_id == "log-1"
    assert run_session.added[0].status == "pending"
    assert fake_scheduler.jobs[-1]["id"] == "task_log-1"

    replay_log = FakeAutomationLog(
        id="log-2",
        task_name="coverage.task",
        payload={"y": 2},
        status="failed",
        max_attempts=3,
        user_id="user-1",
    )
    replay_session = FakeSession(existing_log=replay_log)
    monkeypatch.setattr(database, "SessionLocal", lambda: replay_session)
    scheduler_service._TASK_REGISTRY["coverage.task"] = lambda payload: payload

    assert scheduler_service.replay_task("log-2") is True
    assert replay_log.status == "pending"
    assert fake_scheduler.jobs[-1]["id"] == "replay_log-2"
    assert fake_scheduler.jobs[-1]["args"][0] == "log-2"


def test_nodus_embedding_shim_import_contract():
    from nodus.runtime.embedding import NodusRuntime

    assert NodusRuntime is not None
    assert getattr(NodusRuntime, "__name__", "") == "NodusRuntime"
