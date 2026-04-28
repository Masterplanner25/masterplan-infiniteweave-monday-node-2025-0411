from __future__ import annotations

from datetime import date, datetime
from typing import Any
import uuid

from sqlalchemy.orm import Session

from AINDY.platform_layer.user_ids import require_user_id


def serialize_scalar(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


def task_to_dict(task) -> dict[str, Any]:
    return {
        key: serialize_scalar(value)
        for key, value in task.__dict__.items()
        if not key.startswith("_")
    }


def count_tasks(
    db: Session,
    *,
    user_id: str | uuid.UUID,
    status: str | None = None,
    masterplan_id: int | None = None,
) -> int:
    from apps.tasks.models import Task

    query = db.query(Task).filter(Task.user_id == require_user_id(user_id))
    if status is not None:
        query = query.filter(Task.status == status)
    if masterplan_id is not None:
        query = query.filter(Task.masterplan_id == masterplan_id)
    return int(query.count())


def count_tasks_completed_since(
    db: Session,
    *,
    user_id: str | uuid.UUID,
    since: datetime,
) -> int:
    from apps.tasks.models import Task

    return int(
        db.query(Task)
        .filter(
            Task.user_id == require_user_id(user_id),
            Task.status == "completed",
            Task.end_time >= since,
        )
        .count()
    )


def list_tasks_for_masterplan(
    db: Session,
    *,
    user_id: str | uuid.UUID,
    masterplan_id: int,
) -> list:
    from apps.tasks.models import Task

    return (
        db.query(Task)
        .filter(
            Task.user_id == require_user_id(user_id),
            Task.masterplan_id == masterplan_id,
        )
        .order_by(Task.id.asc())
        .all()
    )


def delete_tasks_by_ids(
    db: Session,
    *,
    user_id: str | uuid.UUID,
    task_ids: list[int],
) -> int:
    from apps.tasks.models import Task

    if not task_ids:
        return 0
    rows = (
        db.query(Task)
        .filter(
            Task.user_id == require_user_id(user_id),
            Task.id.in_(task_ids),
        )
        .all()
    )
    for row in rows:
        db.delete(row)
    db.flush()
    return len(rows)
