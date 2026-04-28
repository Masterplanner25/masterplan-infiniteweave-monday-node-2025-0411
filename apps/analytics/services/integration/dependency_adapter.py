from __future__ import annotations

from typing import Any

from sqlalchemy import case

from AINDY.memory.memory_scoring_service import get_relevant_memories
from AINDY.platform_layer.registry import get_symbol
from AINDY.platform_layer.system_state_service import compute_current_state
from AINDY.platform_layer.user_ids import parse_user_id, require_user_id

from .tasks_bridge import get_task_graph_context_via_syscall


class RecordDict(dict):
    """Dict wrapper that preserves legacy attribute-style access for analytics internals."""

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name: str, value: Any) -> None:
        self[name] = value


def _wrap_record(row: dict[str, Any] | None):
    if row is None:
        return None
    return RecordDict(row)


def _wrap_records(rows: list[dict[str, Any]] | None) -> list[RecordDict]:
    return [_wrap_record(row) for row in (rows or []) if row is not None]


def fetch_recent_memory(user_id: str, db, *, context: str = "infinity_loop") -> list[dict]:
    from apps.identity.public import get_recent_memory as _get_recent_memory

    return list(_get_recent_memory(user_id, db, context=context) or [])


def fetch_user_metrics(user_id: str, db) -> dict[str, Any]:
    from apps.identity.public import get_user_metrics as _get_user_metrics

    return dict(_get_user_metrics(user_id, db) or {})


def fetch_task_graph_context(db, user_id: str) -> dict[str, Any]:
    return dict(get_task_graph_context_via_syscall(user_id, db) or {})


def fetch_social_performance_signals(*, user_id: str) -> list[dict[str, Any]]:
    from apps.social.public import get_social_performance_signals

    return list(get_social_performance_signals(user_id=str(user_id)) or [])


def fetch_memory_signals(*, user_id: str, trigger_event: str, db) -> list[dict[str, Any]]:
    normalized_user_id = require_user_id(user_id)
    return list(
        get_relevant_memories(
            {
                "user_id": normalized_user_id,
                "trigger_event": trigger_event,
                "current_state": "infinity_loop",
                "goal": "select next_action",
                "constraints": [],
            },
            db=db,
        )
        or []
    )


def fetch_system_state(db) -> dict[str, Any]:
    return dict(compute_current_state(db) or {})


def get_latest_loop_adjustment(*, user_id: str, db):
    owner_user_id = parse_user_id(user_id)
    if owner_user_id is None:
        return None

    from apps.automation.public import get_loop_adjustments

    rows = get_loop_adjustments(owner_user_id, db, limit=1)
    return _wrap_record(rows[0] if rows else None)


def list_strategy_accuracy_adjustments(*, user_id: str, db, limit: int = 20) -> list[Any]:
    owner_user_id = parse_user_id(user_id)
    if owner_user_id is None:
        return []

    from apps.automation.public import get_loop_adjustments

    return _wrap_records(
        get_loop_adjustments(
            owner_user_id,
            db,
            limit=limit,
            with_prediction_accuracy=True,
            order_by="evaluated_desc",
        )
        or []
    )


def get_pending_loop_adjustment(*, user_id: str, db, managed_transactions: bool):
    owner_user_id = parse_user_id(user_id)
    if owner_user_id is None:
        return None

    from apps.automation.public import get_loop_adjustments

    rows = get_loop_adjustments(
        owner_user_id,
        db,
        limit=1,
        unevaluated_only=True,
        order_by="created_desc",
        for_update=managed_transactions,
    )
    return _wrap_record(rows[0] if rows else None)


def list_recent_feedback_rows(*, user_id: str, db, limit: int = 5) -> list[Any]:
    owner_user_id = parse_user_id(user_id)
    if owner_user_id is None:
        return []

    from apps.automation.public import get_user_feedback

    return _wrap_records(get_user_feedback(owner_user_id, db, limit=limit) or [])


def fetch_next_ready_task(*, db, user_id: str) -> dict[str, Any] | None:
    context = fetch_task_graph_context(db=db, user_id=user_id)
    task_id = next(iter(context.get("critical_path") or []), None)
    if task_id is None:
        return None
    node = (context.get("nodes") or {}).get(task_id) or (context.get("nodes") or {}).get(int(task_id))
    if not node:
        return None
    return {
        "task_id": task_id,
        "name": node.get("name"),
        "priority": node.get("priority"),
        "status": node.get("status"),
        "critical_weight": (context.get("critical_weight") or {}).get(task_id, 1),
    }


def list_incomplete_tasks(*, user_id: str, db, limit: int | None = None) -> list[Any]:
    Task = get_symbol("Task")
    if Task is None:
        return []

    user_uuid = parse_user_id(user_id)
    if user_uuid is None:
        return []
    priority_rank = case(
        (Task.priority == "high", 3),
        (Task.priority == "medium", 2),
        else_=1,
    )
    query = (
        db.query(Task)
        .filter(
            Task.user_id == user_uuid,
            Task.status.in_(["pending", "in_progress", "paused"]),
        )
        .order_by(priority_rank.desc(), Task.due_date.asc().nulls_last(), Task.id.asc())
    )
    if limit is not None:
        query = query.limit(limit)
    return list(query.all())


def create_loop_adjustment(*, db, **kwargs):
    from apps.automation.public import create_loop_adjustment as _create_loop_adjustment

    return _wrap_record(dict(_create_loop_adjustment(db=db, **kwargs) or {}))


def get_latest_loop_adjustment_for_update(*, persisted_user_id, db):
    from apps.automation.public import get_loop_adjustments

    rows = get_loop_adjustments(
        persisted_user_id,
        db,
        limit=1,
        for_update=True,
    )
    return _wrap_record(rows[0] if rows else None)


def update_loop_adjustment(*, adjustment_id, db, **kwargs):
    from apps.automation.public import update_loop_adjustment as _update_loop_adjustment

    return _wrap_record(_update_loop_adjustment(adjustment_id=adjustment_id, db=db, **kwargs))
