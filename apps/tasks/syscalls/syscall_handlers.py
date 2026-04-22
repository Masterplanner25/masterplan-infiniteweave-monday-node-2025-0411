"""Task domain syscall handlers."""
from __future__ import annotations

import logging
from datetime import datetime

from AINDY.kernel.syscall_registry import SyscallContext, register_syscall

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


def _handle_task_get(payload: dict, ctx: SyscallContext) -> dict:
    from AINDY.db.database import SessionLocal
    from apps.tasks.services.task_service import get_task_by_id

    task_id = payload.get("task_id")
    if task_id is None:
        raise ValueError("sys.v1.task.get requires 'task_id'")

    external_db = ctx.metadata.get("_db")
    owns_session = external_db is None
    db = external_db if external_db is not None else SessionLocal()
    try:
        task = get_task_by_id(db, task_id, payload.get("user_id") or ctx.user_id)
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

    external_db = ctx.metadata.get("_db")
    owns_session = external_db is None
    db = external_db if external_db is not None else SessionLocal()
    try:
        user_id = payload.get("user_id") or ctx.user_id
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

    user_id = payload.get("user_id") or ctx.user_id
    owner_user_id = _user_uuid(user_id)
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


def register_task_syscall_handlers() -> None:
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
    logger.info(
        "[task_syscalls] registered sys.v1.task.get, sys.v1.task.queue_automation, sys.v1.task.get_user_tasks"
    )
