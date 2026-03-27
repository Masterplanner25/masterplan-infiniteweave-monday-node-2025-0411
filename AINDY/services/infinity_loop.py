import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import case

logger = logging.getLogger(__name__)
from services.observability_events import emit_observability_event
from services.system_event_service import emit_error_event
from utils.trace_context import get_current_trace_id

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
        "trace_id": getattr(adjustment, "trace_id", None),
        "decision_type": adjustment.decision_type,
        "applied_at": adjustment.applied_at.isoformat() if adjustment.applied_at else None,
        "adjustment_payload": adjustment.adjustment_payload,
    }


def _get_recent_feedback_context(user_id: str, db, limit: int = 5) -> dict:
    try:
        from db.models.infinity_loop import UserFeedback

        rows = (
            db.query(UserFeedback)
            .filter(UserFeedback.user_id == user_id)
            .order_by(UserFeedback.created_at.desc())
            .limit(limit)
            .all()
        )
        positives = sum(1 for row in rows if getattr(row, "feedback_value", 0) > 0)
        negatives = sum(1 for row in rows if getattr(row, "feedback_value", 0) < 0)
        return {
            "count": len(rows),
            "positive": positives,
            "negative": negatives,
            "latest_feedback_text": next(
                (
                    getattr(row, "feedback_text", None)
                    for row in rows
                    if getattr(row, "feedback_text", None)
                ),
                None,
            ),
        }
    except Exception as exc:
        logger.warning("[InfinityLoop] feedback context lookup failed for %s: %s", user_id, exc)
        return {"count": 0, "positive": 0, "negative": 0, "latest_feedback_text": None}


def _get_top_incomplete_task(user_id: str, db) -> dict | None:
    from db.models.task import Task

    try:
        user_uuid = uuid.UUID(str(user_id))
    except (TypeError, ValueError):
        return None

    priority_rank = case(
        (Task.priority == "high", 3),
        (Task.priority == "medium", 2),
        else_=1,
    )
    task = (
        db.query(Task)
        .filter(
            Task.user_id == user_uuid,
            Task.status.in_(["pending", "in_progress", "paused"]),
        )
        .order_by(priority_rank.desc(), Task.due_date.asc().nulls_last(), Task.id.asc())
        .first()
    )
    if not task:
        return None
    return {
        "task_id": task.id,
        "name": task.name,
        "priority": task.priority,
        "status": task.status,
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


def _decide(score_snapshot: dict | None, feedback_context: dict | None = None) -> tuple[str, dict]:
    feedback_context = feedback_context or {}
    if feedback_context.get("negative", 0) > feedback_context.get("positive", 0):
        suggestions = _build_focus_suggestions(score_snapshot or {})
        return "review_plan", {
            "reason": "recent_negative_feedback",
            "suggestions": suggestions,
            "feedback_context": feedback_context,
            "suggested_goal": suggestions[0]["suggested_goal"],
            "next_action": {
                "type": "review_plan",
                "title": "Review current plan and recent feedback",
                "suggested_goal": suggestions[0]["suggested_goal"],
            },
        }

    if not score_snapshot:
        suggestions = _build_focus_suggestions({})
        return "review_plan", {
            "reason": "insufficient_data",
            "suggestions": suggestions,
            "suggested_goal": suggestions[0]["suggested_goal"],
            "next_action": {
                "type": "review_plan",
                "title": "Review current plan due to insufficient score data",
                "suggested_goal": suggestions[0]["suggested_goal"],
            },
        }

    try:
        execution_speed = float(score_snapshot.get("execution_speed", 50.0) or 50.0)
        decision_efficiency = float(score_snapshot.get("decision_efficiency", 50.0) or 50.0)
        focus_quality = float(score_snapshot.get("focus_quality", 50.0) or 50.0)
        ai_boost = float(score_snapshot.get("ai_productivity_boost", 50.0) or 50.0)
    except (TypeError, ValueError):
        suggestions = _build_focus_suggestions({})
        return "review_plan", {
            "reason": "invalid_snapshot",
            "suggestions": suggestions,
            "suggested_goal": suggestions[0]["suggested_goal"],
            "next_action": {
                "type": "review_plan",
                "title": "Review current plan due to invalid score snapshot",
                "suggested_goal": suggestions[0]["suggested_goal"],
            },
        }

    if execution_speed < 40 or decision_efficiency < 40:
        return "reprioritize_tasks", {
            "reason": "execution_or_decision_below_threshold",
            "thresholds": {
                "execution_speed": execution_speed,
                "decision_efficiency": decision_efficiency,
            },
            "next_action": {
                "type": "reprioritize_tasks",
                "title": "Reprioritize current tasks around execution bottlenecks",
            },
        }
    if focus_quality < 40:
        suggestions = _build_focus_suggestions(score_snapshot)
        return "review_plan", {
            "reason": "focus_below_threshold",
            "suggestions": suggestions,
            "suggested_goal": suggestions[0]["suggested_goal"],
            "next_action": {
                "type": "review_plan",
                "title": "Review plan and refresh context before continuing",
                "suggested_goal": suggestions[0]["suggested_goal"],
            },
        }
    if ai_boost < 40:
        suggestions = _build_ai_suggestions(score_snapshot)
        return "review_plan", {
            "reason": "ai_productivity_below_threshold",
            "suggestions": suggestions,
            "suggested_goal": suggestions[0]["suggested_goal"],
            "next_action": {
                "type": "review_plan",
                "title": "Review plan and use ARM guidance before continuing",
                "suggested_goal": suggestions[0]["suggested_goal"],
            },
        }
    return "continue_highest_priority_task", {
        "reason": "kpis_stable",
        "next_action": {
            "type": "continue_highest_priority_task",
            "title": "Continue the highest-priority in-progress task",
        },
    }


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


def run_loop(
    user_id: str,
    trigger_event: str,
    db,
    score_snapshot: dict | None = None,
    feedback_context: dict | None = None,
):
    from db.models.infinity_loop import LoopAdjustment

    try:
        normalized_trigger = _normalize_trigger_event(trigger_event)
        if score_snapshot is None:
            from services.infinity_service import get_user_kpi_snapshot

            score_snapshot = get_user_kpi_snapshot(user_id=user_id, db=db)
        feedback_context = feedback_context or _get_recent_feedback_context(user_id=user_id, db=db)
        decision_type, payload = _decide(score_snapshot, feedback_context=feedback_context)
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

        if decision_type == "reprioritize_tasks":
            reprioritized = _reprioritize_tasks(user_id=user_id, db=db)
            if reprioritized.get("task_ids"):
                payload.update(reprioritized)
                payload["next_action"] = {
                    "type": "reprioritize_tasks",
                    "title": "Continue after reprioritizing the current task queue",
                    "task_ids": reprioritized["task_ids"],
                }
            else:
                decision_type = "create_new_task"
                payload = {
                    "reason": reprioritized.get("reason", "no_incomplete_tasks"),
                    "suggested_goal": "Create one concrete next task to rebuild momentum",
                    "next_action": {
                        "type": "create_new_task",
                        "title": "Create one concrete next task",
                        "suggested_goal": "Create one concrete next task to rebuild momentum",
                    },
                }
        elif decision_type == "continue_highest_priority_task":
            top_task = _get_top_incomplete_task(user_id=user_id, db=db)
            if top_task:
                payload["task"] = top_task
                payload["next_action"] = {
                    "type": "continue_highest_priority_task",
                    "title": f"Continue task: {top_task['name']}",
                    "task_id": top_task["task_id"],
                    "task_name": top_task["name"],
                }
            else:
                decision_type = "create_new_task"
                payload = {
                    "reason": "no_incomplete_tasks",
                    "suggested_goal": "Create the next highest-value task for today",
                    "next_action": {
                        "type": "create_new_task",
                        "title": "Create the next highest-value task",
                        "suggested_goal": "Create the next highest-value task for today",
                    },
                }

        if not payload.get("next_action"):
            raise RuntimeError("Infinity loop invariant violated: next_action is required")

        adjustment = LoopAdjustment(
            user_id=user_id,
            trace_id=get_current_trace_id(),
            trigger_event=normalized_trigger,
            score_snapshot=score_snapshot,
            decision_type=decision_type,
            adjustment_payload={**payload, "feedback_context": feedback_context},
            applied_at=now,
        )
        db.add(adjustment)
        db.commit()
        db.refresh(adjustment)
        return adjustment
    except Exception as exc:
        logger.warning("[InfinityLoop] run_loop failed for %s: %s", user_id, exc)
        try:
            emit_error_event(
                db=db,
                error_type="loop",
                message=str(exc),
                user_id=user_id,
                trace_id=get_current_trace_id(),
                payload={"trigger_event": trigger_event},
                required=True,
            )
        except Exception:
            logger.exception("[InfinityLoop] failed to emit required error event for %s", user_id)
        try:
            db.rollback()
        except Exception as rollback_exc:
            emit_observability_event(
                logger,
                event="infinity_loop_rollback_failed",
                user_id=user_id,
                error=str(rollback_exc),
            )
        return None
