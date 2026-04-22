from __future__ import annotations

from typing import Any

from sqlalchemy import case, select

from AINDY.memory.memory_scoring_service import get_relevant_memories
from AINDY.platform_layer.system_state_service import compute_current_state
from AINDY.platform_layer.user_ids import parse_user_id


def fetch_recent_memory(user_id: str, db, *, context: str = "infinity_loop") -> list[dict]:
    from apps.identity.services.identity_boot_service import get_recent_memory

    return list(get_recent_memory(user_id, db, context=context) or [])


def fetch_user_metrics(user_id: str, db) -> dict[str, Any]:
    from apps.identity.services.identity_boot_service import get_user_metrics

    return dict(get_user_metrics(user_id, db) or {})


def fetch_task_graph_context(db, user_id: str) -> dict[str, Any]:
    from apps.tasks.services.task_service import get_task_graph_context

    return dict(get_task_graph_context(db, user_id) or {})


def fetch_social_performance_signals(*, user_id: str) -> list[dict[str, Any]]:
    from apps.social.services.social_performance_service import get_social_performance_signals

    return list(get_social_performance_signals(user_id=str(user_id)) or [])


def fetch_memory_signals(*, user_id: str, trigger_event: str, db) -> list[dict[str, Any]]:
    return list(
        get_relevant_memories(
            {
                "user_id": user_id,
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


def get_loop_adjustment_model():
    from apps.automation.models import LoopAdjustment

    return LoopAdjustment


def get_user_feedback_model():
    from apps.automation.models import UserFeedback

    return UserFeedback


def get_latest_loop_adjustment(*, user_id: str, db):
    LoopAdjustment = get_loop_adjustment_model()
    owner_user_id = parse_user_id(user_id)
    if owner_user_id is None:
        return None
    return (
        db.query(LoopAdjustment)
        .filter(LoopAdjustment.user_id == owner_user_id)
        .order_by(LoopAdjustment.applied_at.desc(), LoopAdjustment.created_at.desc())
        .first()
    )


def list_strategy_accuracy_adjustments(*, user_id: str, db, limit: int = 20) -> list[Any]:
    LoopAdjustment = get_loop_adjustment_model()
    owner_user_id = parse_user_id(user_id)
    if owner_user_id is None:
        return []
    return (
        db.query(LoopAdjustment)
        .filter(
            LoopAdjustment.user_id == owner_user_id,
            LoopAdjustment.prediction_accuracy.isnot(None),
        )
        .order_by(LoopAdjustment.evaluated_at.desc(), LoopAdjustment.created_at.desc())
        .limit(limit)
        .all()
    )


def get_pending_loop_adjustment(*, user_id: str, db, managed_transactions: bool):
    LoopAdjustment = get_loop_adjustment_model()
    owner_user_id = parse_user_id(user_id)
    if owner_user_id is None:
        return None
    if managed_transactions:
        return (
            db.execute(
                select(LoopAdjustment)
                .where(
                    LoopAdjustment.user_id == owner_user_id,
                    LoopAdjustment.evaluated_at.is_(None),
                )
                .order_by(LoopAdjustment.created_at.desc())
                .with_for_update()
            )
            .scalars()
            .first()
        )
    return (
        db.query(LoopAdjustment)
        .filter(
            LoopAdjustment.user_id == owner_user_id,
            LoopAdjustment.evaluated_at.is_(None),
        )
        .order_by(LoopAdjustment.created_at.desc())
        .first()
    )


def list_recent_feedback_rows(*, user_id: str, db, limit: int = 5) -> list[Any]:
    UserFeedback = get_user_feedback_model()
    owner_user_id = parse_user_id(user_id)
    if owner_user_id is None:
        return []
    return (
        db.query(UserFeedback)
        .filter(UserFeedback.user_id == owner_user_id)
        .order_by(UserFeedback.created_at.desc())
        .limit(limit)
        .all()
    )


def fetch_next_ready_task(*, db, user_id: str) -> dict[str, Any] | None:
    from apps.tasks.services.task_service import get_next_ready_task

    return get_next_ready_task(db=db, user_id=user_id)


def list_incomplete_tasks(*, user_id: str, db, limit: int | None = None) -> list[Any]:
    from apps.tasks.models import Task

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


def create_loop_adjustment(**kwargs):
    LoopAdjustment = get_loop_adjustment_model()
    return LoopAdjustment(**kwargs)


def get_latest_loop_adjustment_for_update(*, persisted_user_id, db):
    LoopAdjustment = get_loop_adjustment_model()
    return (
        db.execute(
            select(LoopAdjustment)
            .where(LoopAdjustment.user_id == persisted_user_id)
            .order_by(LoopAdjustment.applied_at.desc(), LoopAdjustment.created_at.desc())
            .with_for_update()
        )
        .scalars()
        .first()
    )
