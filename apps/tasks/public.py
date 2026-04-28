"""Public contract for the tasks app."""

from __future__ import annotations

import uuid
from typing import Any, TypedDict

from sqlalchemy.orm import Session

from apps.tasks.models import Task
from apps.tasks.services.task_service import (
    get_task_by_id as _get_task_by_id,
    queue_task_automation as _queue_task_automation,
)

PUBLIC_API_VERSION = "1.0"


class TaskAutomationDispatchResult(TypedDict, total=False):
    job_id: str
    status: str
    queue: str
    message: str
    trace_id: str
    execution_unit_id: str


def _task_to_dict(task) -> dict[str, Any]:
    from apps.tasks.services.public_surface_service import task_to_dict

    return task_to_dict(task)


def get_task_by_id(
    db: Session,
    task_id: int,
    user_id: str | uuid.UUID | None,
) -> dict[str, Any] | None:
    """Load one task for a user by primary key."""
    task = _get_task_by_id(db, task_id, user_id)
    return _task_to_dict(task) if task is not None else None


def queue_task_automation(
    db: Session,
    task: Any,
    user_id: str | uuid.UUID | None,
    *,
    reason: str,
) -> TaskAutomationDispatchResult | None:
    """Dispatch automation for a task when automation metadata is present."""
    return _queue_task_automation(db, task, user_id, reason=reason)


def update_task_status(
    db: Session,
    *,
    task_id: int,
    user_id: str | uuid.UUID,
    status: str,
) -> dict[str, Any] | None:
    """Update one task status and return the new task snapshot."""
    task = _get_task_by_id(db, task_id, user_id)
    if task is None:
        return None
    task.status = status
    db.commit()
    db.refresh(task)
    return _task_to_dict(task)


def queue_task_automation_by_id(
    db: Session,
    *,
    task_id: int,
    user_id: str | uuid.UUID,
    reason: str,
) -> TaskAutomationDispatchResult | None:
    """Dispatch automation for one task ID when the task exists and is configured."""
    task = _get_task_by_id(db, task_id, user_id)
    if task is None:
        return None
    return _queue_task_automation(db, task, user_id, reason=reason)


def count_tasks(
    db: Session,
    *,
    user_id: str | uuid.UUID,
    status: str | None = None,
    masterplan_id: int | None = None,
) -> int:
    """Count tasks for one user with optional status/masterplan filters."""
    from apps.tasks.services.public_surface_service import count_tasks as _count_tasks

    return int(_count_tasks(db, user_id=user_id, status=status, masterplan_id=masterplan_id))


def count_tasks_completed_since(
    db: Session,
    *,
    user_id: str | uuid.UUID,
    since,
) -> int:
    """Count completed tasks for one user since a timestamp."""
    from apps.tasks.services.public_surface_service import (
        count_tasks_completed_since as _count_tasks_completed_since,
    )

    return int(_count_tasks_completed_since(db, user_id=user_id, since=since))


def list_tasks_for_masterplan(
    db: Session,
    *,
    user_id: str | uuid.UUID,
    masterplan_id: int,
) -> list[dict[str, Any]]:
    """Return masterplan-linked tasks as plain dicts."""
    from apps.tasks.services.public_surface_service import (
        list_tasks_for_masterplan as _list_tasks_for_masterplan,
    )

    return [
        _task_to_dict(task)
        for task in _list_tasks_for_masterplan(
            db,
            user_id=user_id,
            masterplan_id=masterplan_id,
        )
    ]


def delete_tasks_by_ids(
    db: Session,
    *,
    user_id: str | uuid.UUID,
    task_ids: list[int],
) -> int:
    """Delete task rows by ID for one user and return the delete count."""
    from apps.tasks.services.public_surface_service import (
        delete_tasks_by_ids as _delete_tasks_by_ids,
    )

    return int(_delete_tasks_by_ids(db, user_id=user_id, task_ids=task_ids))


__all__ = [
    "get_task_by_id",
    "queue_task_automation",
    "update_task_status",
    "queue_task_automation_by_id",
    "count_tasks",
    "count_tasks_completed_since",
    "list_tasks_for_masterplan",
    "delete_tasks_by_ids",
]
