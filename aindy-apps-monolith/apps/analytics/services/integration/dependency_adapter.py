from __future__ import annotations

from typing import Any

from sqlalchemy import case

from AINDY.kernel.syscall_dispatcher import get_dispatcher, make_syscall_ctx_from_tool
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


def _dispatch_syscall(name: str, payload: dict[str, Any], *, user_id: str | None, capability: str, db=None) -> dict[str, Any]:
    ctx = make_syscall_ctx_from_tool(str(user_id or ""), capabilities=[capability])
    if db is not None:
        ctx.metadata["_db"] = db
    result = get_dispatcher().dispatch(name, payload, ctx)
    if result.get("status") != "success":
        return {}
    return result.get("data") or {}


def fetch_recent_memory(user_id: str, db, *, context: str = "infinity_loop") -> list[dict]:
    from apps.identity.public import get_recent_memory as _get_recent_memory

    return list(_get_recent_memory(user_id, db, context=context) or [])


def fetch_user_metrics(user_id: str, db) -> dict[str, Any]:
    from apps.identity.public import get_user_metrics as _get_user_metrics

    return dict(_get_user_metrics(user_id, db) or {})


def fetch_task_graph_context(db, user_id: str) -> dict[str, Any]:
    return dict(get_task_graph_context_via_syscall(user_id, db) or {})


def fetch_social_performance_signals(*, user_id: str) -> list[dict[str, Any]]:
    result = _dispatch_syscall(
        "sys.v1.social.get_performance_signals",
        {"user_id": str(user_id), "limit": 3},
        user_id=str(user_id),
        capability="social.read",
    )
    return list(result.get("signals") or [])


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

    result = _dispatch_syscall(
        "sys.v1.automation.list_loop_adjustments",
        {"user_id": str(owner_user_id), "limit": 1},
        user_id=str(owner_user_id),
        capability="automation.read",
        db=db,
    )
    rows = result.get("adjustments") or []
    return _wrap_record(rows[0] if rows else None)


def list_strategy_accuracy_adjustments(*, user_id: str, db, limit: int = 20) -> list[Any]:
    owner_user_id = parse_user_id(user_id)
    if owner_user_id is None:
        return []

    result = _dispatch_syscall(
        "sys.v1.automation.list_loop_adjustments",
        {
            "user_id": str(owner_user_id),
            "limit": limit,
            "with_prediction_accuracy": True,
            "order_by": "evaluated_desc",
        },
        user_id=str(owner_user_id),
        capability="automation.read",
        db=db,
    )
    return _wrap_records(result.get("adjustments") or [])


def get_pending_loop_adjustment(*, user_id: str, db, managed_transactions: bool):
    owner_user_id = parse_user_id(user_id)
    if owner_user_id is None:
        return None

    result = _dispatch_syscall(
        "sys.v1.automation.list_loop_adjustments",
        {
            "user_id": str(owner_user_id),
            "limit": 1,
            "unevaluated_only": True,
            "order_by": "created_desc",
            "for_update": managed_transactions,
        },
        user_id=str(owner_user_id),
        capability="automation.read",
        db=db,
    )
    rows = result.get("adjustments") or []
    return _wrap_record(rows[0] if rows else None)


def list_recent_feedback_rows(*, user_id: str, db, limit: int = 5) -> list[Any]:
    owner_user_id = parse_user_id(user_id)
    if owner_user_id is None:
        return []

    result = _dispatch_syscall(
        "sys.v1.automation.list_feedback",
        {"user_id": str(owner_user_id), "limit": limit},
        user_id=str(owner_user_id),
        capability="automation.read",
        db=db,
    )
    return _wrap_records(result.get("feedback") or [])


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
    result = _dispatch_syscall(
        "sys.v1.automation.create_loop_adjustment",
        kwargs,
        user_id=str(kwargs.get("user_id") or ""),
        capability="automation.write",
        db=db,
    )
    return _wrap_record(dict(result.get("adjustment") or {}))


def get_latest_loop_adjustment_for_update(*, persisted_user_id, db):
    result = _dispatch_syscall(
        "sys.v1.automation.list_loop_adjustments",
        {
            "user_id": str(persisted_user_id),
            "limit": 1,
            "for_update": True,
        },
        user_id=str(persisted_user_id),
        capability="automation.read",
        db=db,
    )
    rows = result.get("adjustments") or []
    return _wrap_record(rows[0] if rows else None)


def update_loop_adjustment(*, adjustment_id, db, **kwargs):
    result = _dispatch_syscall(
        "sys.v1.automation.update_loop_adjustment",
        {"adjustment_id": adjustment_id, **kwargs},
        user_id=str(kwargs.get("user_id") or ""),
        capability="automation.write",
        db=db,
    )
    return _wrap_record(result.get("adjustment"))
