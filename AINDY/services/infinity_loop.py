import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import case

logger = logging.getLogger(__name__)

THRASH_GUARD_MINUTES = 60
TASK_REPRIORITIZATION_LIMIT = 5


def _normalize_trigger_event(trigger_event: str) -> str:
    mapping = {
        "task_completion": "task_completed",
        "arm_analysis": "arm_analyzed",
    }
    return mapping.get(trigger_event or "manual", trigger_event or "manual")


def get_latest_adjustment(user_id: str, db):
    try:
        from db.models.infinity_loop import LoopAdjustment

        return (
            db.query(LoopAdjustment)
            .filter(LoopAdjustment.user_id == user_id)
            .order_by(LoopAdjustment.applied_at.desc(), LoopAdjustment.created_at.desc())
            .first()
        )
    except Exception as exc:
        logger.warning("[InfinityLoop] get_latest_adjustment failed for %s: %s", user_id, exc)
        return None


def serialize_adjustment(adjustment) -> dict | None:
    if not adjustment:
        return None
    return {
        "id": str(adjustment.id),
        "decision_type": adjustment.decision_type,
        "applied_at": adjustment.applied_at.isoformat() if adjustment.applied_at else None,
        "adjustment_payload": adjustment.adjustment_payload,
    }


def _build_focus_suggestions(score_snapshot: dict) -> list[dict]:
    focus = float(score_snapshot.get("focus_quality", 50.0) or 50.0)
    return [
        {
            "tool": "memory.recall",
            "reason": f"Focus quality is low ({focus:.0f}/100) - recall relevant context before switching tasks.",
            "suggested_goal": "Recall recent context and notes before resuming the current workstream",
        },
        {
            "tool": "research.query",
            "reason": f"Focus quality is low ({focus:.0f}/100) - external context gathering can reduce restart friction.",
            "suggested_goal": "Research the current topic to rebuild momentum with a quick context refresh",
        },
    ]


def _build_ai_suggestions(score_snapshot: dict) -> list[dict]:
    ai_boost = float(score_snapshot.get("ai_productivity_boost", 50.0) or 50.0)
    return [
        {
            "tool": "arm.analyze",
            "reason": f"AI productivity boost is low ({ai_boost:.0f}/100) - use ARM to identify the highest-leverage next improvements.",
            "suggested_goal": "Analyze the current code or plan with ARM to identify the next highest-leverage improvement",
        }
    ]


def _decide(score_snapshot: dict | None) -> tuple[str, dict]:
    if not score_snapshot:
        return "no_op", {"reason": "insufficient_data"}

    try:
        execution_speed = float(score_snapshot.get("execution_speed", 50.0) or 50.0)
        decision_efficiency = float(score_snapshot.get("decision_efficiency", 50.0) or 50.0)
        focus_quality = float(score_snapshot.get("focus_quality", 50.0) or 50.0)
        ai_boost = float(score_snapshot.get("ai_productivity_boost", 50.0) or 50.0)
    except (TypeError, ValueError):
        return "no_op", {"reason": "invalid_snapshot"}

    if execution_speed < 40 or decision_efficiency < 40:
        return "task_reprioritization", {
            "reason": "execution_or_decision_below_threshold",
            "thresholds": {
                "execution_speed": execution_speed,
                "decision_efficiency": decision_efficiency,
            },
        }
    if focus_quality < 40:
        suggestions = _build_focus_suggestions(score_snapshot)
        return "suggestion_refresh", {
            "reason": "focus_below_threshold",
            "suggestions": suggestions,
            "suggested_goal": suggestions[0]["suggested_goal"],
        }
    if ai_boost < 40:
        suggestions = _build_ai_suggestions(score_snapshot)
        return "suggestion_refresh", {
            "reason": "ai_productivity_below_threshold",
            "suggestions": suggestions,
            "suggested_goal": suggestions[0]["suggested_goal"],
        }
    return "no_op", {"reason": "kpis_neutral"}


def _reprioritize_tasks(user_id: str, db) -> dict:
    from db.models.task import Task

    try:
        user_uuid = uuid.UUID(str(user_id))
    except (TypeError, ValueError):
        return {"reason": "invalid_user_id", "task_ids": []}

    priority_rank = case(
        (Task.priority == "high", 3),
        (Task.priority == "medium", 2),
        else_=1,
    )
    tasks = (
        db.query(Task)
        .filter(
            Task.user_id == user_uuid,
            Task.status.in_(["pending", "in_progress", "paused"]),
        )
        .order_by(priority_rank.desc(), Task.due_date.asc().nulls_last(), Task.id.asc())
        .limit(TASK_REPRIORITIZATION_LIMIT)
        .all()
    )

    if not tasks:
        return {"reason": "no_incomplete_tasks", "task_ids": []}

    affected = []
    for task in tasks:
        previous_priority = task.priority
        task.priority = "high"
        affected.append(
            {
                "task_id": task.id,
                "name": task.name,
                "previous_priority": previous_priority,
                "new_priority": task.priority,
            }
        )
    db.commit()
    return {"task_ids": [item["task_id"] for item in affected], "tasks": affected}


def run_loop(user_id: str, trigger_event: str, db):
    from db.models.infinity_loop import LoopAdjustment
    from services.infinity_service import get_user_kpi_snapshot

    try:
        normalized_trigger = _normalize_trigger_event(trigger_event)
        score_snapshot = get_user_kpi_snapshot(user_id=user_id, db=db)
        decision_type, payload = _decide(score_snapshot)
        now = datetime.now(timezone.utc)

        last_adjustment = get_latest_adjustment(user_id=user_id, db=db)
        if (
            last_adjustment
            and last_adjustment.decision_type == decision_type
            and last_adjustment.applied_at
        ):
            applied_at = last_adjustment.applied_at
            if applied_at.tzinfo is None:
                applied_at = applied_at.replace(tzinfo=timezone.utc)
            if now - applied_at < timedelta(minutes=THRASH_GUARD_MINUTES):
                return last_adjustment

        if decision_type == "task_reprioritization":
            payload.update(_reprioritize_tasks(user_id=user_id, db=db))

        adjustment = LoopAdjustment(
            user_id=user_id,
            trigger_event=normalized_trigger,
            score_snapshot=score_snapshot,
            decision_type=decision_type,
            adjustment_payload=payload,
            applied_at=now,
        )
        db.add(adjustment)
        db.commit()
        db.refresh(adjustment)
        return adjustment
    except Exception as exc:
        logger.warning("[InfinityLoop] run_loop failed for %s: %s", user_id, exc)
        try:
            db.rollback()
        except Exception:
            pass
        return None
