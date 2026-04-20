import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import case
from sqlalchemy import select
logger = logging.getLogger(__name__)
from AINDY.core.observability_events import emit_observability_event
from AINDY.core.system_event_service import emit_error_event
from AINDY.platform_layer.trace_context import get_current_trace_id
from AINDY.platform_layer.user_ids import parse_user_id
from apps.analytics.services.concurrency import supports_managed_transactions, transaction_scope

THRASH_GUARD_MINUTES = 60
TASK_REPRIORITIZATION_LIMIT = 5

EXPECTED_SCORE_OFFSETS = {
    "continue_highest_priority_task": 3.0,
    "create_new_task": 2.0,
    "reprioritize_tasks": 1.5,
    "review_plan": 1.0,
}


def _normalize_trigger_event(trigger_event: str) -> str:
    mapping = {
        "task_completion": "task_completed",
        "arm_analysis": "arm_analyzed",
    }
    return mapping.get(trigger_event or "manual", trigger_event or "manual")


def _normalize_user_id(user_id: str | uuid.UUID | None):
    return parse_user_id(user_id) if user_id is not None else None


def get_latest_adjustment(user_id: str, db):
    try:
        from apps.automation.models import LoopAdjustment
        owner_user_id = _normalize_user_id(user_id)
        if owner_user_id is None:
            return None

        return (
            db.query(LoopAdjustment)
            .filter(LoopAdjustment.user_id == owner_user_id)
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
        "expected_outcome": getattr(adjustment, "expected_outcome", None),
        "expected_score": getattr(adjustment, "expected_score", None),
        "actual_outcome": getattr(adjustment, "actual_outcome", None),
        "actual_score": getattr(adjustment, "actual_score", None),
        "prediction_accuracy": getattr(adjustment, "prediction_accuracy", None),
        "deviation_score": getattr(adjustment, "deviation_score", None),
        "applied_at": adjustment.applied_at.isoformat() if adjustment.applied_at else None,
        "adjustment_payload": adjustment.adjustment_payload,
    }


def _derive_expected_outcome(decision_type: str) -> str:
    if decision_type in {"continue_highest_priority_task", "create_new_task", "reprioritize_tasks"}:
        return "task_progress"
    if decision_type == "review_plan":
        return "plan_adjustment"
    return "stable_progress"


def _derive_actual_outcome(trigger_event: str) -> str:
    normalized = _normalize_trigger_event(trigger_event)
    if normalized in {"task_completed", "agent_completed"}:
        return "task_progress"
    if normalized in {"manual", "scheduled"}:
        return "stable_progress"
    return "plan_adjustment"


def _build_expectation(decision_type: str, score_snapshot: dict | None) -> tuple[str, int]:
    baseline = float((score_snapshot or {}).get("master_score", 50.0) or 50.0)
    expected_score = int(round(min(100.0, baseline + EXPECTED_SCORE_OFFSETS.get(decision_type, 1.0))))
    return _derive_expected_outcome(decision_type), expected_score


def _get_strategy_accuracy_context(user_id: str, db, limit: int = 20) -> dict[str, float]:
    try:
        from apps.automation.models import LoopAdjustment
        owner_user_id = _normalize_user_id(user_id)
        if owner_user_id is None:
            return {}

        rows = (
            db.query(LoopAdjustment)
            .filter(
                LoopAdjustment.user_id == owner_user_id,
                LoopAdjustment.prediction_accuracy.isnot(None),
            )
            .order_by(LoopAdjustment.evaluated_at.desc(), LoopAdjustment.created_at.desc())
            .limit(limit)
            .all()
        )
        grouped: dict[str, list[float]] = {}
        for row in rows:
            grouped.setdefault(row.decision_type, []).append(float(row.prediction_accuracy) / 100.0)
        return {
            decision_type: round(sum(values) / len(values), 4)
            for decision_type, values in grouped.items()
            if values
        }
    except Exception as exc:
        logger.warning("[InfinityLoop] strategy accuracy lookup failed for %s: %s", user_id, exc)
        return {}


def _apply_strategy_accuracy_weighting(user_id: str, decision_type: str, payload: dict, db) -> tuple[str, dict]:
    accuracy = _get_strategy_accuracy_context(user_id, db).get(decision_type)
    if accuracy is None:
        payload["strategy_accuracy"] = {"status": "unknown"}
        return decision_type, payload
    adjusted_payload = {
        **payload,
        "strategy_accuracy": {
            "decision_type": decision_type,
            "accuracy": accuracy,
        },
    }
    if accuracy < 0.45 and decision_type != "review_plan":
        adjusted_payload["strategy_accuracy"]["status"] = "penalized"
        adjusted_payload["next_action"] = {
            "type": "review_plan",
            "title": "Review the plan because the current strategy has been inaccurate",
            "suggested_goal": "Correct course using the most recent outcome deviations",
        }
        adjusted_payload["reason"] = f"{payload.get('reason', 'strategy')}|low_prediction_accuracy"
        return "review_plan", adjusted_payload
    if accuracy > 0.75:
        adjusted_payload["strategy_accuracy"]["status"] = "boosted"
        next_action = dict(adjusted_payload.get("next_action") or {})
        next_action["strategy_boost"] = "high_prediction_accuracy"
        adjusted_payload["next_action"] = next_action
    else:
        adjusted_payload["strategy_accuracy"]["status"] = "neutral"
    return decision_type, adjusted_payload


def evaluate_pending_adjustment(
    *,
    user_id: str,
    trigger_event: str,
    actual_score: float | None,
    db,
) -> dict | None:
    from apps.automation.models import LoopAdjustment

    try:
        owner_user_id = _normalize_user_id(user_id)
        if owner_user_id is None:
            return None
        with transaction_scope(db):
            if supports_managed_transactions(db):
                adjustment = db.execute(
                    select(LoopAdjustment)
                    .where(
                        LoopAdjustment.user_id == owner_user_id,
                        LoopAdjustment.evaluated_at.is_(None),
                    )
                    .order_by(LoopAdjustment.created_at.desc())
                    .with_for_update()
                ).scalars().first()
            else:
                adjustment = (
                    db.query(LoopAdjustment)
                    .filter(
                        LoopAdjustment.user_id == owner_user_id,
                        LoopAdjustment.evaluated_at.is_(None),
                    )
                    .order_by(LoopAdjustment.created_at.desc())
                    .first()
                )
            if not adjustment:
                return None

            actual_outcome = _derive_actual_outcome(trigger_event)
            expected_outcome = adjustment.expected_outcome or _derive_expected_outcome(adjustment.decision_type)
            expected_score = float(adjustment.expected_score or 50.0)
            actual_score_value = float(actual_score if actual_score is not None else adjustment.score_snapshot.get("master_score", 50.0))
            score_delta = round(actual_score_value - expected_score, 2)
            deviation_score = int(round(abs(score_delta)))
            outcome_match = 1.0 if actual_outcome == expected_outcome else 0.5
            score_accuracy = max(0.0, 1.0 - min(1.0, abs(score_delta) / 25.0))
            prediction_accuracy = int(round(((outcome_match * 0.4) + (score_accuracy * 0.6)) * 100))

            adjustment.actual_outcome = actual_outcome
            adjustment.actual_score = int(round(actual_score_value))
            adjustment.deviation_score = deviation_score
            adjustment.prediction_accuracy = prediction_accuracy
            adjustment.evaluated_at = datetime.now(timezone.utc)

            payload = dict(adjustment.adjustment_payload or {})
            payload["expected_vs_actual"] = {
                "expected_outcome": expected_outcome,
                "actual_outcome": actual_outcome,
                "expected_score": expected_score,
                "actual_score": actual_score_value,
                "score_delta": score_delta,
                "deviation_score": deviation_score,
                "prediction_accuracy": prediction_accuracy,
            }
            adjustment.adjustment_payload = payload
            db.add(adjustment)
            db.flush()
        return {
            "adjustment_id": str(adjustment.id),
            "prediction_accuracy": prediction_accuracy,
            "deviation_score": deviation_score,
            "score_delta": score_delta,
        }
    except Exception as exc:
        logger.warning("[InfinityLoop] evaluate_pending_adjustment failed for %s: %s", user_id, exc)
        try:
            db.rollback()
        except Exception:
            logger.exception("[InfinityLoop] rollback failed while evaluating pending adjustment")
        return None


def _get_recent_feedback_context(user_id: str, db, limit: int = 5) -> dict:
    try:
        from apps.automation.models import UserFeedback
        owner_user_id = _normalize_user_id(user_id)
        if owner_user_id is None:
            return {"count": 0, "positive": 0, "negative": 0, "latest_feedback_text": None}

        rows = (
            db.query(UserFeedback)
            .filter(UserFeedback.user_id == owner_user_id)
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
    from apps.tasks.services.task_service import get_next_ready_task

    try:
        next_ready = get_next_ready_task(db=db, user_id=user_id)
        if next_ready:
            return next_ready
    except Exception as exc:
        logger.warning("[InfinityLoop] next ready task lookup failed for %s: %s", user_id, exc)

    from apps.tasks.models import Task

    user_uuid = _normalize_user_id(user_id) or user_id

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


def _summarize_memory_signals(memory_signals: list[dict] | None) -> dict:
    signals = memory_signals or []
    failures = [signal for signal in signals if signal.get("type") == "failure"]
    successes = [signal for signal in signals if signal.get("type") == "success"]
    patterns = [signal for signal in signals if signal.get("type") == "pattern"]
    failure_weight = round(sum(float(signal.get("weighted_score", 0.0) or 0.0) for signal in failures), 4)
    success_weight = round(sum(float(signal.get("weighted_score", 0.0) or 0.0) for signal in successes), 4)
    pattern_weight = round(sum(float(signal.get("weighted_score", 0.0) or 0.0) for signal in patterns), 4)
    return {
        "failures": failures[:3],
        "successes": successes[:3],
        "patterns": patterns[:3],
        "failure_weight": failure_weight,
        "success_weight": success_weight,
        "pattern_weight": pattern_weight,
    }


def _apply_memory_weighting(
    decision_type: str,
    payload: dict,
    memory_signals: list[dict] | None = None,
) -> tuple[str, dict]:
    summary = _summarize_memory_signals(memory_signals)
    adjusted_payload = {
        **payload,
        "memory_signals": memory_signals or [],
        "memory_summary": summary,
    }

    failure_weight = summary["failure_weight"]
    success_weight = summary["success_weight"]
    pattern_weight = summary["pattern_weight"]

    if failure_weight >= max(0.75, success_weight):
        adjusted_payload["memory_adjustment"] = {
            "reason": "high_impact_failures_detected",
            "top_failures": summary["failures"],
        }
        adjusted_payload["next_action"] = {
            "type": "review_plan",
            "title": "Review current plan against recent failure patterns",
            "suggested_goal": "Avoid repeating recent high-impact failures and choose an adjusted path",
        }
        return "review_plan", adjusted_payload

    if decision_type == "continue_highest_priority_task" and success_weight > failure_weight:
        top_success = summary["successes"][0] if summary["successes"] else None
        adjusted_payload["memory_adjustment"] = {
            "reason": "successful_trajectory_detected",
            "top_success": top_success,
        }
        adjusted_payload["next_action"] = {
            **(adjusted_payload.get("next_action") or {}),
            "memory_weighted_adjustment": "boost_successful_pattern",
            "successful_pattern": top_success,
        }
        return decision_type, adjusted_payload

    if pattern_weight >= 0.9 and decision_type == "reprioritize_tasks":
        top_pattern = summary["patterns"][0] if summary["patterns"] else None
        adjusted_payload["memory_adjustment"] = {
            "reason": "high_impact_pattern_detected",
            "top_pattern": top_pattern,
        }
        adjusted_payload["next_action"] = {
            "type": "review_plan",
            "title": "Review task plan around a recurring high-impact pattern",
            "suggested_goal": "Adjust the current path using the strongest recurring memory pattern",
            "pattern": top_pattern,
        }
        return "review_plan", adjusted_payload

    adjusted_payload["memory_adjustment"] = {
        "reason": "memory_signals_applied",
        "failure_weight": failure_weight,
        "success_weight": success_weight,
        "pattern_weight": pattern_weight,
    }
    return decision_type, adjusted_payload


def _apply_system_state_weighting(
    decision_type: str,
    payload: dict,
    system_state: dict | None = None,
) -> tuple[str, dict]:
    state = system_state or {}
    health_status = str(state.get("health_status") or "healthy").lower()
    failure_rate = float(state.get("failure_rate", 0.0) or 0.0)
    system_load = float(state.get("system_load", 0.0) or 0.0)

    adjusted_payload = {
        **payload,
        "system_state": state,
    }

    if health_status == "critical":
        adjusted_payload["system_adjustment"] = {
            "reason": "critical_system_health",
            "failure_rate": failure_rate,
            "system_load": system_load,
        }
        adjusted_payload["next_action"] = {
            "type": "review_plan",
            "title": "Review current plan under critical system conditions",
            "suggested_goal": "Choose a safe, low-risk action until failures and load stabilize",
            "safe_mode": True,
        }
        return "review_plan", adjusted_payload

    if failure_rate >= 0.20 and decision_type == "continue_highest_priority_task":
        adjusted_payload["system_adjustment"] = {
            "reason": "elevated_failure_rate",
            "failure_rate": failure_rate,
        }
        adjusted_payload["next_action"] = {
            "type": "review_plan",
            "title": "Review the current path due to elevated failure rate",
            "suggested_goal": "Avoid repeating risky execution paths until failure rate improves",
        }
        return "review_plan", adjusted_payload

    if system_load >= 0.75:
        adjusted_payload["system_adjustment"] = {
            "reason": "high_system_load",
            "system_load": system_load,
        }
        next_action = dict(adjusted_payload.get("next_action") or {})
        next_action["load_adjustment"] = "reduce_heavy_execution"
        next_action["prefer_lightweight_actions"] = True
        if not next_action.get("title"):
            next_action["title"] = "Reduce heavy execution while system load is elevated"
        adjusted_payload["next_action"] = next_action
        return decision_type, adjusted_payload

    adjusted_payload["system_adjustment"] = {
        "reason": "system_state_applied",
        "health_status": health_status,
        "failure_rate": failure_rate,
        "system_load": system_load,
    }
    return decision_type, adjusted_payload


def _apply_goal_weighting(
    decision_type: str,
    payload: dict,
    goals: list[dict] | None = None,
) -> tuple[str, dict]:
    from apps.masterplan.services.goal_service import calculate_goal_alignment

    ranked_goals = goals or []
    if not ranked_goals:
        adjusted_payload = {**payload, "goal_summary": {"goal_count": 0, "goal_alignment": 0.0}}
        return decision_type, adjusted_payload

    top_goal = ranked_goals[0]
    next_action = dict(payload.get("next_action") or {})
    alignment_text = " ".join(
        filter(
            None,
            [
                str(next_action.get("title") or ""),
                str(next_action.get("suggested_goal") or ""),
                str(next_action.get("task_name") or ""),
                str(payload.get("reason") or ""),
            ],
        )
    )
    goal_alignment = calculate_goal_alignment(ranked_goals, alignment_text)
    adjusted_payload = {
        **payload,
        "goal_summary": {
            "goal_count": len(ranked_goals),
            "goal_alignment": goal_alignment,
            "top_goal": {
                "id": top_goal.get("id"),
                "name": top_goal.get("name"),
                "ranked_priority": top_goal.get("ranked_priority"),
                "progress": top_goal.get("progress"),
            },
        },
    }

    if goal_alignment >= 0.25:
        next_action["goal_alignment"] = {
            "status": "aligned",
            "score": goal_alignment,
            "goal_id": top_goal.get("id"),
            "goal_name": top_goal.get("name"),
        }
        adjusted_payload["next_action"] = next_action
        return decision_type, adjusted_payload

    if float(top_goal.get("ranked_priority") or 0.0) >= 0.70:
        adjusted_payload["goal_adjustment"] = {
            "reason": "low_goal_alignment",
            "goal_id": top_goal.get("id"),
            "goal_name": top_goal.get("name"),
            "goal_alignment": goal_alignment,
        }
        adjusted_payload["next_action"] = {
            "type": "review_plan",
            "title": f"Realign work toward goal: {top_goal.get('name')}",
            "suggested_goal": top_goal.get("description") or top_goal.get("name"),
            "goal_id": top_goal.get("id"),
            "goal_alignment": {"status": "low_alignment", "score": goal_alignment},
        }
        return "review_plan", adjusted_payload

    next_action["goal_alignment"] = {"status": "weak_alignment", "score": goal_alignment}
    adjusted_payload["next_action"] = next_action
    return decision_type, adjusted_payload


def _apply_social_weighting(
    decision_type: str,
    payload: dict,
    social_signals: list[dict] | None = None,
) -> tuple[str, dict]:
    signals = list(social_signals or [])
    adjusted_payload = {**payload, "social_signals": signals}
    if not signals:
        return decision_type, adjusted_payload

    top_success = next((signal for signal in signals if signal.get("type") == "success"), None)
    top_failure = next((signal for signal in signals if signal.get("type") == "failure"), None)
    pattern = next((signal for signal in signals if signal.get("type") == "pattern"), None)

    if top_failure and float(top_failure.get("engagement_score", 0.0) or 0.0) <= 2.0:
        adjusted_payload["social_adjustment"] = {
            "reason": "low_social_performance",
            "signal": top_failure,
        }
        adjusted_payload["next_action"] = {
            "type": "review_plan",
            "title": "Review content strategy due to low social performance",
            "suggested_goal": "Adjust content direction before publishing more low-performing updates",
            "social_signal": top_failure,
        }
        return "review_plan", adjusted_payload

    if top_success:
        next_action = dict(adjusted_payload.get("next_action") or {})
        next_action["social_strategy"] = {
            "status": "boost_success_pattern",
            "content_hint": top_success.get("content"),
            "engagement_score": top_success.get("engagement_score"),
            "pattern": pattern,
        }
        adjusted_payload["next_action"] = next_action
        adjusted_payload["social_adjustment"] = {
            "reason": "high_social_performance",
            "signal": top_success,
            "pattern": pattern,
        }
    return decision_type, adjusted_payload


def _decide(
    score_snapshot: dict | None,
    feedback_context: dict | None = None,
    memory_signals: list[dict] | None = None,
    system_state: dict | None = None,
    goals: list[dict] | None = None,
    social_signals: list[dict] | None = None,
) -> tuple[str, dict]:
    feedback_context = feedback_context or {}
    if feedback_context.get("negative", 0) > feedback_context.get("positive", 0):
        suggestions = _build_focus_suggestions(score_snapshot or {})
        decision_type = "review_plan"
        payload = {
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
        decision_type, payload = _apply_memory_weighting(decision_type, payload, memory_signals)
        decision_type, payload = _apply_system_state_weighting(decision_type, payload, system_state)
        decision_type, payload = _apply_goal_weighting(decision_type, payload, goals)
        return _apply_social_weighting(decision_type, payload, social_signals)

    if not score_snapshot:
        suggestions = _build_focus_suggestions({})
        decision_type = "review_plan"
        payload = {
            "reason": "insufficient_data",
            "suggestions": suggestions,
            "suggested_goal": suggestions[0]["suggested_goal"],
            "next_action": {
                "type": "review_plan",
                "title": "Review current plan due to insufficient score data",
                "suggested_goal": suggestions[0]["suggested_goal"],
            },
        }
        decision_type, payload = _apply_memory_weighting(decision_type, payload, memory_signals)
        decision_type, payload = _apply_system_state_weighting(decision_type, payload, system_state)
        decision_type, payload = _apply_goal_weighting(decision_type, payload, goals)
        return _apply_social_weighting(decision_type, payload, social_signals)

    try:
        execution_speed = float(score_snapshot.get("execution_speed", 50.0) or 50.0)
        decision_efficiency = float(score_snapshot.get("decision_efficiency", 50.0) or 50.0)
        focus_quality = float(score_snapshot.get("focus_quality", 50.0) or 50.0)
        ai_boost = float(score_snapshot.get("ai_productivity_boost", 50.0) or 50.0)
    except (TypeError, ValueError):
        suggestions = _build_focus_suggestions({})
        decision_type = "review_plan"
        payload = {
            "reason": "invalid_snapshot",
            "suggestions": suggestions,
            "suggested_goal": suggestions[0]["suggested_goal"],
            "next_action": {
                "type": "review_plan",
                "title": "Review current plan due to invalid score snapshot",
                "suggested_goal": suggestions[0]["suggested_goal"],
            },
        }
        decision_type, payload = _apply_memory_weighting(decision_type, payload, memory_signals)
        decision_type, payload = _apply_system_state_weighting(decision_type, payload, system_state)
        decision_type, payload = _apply_goal_weighting(decision_type, payload, goals)
        return _apply_social_weighting(decision_type, payload, social_signals)

    if execution_speed < 40 or decision_efficiency < 40:
        decision_type = "reprioritize_tasks"
        payload = {
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
        decision_type, payload = _apply_memory_weighting(decision_type, payload, memory_signals)
        decision_type, payload = _apply_system_state_weighting(decision_type, payload, system_state)
        decision_type, payload = _apply_goal_weighting(decision_type, payload, goals)
        return _apply_social_weighting(decision_type, payload, social_signals)
    if focus_quality < 40:
        suggestions = _build_focus_suggestions(score_snapshot)
        decision_type = "review_plan"
        payload = {
            "reason": "focus_below_threshold",
            "suggestions": suggestions,
            "suggested_goal": suggestions[0]["suggested_goal"],
            "next_action": {
                "type": "review_plan",
                "title": "Review plan and refresh context before continuing",
                "suggested_goal": suggestions[0]["suggested_goal"],
            },
        }
        decision_type, payload = _apply_memory_weighting(decision_type, payload, memory_signals)
        decision_type, payload = _apply_system_state_weighting(decision_type, payload, system_state)
        decision_type, payload = _apply_goal_weighting(decision_type, payload, goals)
        return _apply_social_weighting(decision_type, payload, social_signals)
    if ai_boost < 40:
        suggestions = _build_ai_suggestions(score_snapshot)
        decision_type = "review_plan"
        payload = {
            "reason": "ai_productivity_below_threshold",
            "suggestions": suggestions,
            "suggested_goal": suggestions[0]["suggested_goal"],
            "next_action": {
                "type": "review_plan",
                "title": "Review plan and use ARM guidance before continuing",
                "suggested_goal": suggestions[0]["suggested_goal"],
            },
        }
        decision_type, payload = _apply_memory_weighting(decision_type, payload, memory_signals)
        decision_type, payload = _apply_system_state_weighting(decision_type, payload, system_state)
        decision_type, payload = _apply_goal_weighting(decision_type, payload, goals)
        return _apply_social_weighting(decision_type, payload, social_signals)
    decision_type = "continue_highest_priority_task"
    payload = {
        "reason": "kpis_stable",
        "next_action": {
            "type": "continue_highest_priority_task",
            "title": "Continue the highest-priority in-progress task",
        },
    }
    decision_type, payload = _apply_memory_weighting(decision_type, payload, memory_signals)
    decision_type, payload = _apply_system_state_weighting(decision_type, payload, system_state)
    decision_type, payload = _apply_goal_weighting(decision_type, payload, goals)
    return _apply_social_weighting(decision_type, payload, social_signals)


def _reprioritize_tasks(user_id: str, db) -> dict:
    from apps.tasks.models import Task

    user_uuid = _normalize_user_id(user_id)
    if user_uuid is None:
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

    with transaction_scope(db):
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
            db.add(task)
        db.flush()
        return {"task_ids": [item["task_id"] for item in affected], "tasks": affected}


def run_loop(
    user_id: str,
    trigger_event: str,
    db,
    score_snapshot: dict | None = None,
    feedback_context: dict | None = None,
    loop_context: dict | None = None,
):
    from apps.automation.models import LoopAdjustment

    try:
        with transaction_scope(db):
            normalized_trigger = _normalize_trigger_event(trigger_event)
            persisted_user_id = _normalize_user_id(user_id)
            owner_user_id = persisted_user_id or user_id
            if score_snapshot is None:
                from apps.analytics.services.infinity_service import get_user_kpi_snapshot

                score_snapshot = get_user_kpi_snapshot(user_id=owner_user_id, db=db)
            feedback_context = feedback_context or _get_recent_feedback_context(user_id=owner_user_id, db=db)
            memory_signals = list((loop_context or {}).get("memory_signals") or [])
            system_state = dict((loop_context or {}).get("system_state") or {})
            goals = list((loop_context or {}).get("goals") or [])
            social_signals = list((loop_context or {}).get("social_signals") or [])
            decision_type, payload = _decide(
                score_snapshot,
                feedback_context=feedback_context,
                memory_signals=memory_signals,
                system_state=system_state,
                goals=goals,
                social_signals=social_signals,
            )
            decision_type, payload = _apply_strategy_accuracy_weighting(
                user_id=owner_user_id,
                decision_type=decision_type,
                payload=payload,
                db=db,
            )
            now = datetime.now(timezone.utc)

            if supports_managed_transactions(db):
                last_adjustment = db.execute(
                    select(LoopAdjustment)
                    .where(LoopAdjustment.user_id == persisted_user_id)
                    .order_by(LoopAdjustment.applied_at.desc(), LoopAdjustment.created_at.desc())
                    .with_for_update()
                ).scalars().first()
            else:
                last_adjustment = get_latest_adjustment(user_id=owner_user_id, db=db)
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
                reprioritized = _reprioritize_tasks(user_id=owner_user_id, db=db)
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
                top_task = _get_top_incomplete_task(user_id=owner_user_id, db=db)
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

            expected_outcome, expected_score = _build_expectation(decision_type, score_snapshot)

            adjustment = LoopAdjustment(
                user_id=persisted_user_id,
                trace_id=get_current_trace_id(),
                trigger_event=normalized_trigger,
                score_snapshot=score_snapshot,
                decision_type=decision_type,
                expected_outcome=expected_outcome,
                expected_score=expected_score,
                adjustment_payload={
                    **payload,
                    "feedback_context": feedback_context,
                    "loop_context": loop_context or {},
                    "expected_vs_actual": {
                        "expected_outcome": expected_outcome,
                        "expected_score": expected_score,
                    },
                },
                applied_at=now,
            )
            db.add(adjustment)
            db.flush()
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

