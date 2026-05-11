"""Task-owned adapters for platform execution views."""

from __future__ import annotations

from typing import Optional


def task_to_execution_unit(task) -> dict:
    return {
        "id": None,
        "type": "task",
        "status": _map_task_status(getattr(task, "status", "pending")),
        "user_id": str(task.user_id) if getattr(task, "user_id", None) else None,
        "source_type": "task",
        "source_id": str(task.id),
        "parent_id": None,
        "flow_run_id": None,
        "correlation_id": None,
        "memory_context_ids": [],
        "output_memory_ids": [],
        "extra": {
            "task_name": getattr(task, "name", None),
            "category": getattr(task, "category", None),
            "priority": getattr(task, "priority", None),
        },
        "created_at": _iso(getattr(task, "created_at", None)),
        "updated_at": _iso(getattr(task, "updated_at", None)),
        "completed_at": _iso(getattr(task, "completed_at", None)),
    }


def register(register_execution_adapter) -> None:
    register_execution_adapter("task", task_to_execution_unit)


def _iso(dt) -> Optional[str]:
    if dt is None:
        return None
    if hasattr(dt, "isoformat"):
        return dt.isoformat()
    return str(dt)


def _map_task_status(status: str) -> str:
    return {
        "pending": "pending",
        "in_progress": "executing",
        "paused": "waiting",
        "completed": "completed",
    }.get(status, "pending")
