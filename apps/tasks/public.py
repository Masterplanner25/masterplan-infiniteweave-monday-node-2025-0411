"""Public contract for the tasks app."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, TypedDict

from sqlalchemy.orm import Session

from apps.tasks.models import Task
from apps.tasks.services.task_service import (
    check_reminders,
    complete_task,
    create_task,
    get_task_by_id as _get_task_by_id,
    handle_recurrence,
    orchestrate_task_completion,
    pause_task,
    queue_task_automation as _queue_task_automation,
    start_background_tasks,
    start_task,
    stop_background_tasks,
)

PUBLIC_API_VERSION = "1.0"


class TaskAutomationDispatchResult(TypedDict, total=False):
    job_id: str
    status: str
    queue: str
    message: str
    trace_id: str
    execution_unit_id: str


def get_task_by_id(
    db: Session,
    task_id: int,
    user_id: str | uuid.UUID | None,
) -> Task | None:
    """Load one task for a user by primary key."""
    return _get_task_by_id(db, task_id, user_id)


def queue_task_automation(
    db: Session,
    task: Task,
    user_id: str | uuid.UUID | None,
    *,
    reason: str,
) -> TaskAutomationDispatchResult | None:
    """Dispatch automation for a task when automation metadata is present."""
    return _queue_task_automation(db, task, user_id, reason=reason)


__all__ = [
    "get_task_by_id",
    "queue_task_automation",
]
