from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
import statistics

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

LOOKBACK_SCORES = 30
LOOKBACK_ADJUSTMENTS = 20
MIN_SCORES_REQUIRED = 10
MIN_ADJUSTMENTS_REQUIRED = 5
THRESHOLD_FLOOR = 10.0
THRESHOLD_CEILING = 55.0
THRESHOLD_BUFFER = 5.0
OFFSET_FLOOR = 0.5
OFFSET_CEILING = 10.0
ADAPTATION_COOLDOWN_MINUTES = 120


def get_or_create_thresholds(db: Session, user_id):
    from AINDY.platform_layer.user_ids import parse_user_id
    from apps.analytics.user_score import UserPolicyThresholds

    uid = parse_user_id(user_id)
    row = db.query(UserPolicyThresholds).filter(UserPolicyThresholds.user_id == uid).first()
    if row is None:
        row = UserPolicyThresholds(user_id=uid)
        db.add(row)
        db.flush()
    return row


def get_effective_thresholds(db: Session, user_id) -> dict:
    """
    Return effective per-user KPI low thresholds and expected offsets.
    """
    from ..orchestration.infinity_loop import EXPECTED_SCORE_OFFSETS

    defaults = {
        "kpi_low": {
            "execution_speed": 40.0,
            "decision_efficiency": 40.0,
            "ai_productivity_boost": 40.0,
            "focus_quality": 40.0,
            "masterplan_progress": 40.0,
        },
        "offsets": dict(EXPECTED_SCORE_OFFSETS),
        "is_personalized": False,
        "adapted_count": 0,
        "last_adapted_at": None,
    }
    try:
        row = get_or_create_thresholds(db, user_id)
        adapted_count = getattr(row, "adapted_count", 0)
        if not isinstance(adapted_count, (int, float)) or int(adapted_count) <= 0:
            return defaults
        return {
            "kpi_low": {
                "execution_speed": float(row.execution_speed_low_threshold),
                "decision_efficiency": float(row.decision_efficiency_low_threshold),
                "ai_productivity_boost": float(row.ai_productivity_boost_low_threshold),
                "focus_quality": float(row.focus_quality_low_threshold),
                "masterplan_progress": float(row.masterplan_progress_low_threshold),
            },
            "offsets": {
                "continue_highest_priority_task": float(row.offset_continue_highest_priority_task),
                "create_new_task": float(row.offset_create_new_task),
                "reprioritize_tasks": float(row.offset_reprioritize_tasks),
                "review_plan": float(row.offset_review_plan),
            },
            "is_personalized": True,
            "adapted_count": int(adapted_count or 0),
            "last_adapted_at": row.last_adapted_at.isoformat() if row.last_adapted_at else None,
        }
    except Exception as exc:
        logger.warning("[PolicyAdaptation] get_effective_thresholds failed for %s: %s", user_id, exc)
        return defaults


def adapt_policy_thresholds(db: Session, user_id) -> dict:
    """
    Run one per-user adaptation pass for loop thresholds and expected offsets.
    """
    from AINDY.platform_layer.user_ids import parse_user_id
    from ..orchestration.infinity_loop import EXPECTED_SCORE_OFFSETS
    from apps.analytics.user_score import ScoreHistory
    from apps.automation.infinity_loop import LoopAdjustment

    try:
        uid = parse_user_id(user_id)
        row = get_or_create_thresholds(db, user_id)

        now = datetime.now(timezone.utc)
        if row.last_adapted_at:
            last = row.last_adapted_at
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            if now - last < timedelta(minutes=ADAPTATION_COOLDOWN_MINUTES):
                return {
                    "status": "skipped",
                    "reason": "cooldown",
                    "adapted_count": row.adapted_count,
                }

        history = (
            db.query(ScoreHistory)
            .filter(ScoreHistory.user_id == uid)
            .order_by(ScoreHistory.calculated_at.desc())
            .limit(LOOKBACK_SCORES)
            .all()
        )

        thresholds_adapted = False
        if len(history) >= MIN_SCORES_REQUIRED:
            kpi_col_map = {
                "execution_speed": "execution_speed_score",
                "decision_efficiency": "decision_efficiency_score",
                "ai_productivity_boost": "ai_productivity_boost_score",
                "focus_quality": "focus_quality_score",
                "masterplan_progress": "masterplan_progress_score",
            }
            threshold_col_map = {
                "execution_speed": "execution_speed_low_threshold",
                "decision_efficiency": "decision_efficiency_low_threshold",
                "ai_productivity_boost": "ai_productivity_boost_low_threshold",
                "focus_quality": "focus_quality_low_threshold",
                "masterplan_progress": "masterplan_progress_low_threshold",
            }
            for kpi, history_col in kpi_col_map.items():
                values = [float(getattr(item, history_col) or 40.0) for item in history]
                if len(values) >= 4:
                    values_sorted = sorted(values)
                    p25_idx = max(0, len(values_sorted) // 4)
                    p25 = values_sorted[p25_idx]
                    new_threshold = max(
                        THRESHOLD_FLOOR,
                        min(THRESHOLD_CEILING, p25 - THRESHOLD_BUFFER),
                    )
                    setattr(row, threshold_col_map[kpi], round(new_threshold, 2))
            thresholds_adapted = True

        offsets_adapted = False
        offset_col_map = {
            "continue_highest_priority_task": "offset_continue_highest_priority_task",
            "create_new_task": "offset_create_new_task",
            "reprioritize_tasks": "offset_reprioritize_tasks",
            "review_plan": "offset_review_plan",
        }
        for decision_type, col in offset_col_map.items():
            rows = (
                db.query(LoopAdjustment)
                .filter(
                    LoopAdjustment.user_id == uid,
                    LoopAdjustment.decision_type == decision_type,
                    LoopAdjustment.actual_score.isnot(None),
                    LoopAdjustment.expected_score.isnot(None),
                )
                .order_by(LoopAdjustment.applied_at.desc(), LoopAdjustment.created_at.desc())
                .limit(LOOKBACK_ADJUSTMENTS)
                .all()
            )
            if len(rows) < MIN_ADJUSTMENTS_REQUIRED:
                continue
            deltas = [
                float(item.actual_score or 0) - float(item.expected_score or 0)
                for item in rows
            ]
            observed_mean_delta = statistics.mean(deltas)
            default_offset = EXPECTED_SCORE_OFFSETS.get(decision_type, 1.0)
            new_offset = max(
                OFFSET_FLOOR,
                min(OFFSET_CEILING, default_offset + observed_mean_delta),
            )
            setattr(row, col, round(new_offset, 3))
            offsets_adapted = True

        if not thresholds_adapted and not offsets_adapted:
            return {
                "status": "insufficient_data",
                "score_history_rows": len(history),
                "min_required": MIN_SCORES_REQUIRED,
            }

        row.adapted_count = row.adapted_count + 1
        row.last_adapted_at = now
        row.updated_at = now
        db.add(row)
        db.commit()
        db.refresh(row)

        effective = get_effective_thresholds(db, user_id)
        return {
            "status": "adapted",
            "adapted_count": row.adapted_count,
            "thresholds_adapted": thresholds_adapted,
            "offsets_adapted": offsets_adapted,
            "thresholds": effective["kpi_low"],
            "offsets": effective["offsets"],
        }
    except Exception as exc:
        logger.warning("[PolicyAdaptation] adapt_policy_thresholds failed for %s: %s", user_id, exc)
        try:
            db.rollback()
        except Exception:
            logger.debug("[PolicyAdaptation] rollback failed")
        return {"status": "error", "error": str(exc)}
