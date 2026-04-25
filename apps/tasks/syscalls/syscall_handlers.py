"""Task domain syscall handlers."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from AINDY.kernel.syscall_registry import SyscallContext, register_syscall
from AINDY.platform_layer.user_ids import require_user_id

logger = logging.getLogger(__name__)


def _serialize_task(task) -> dict:
    return {
        "id": str(task.id) if getattr(task, "id", None) is not None else None,
        "name": getattr(task, "name", None),
        "status": getattr(task, "status", None),
        "priority": getattr(task, "priority", None),
        "masterplan_id": getattr(task, "masterplan_id", None),
        "automation_type": getattr(task, "automation_type", None),
        "automation_config": getattr(task, "automation_config", None),
        "end_time": (
            task.end_time.isoformat()
            if getattr(task, "end_time", None) is not None
            else None
        ),
    }


def _task_name(payload: dict, syscall_name: str) -> str:
    name = payload.get("task_name") or payload.get("name")
    if not name:
        raise ValueError(f"{syscall_name} requires 'task_name' or 'name'")
    return name


def _session_from_context(ctx: SyscallContext):
    from AINDY.db.database import SessionLocal

    external_db = ctx.metadata.get("_db")
    if external_db is not None:
        return external_db, False
    return SessionLocal(), True


def _context_user_id(ctx: SyscallContext):
    user_id = require_user_id(ctx.user_id)
    logger.debug("[task_syscall] using user_id=%s", user_id)
    return user_id


def _handle_task_create(payload: dict, ctx: SyscallContext) -> dict:
    from apps.tasks.services.task_service import create_task

    name = _task_name(payload, "sys.v1.task.create")
    user_id = _context_user_id(ctx)
    db, owns_session = _session_from_context(ctx)
    try:
        task = create_task(
            db=db,
            name=name,
            category=payload.get("category"),
            priority=payload.get("priority"),
            due_date=payload.get("due_date"),
            masterplan_id=payload.get("masterplan_id"),
            parent_task_id=payload.get("parent_task_id"),
            dependency_type=payload.get("dependency_type"),
            dependencies=payload.get("dependencies"),
            automation_type=payload.get("automation_type"),
            automation_config=payload.get("automation_config"),
            scheduled_time=payload.get("scheduled_time"),
            reminder_time=payload.get("reminder_time"),
            recurrence=payload.get("recurrence"),
            user_id=user_id,
        )
        return {
            "task_id": str(task.id) if task.id else None,
            "task_name": task.name,
            "category": task.category,
            "priority": task.priority,
            "status": getattr(task, "status", "unknown"),
            "time_spent": getattr(task, "time_spent", 0),
            "masterplan_id": getattr(task, "masterplan_id", None),
            "parent_task_id": getattr(task, "parent_task_id", None),
            "depends_on": getattr(task, "depends_on", []) or [],
            "dependency_type": getattr(task, "dependency_type", "hard"),
            "automation_type": getattr(task, "automation_type", None),
            "automation_config": getattr(task, "automation_config", None),
        }
    finally:
        if owns_session:
            db.close()


def _handle_task_complete(payload: dict, ctx: SyscallContext) -> dict:
    from apps.tasks.services.task_service import complete_task

    name = _task_name(payload, "sys.v1.task.complete")
    user_id = _context_user_id(ctx)
    db, owns_session = _session_from_context(ctx)
    try:
        return {"task_result": complete_task(db=db, name=name, user_id=user_id)}
    finally:
        if owns_session:
            db.close()


def _handle_task_complete_full(payload: dict, ctx: SyscallContext) -> dict:
    from apps.tasks.services.task_service import execute_task_completion

    name = _task_name(payload, "sys.v1.task.complete_full")
    user_id = _context_user_id(ctx)
    db, owns_session = _session_from_context(ctx)
    try:
        result = execute_task_completion(db=db, name=name, user_id=user_id)
        return result if isinstance(result, dict) else {"result": result}
    finally:
        if owns_session:
            db.close()


def _handle_task_start(payload: dict, ctx: SyscallContext) -> dict:
    from apps.tasks.services.task_service import start_task

    name = _task_name(payload, "sys.v1.task.start")
    user_id = _context_user_id(ctx)
    db, owns_session = _session_from_context(ctx)
    try:
        return {"task_start_result": {"message": start_task(db, name, user_id=user_id)}}
    finally:
        if owns_session:
            db.close()


def _handle_task_pause(payload: dict, ctx: SyscallContext) -> dict:
    from apps.tasks.services.task_service import pause_task

    name = _task_name(payload, "sys.v1.task.pause")
    user_id = _context_user_id(ctx)
    db, owns_session = _session_from_context(ctx)
    try:
        return {"task_pause_result": {"message": pause_task(db, name, user_id=user_id)}}
    finally:
        if owns_session:
            db.close()


def _handle_task_orchestrate(payload: dict, ctx: SyscallContext) -> dict:
    from apps.tasks.services.task_service import orchestrate_task_completion

    name = _task_name(payload, "sys.v1.task.orchestrate")
    user_id = _context_user_id(ctx)
    db, owns_session = _session_from_context(ctx)
    try:
        return {
            "task_orchestration": orchestrate_task_completion(
                db=db,
                name=name,
                user_id=user_id,
            )
        }
    finally:
        if owns_session:
            db.close()


def _handle_watcher_ingest(payload: dict, ctx: SyscallContext) -> dict:
    from AINDY.db.models.watcher_signal import WatcherSignal
    from AINDY.platform_layer.watcher_contract import (
        get_valid_activity_types,
        get_valid_signal_types,
        parse_signal_timestamp,
    )

    signals: list = payload.get("signals") or []
    if not isinstance(signals, list) or not signals:
        raise ValueError("sys.v1.watcher.ingest requires non-empty 'signals' list")
    user_id = _context_user_id(ctx)

    db, owns_session = _session_from_context(ctx)
    try:
        persisted = 0
        session_ended_count = 0
        batch_user_id = str(user_id)

        for idx, sig in enumerate(signals):
            signal_type = sig.get("signal_type")
            activity_type = sig.get("activity_type")
            if signal_type not in get_valid_signal_types():
                raise ValueError(f"Signal [{idx}]: unknown signal_type {signal_type!r}")
            if activity_type not in get_valid_activity_types():
                raise ValueError(f"Signal [{idx}]: unknown activity_type {activity_type!r}")

            ts = parse_signal_timestamp(sig.get("timestamp"))
            meta = sig.get("metadata") or {}
            db.add(
                WatcherSignal(
                    signal_type=signal_type,
                    session_id=sig.get("session_id"),
                    user_id=user_id,
                    app_name=sig.get("app_name"),
                    window_title=sig.get("window_title") or None,
                    activity_type=activity_type,
                    signal_timestamp=ts,
                    received_at=datetime.now(timezone.utc),
                    duration_seconds=meta.get("duration_seconds"),
                    focus_score=meta.get("focus_score"),
                    signal_metadata=meta if meta else None,
                )
            )
            if signal_type == "session_ended":
                session_ended_count += 1
            persisted += 1

        db.commit()
        return {
            "watcher_ingest_result": {
                "accepted": persisted,
                "session_ended_count": session_ended_count,
            },
            "watcher_batch_user_id": batch_user_id,
            "watcher_session_ended_count": session_ended_count,
        }
    except Exception:
        db.rollback()
        raise
    finally:
        if owns_session:
            db.close()


def _handle_task_get(payload: dict, ctx: SyscallContext) -> dict:
    from AINDY.db.database import SessionLocal
    from apps.tasks.services.task_service import get_task_by_id

    task_id = payload.get("task_id")
    if task_id is None:
        raise ValueError("sys.v1.task.get requires 'task_id'")
    user_id = _context_user_id(ctx)

    external_db = ctx.metadata.get("_db")
    owns_session = external_db is None
    db = external_db if external_db is not None else SessionLocal()
    try:
        task = get_task_by_id(db, task_id, user_id)
        if not task:
            raise ValueError("HTTP_404:Task not found")
        return {"task": _serialize_task(task)}
    finally:
        if owns_session:
            db.close()


def _handle_task_queue_automation(payload: dict, ctx: SyscallContext) -> dict:
    from AINDY.db.database import SessionLocal
    from apps.tasks.services.task_service import get_task_by_id, queue_task_automation

    task_id = payload.get("task_id")
    if task_id is None:
        raise ValueError("sys.v1.task.queue_automation requires 'task_id'")
    user_id = _context_user_id(ctx)

    external_db = ctx.metadata.get("_db")
    owns_session = external_db is None
    db = external_db if external_db is not None else SessionLocal()
    try:
        task = get_task_by_id(db, task_id, user_id)
        if not task:
            raise ValueError("HTTP_404:Task not found")

        if payload.get("automation_type") is not None:
            task.automation_type = payload.get("automation_type")
        if payload.get("automation_config") is not None:
            task.automation_config = payload.get("automation_config")

        db.commit()
        db.refresh(task)

        if not task.automation_type:
            raise ValueError("HTTP_422:task_automation_not_configured")

        dispatch = queue_task_automation(
            db=db,
            task=task,
            user_id=user_id,
            reason=payload.get("reason", "manual_trigger"),
        )
        if not dispatch:
            raise ValueError("HTTP_500:task_automation_dispatch_failed")
        return {"automation_task_trigger_result": dispatch}
    finally:
        if owns_session:
            db.close()


def _handle_task_get_user_tasks(payload: dict, ctx: SyscallContext) -> dict:
    from AINDY.db.database import SessionLocal
    from apps.tasks.models import Task
    from apps.tasks.services.task_service import _user_uuid

    owner_user_id = _user_uuid(_context_user_id(ctx))
    if owner_user_id is None:
        return {"tasks": []}

    external_db = ctx.metadata.get("_db")
    owns_session = external_db is None
    db = external_db if external_db is not None else SessionLocal()
    try:
        tasks = (
            db.query(Task)
            .filter(Task.user_id == owner_user_id)
            .all()
        )
        return {
            "tasks": [
                {
                    "status": task.status,
                    "end_time": (
                        task.end_time.isoformat()
                        if isinstance(task.end_time, datetime)
                        else None
                    ),
                }
                for task in tasks
            ]
        }
    finally:
        if owns_session:
            db.close()


def _handle_task_get_graph_context(payload: dict, ctx: SyscallContext) -> dict:
    from apps.tasks.services.task_service import get_task_graph_context

    user_id = payload.get("user_id") or _context_user_id(ctx)
    db, owns_session = _session_from_context(ctx)
    try:
        return get_task_graph_context(db=db, user_id=user_id) or {}
    finally:
        if owns_session:
            db.close()


def register_task_syscall_handlers() -> None:
    register_syscall(
        name="sys.v1.task.create",
        handler=_handle_task_create,
        capability="task.create",
        description="Create a task.",
        stable=False,
    )
    register_syscall(
        name="sys.v1.task.complete",
        handler=_handle_task_complete,
        capability="task.complete",
        description="Mark task complete.",
        stable=False,
    )
    register_syscall(
        name="sys.v1.task.complete_full",
        handler=_handle_task_complete_full,
        capability="task.complete_full",
        description="Full task completion with orchestration.",
        stable=False,
    )
    register_syscall(
        name="sys.v1.task.start",
        handler=_handle_task_start,
        capability="task.start",
        description="Start a task.",
        stable=False,
    )
    register_syscall(
        name="sys.v1.task.pause",
        handler=_handle_task_pause,
        capability="task.pause",
        description="Pause a task.",
        stable=False,
    )
    register_syscall(
        name="sys.v1.task.orchestrate",
        handler=_handle_task_orchestrate,
        capability="task.orchestrate",
        description="Post-completion task orchestration.",
        stable=False,
    )
    register_syscall(
        name="sys.v1.task.get",
        handler=_handle_task_get,
        capability="task.read",
        description="Get a task by ID for the current user.",
        input_schema={
            "required": ["task_id"],
            "properties": {
                "task_id": {"type": "integer"},
                "user_id": {"type": "string"},
            },
        },
        output_schema={
            "required": ["task"],
            "properties": {"task": {"type": "dict"}},
        },
        stable=False,
    )
    register_syscall(
        name="sys.v1.task.queue_automation",
        handler=_handle_task_queue_automation,
        capability="task.write",
        description="Update task automation settings and queue task automation.",
        input_schema={
            "required": ["task_id"],
            "properties": {
                "task_id": {"type": "integer"},
                "automation_type": {"type": "string"},
                "automation_config": {"type": "dict"},
                "reason": {"type": "string"},
                "user_id": {"type": "string"},
            },
        },
        output_schema={
            "required": ["automation_task_trigger_result"],
            "properties": {"automation_task_trigger_result": {"type": "dict"}},
        },
        stable=False,
    )
    register_syscall(
        name="sys.v1.task.get_user_tasks",
        handler=_handle_task_get_user_tasks,
        capability="task.read",
        description="Return the minimal task snapshot analytics needs for scoring.",
        input_schema={
            "properties": {
                "user_id": {"type": "string"},
            },
        },
        output_schema={
            "required": ["tasks"],
            "properties": {"tasks": {"type": "array"}},
        },
        stable=False,
    )
    register_syscall(
        name="sys.v1.tasks.get_graph_context",
        handler=_handle_task_get_graph_context,
        capability="task.read",
        description="Return the task graph context for the current user.",
        input_schema={
            "required": ["user_id"],
            "properties": {
                "user_id": {"type": "string"},
            },
        },
        output_schema={
            "properties": {
                "nodes": {"type": "dict"},
                "ready": {"type": "array"},
                "blocked": {"type": "array"},
                "critical_path": {"type": "array"},
                "critical_weight": {"type": "dict"},
            },
        },
        stable=False,
    )
    register_syscall(
        name="sys.v1.watcher.ingest",
        handler=_handle_watcher_ingest,
        capability="watcher.ingest",
        description="Persist batch of WatcherSignals.",
        stable=False,
    )
    logger.info(
        "[task_syscalls] registered task lifecycle, graph, watcher ingest, and task read automation syscalls"
    )
