from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

HIGH_ACCURACY_THRESHOLD = 70
LOW_ACCURACY_THRESHOLD = 40
LOOKBACK_WINDOW = 50
ADAPTATION_COOLDOWN_MINUTES = 60
MAX_SINGLE_STEP = 0.05

_DECISION_TO_KPI: dict[str, list[str]] = {
    "reprioritize_tasks": ["execution_speed", "decision_efficiency"],
    "review_plan": ["focus_quality", "ai_productivity_boost"],
    "continue_highest_priority_task": [
        "execution_speed",
        "decision_efficiency",
        "focus_quality",
        "ai_productivity_boost",
        "masterplan_progress",
    ],
    "create_new_task": ["masterplan_progress"],
}

_WEIGHT_COLS: dict[str, str] = {
    "execution_speed": "execution_speed_weight",
    "decision_efficiency": "decision_efficiency_weight",
    "ai_productivity_boost": "ai_productivity_boost_weight",
    "focus_quality": "focus_quality_weight",
    "masterplan_progress": "masterplan_progress_weight",
}


def get_or_create_user_weights(db: Session, user_id):
    """
    Return the UserKpiWeights row for user_id, creating it with defaults.
    """
    from AINDY.platform_layer.user_ids import parse_user_id
    from apps.analytics.user_score import KPI_WEIGHTS, UserKpiWeights

    uid = parse_user_id(user_id)
    row = db.query(UserKpiWeights).filter(UserKpiWeights.user_id == uid).first()
    if row is None:
        candidate = UserKpiWeights(
            user_id=uid,
            execution_speed_weight=KPI_WEIGHTS["execution_speed"],
            decision_efficiency_weight=KPI_WEIGHTS["decision_efficiency"],
            ai_productivity_boost_weight=KPI_WEIGHTS["ai_productivity_boost"],
            focus_quality_weight=KPI_WEIGHTS["focus_quality"],
            masterplan_progress_weight=KPI_WEIGHTS["masterplan_progress"],
            adapted_count=0,
        )
        try:
            with db.begin_nested():
                db.add(candidate)
                db.flush()
            row = candidate
        except IntegrityError:
            row = db.query(UserKpiWeights).filter(UserKpiWeights.user_id == uid).first()
    return row


def get_effective_weights(db: Session, user_id) -> dict[str, float]:
    """
    Return per-user learned KPI weights when available, else global defaults.
    """
    from apps.analytics.user_score import KPI_WEIGHTS

    try:
        row = get_or_create_user_weights(db, user_id)
        if row.adapted_count == 0:
            return dict(KPI_WEIGHTS)
        return _row_to_weights(row)
    except Exception as exc:
        logger.warning("[KpiWeights] get_effective_weights failed for %s: %s", user_id, exc)
        return dict(KPI_WEIGHTS)


def adapt_kpi_weights(db: Session, user_id) -> dict:
    """
    Run one bounded adaptation pass for the user's KPI weights.
    """
    from AINDY.platform_layer.user_ids import parse_user_id
    from apps.analytics.user_score import (
        KPI_WEIGHT_LEARNING_RATE,
        KPI_WEIGHT_MAX,
        KPI_WEIGHT_MIN,
        KPI_WEIGHT_MIN_SAMPLES,
    )
    from apps.analytics.services.integration.dependency_adapter import list_strategy_accuracy_adjustments

    try:
        uid = parse_user_id(user_id)
        row = get_or_create_user_weights(db, uid)

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
                    "weights": _row_to_weights(row),
                }

        adjustments = list(
            list_strategy_accuracy_adjustments(
                user_id=str(uid),
                db=db,
                limit=LOOKBACK_WINDOW,
            )
            or []
        )

        if len(adjustments) < KPI_WEIGHT_MIN_SAMPLES:
            return {
                "status": "insufficient_data",
                "samples_found": len(adjustments),
                "samples_required": KPI_WEIGHT_MIN_SAMPLES,
                "adapted_count": row.adapted_count,
                "weights": _row_to_weights(row),
            }

        nudges: dict[str, float] = {k: 0.0 for k in _WEIGHT_COLS}
        nudges_applied = 0
        for adjustment in adjustments:
            accuracy = int(adjustment.get("prediction_accuracy") or 0)
            kpis = _DECISION_TO_KPI.get(adjustment.get("decision_type") or "", [])
            if accuracy >= HIGH_ACCURACY_THRESHOLD:
                for kpi in kpis:
                    nudges[kpi] += KPI_WEIGHT_LEARNING_RATE
                    nudges_applied += 1
            elif accuracy <= LOW_ACCURACY_THRESHOLD:
                for kpi in kpis:
                    nudges[kpi] -= KPI_WEIGHT_LEARNING_RATE
                    nudges_applied += 1

        if nudges_applied == 0:
            return {
                "status": "skipped",
                "reason": "no_nudges",
                "adapted_count": row.adapted_count,
                "weights": _row_to_weights(row),
            }

        new_weights = _row_to_weights(row)
        for kpi, nudge in nudges.items():
            capped = max(-MAX_SINGLE_STEP, min(MAX_SINGLE_STEP, nudge))
            new_weights[kpi] = new_weights[kpi] + capped

        new_weights = _normalize_weights(
            new_weights,
            min_weight=KPI_WEIGHT_MIN,
            max_weight=KPI_WEIGHT_MAX,
        )

        row.execution_speed_weight = new_weights["execution_speed"]
        row.decision_efficiency_weight = new_weights["decision_efficiency"]
        row.ai_productivity_boost_weight = new_weights["ai_productivity_boost"]
        row.focus_quality_weight = new_weights["focus_quality"]
        row.masterplan_progress_weight = new_weights["masterplan_progress"]
        row.adapted_count = row.adapted_count + 1
        row.last_adapted_at = now
        row.updated_at = now
        db.add(row)
        db.commit()
        db.refresh(row)

        return {
            "status": "adapted",
            "adapted_count": row.adapted_count,
            "nudges_applied": nudges_applied,
            "weights": _row_to_weights(row),
        }
    except Exception as exc:
        logger.warning("[KpiWeights] adapt_kpi_weights failed for %s: %s", user_id, exc)
        try:
            db.rollback()
        except Exception:
            logger.debug("[KpiWeights] rollback failed during adaptation")
        return {"status": "error", "error": str(exc)}


def _row_to_weights(row) -> dict[str, float]:
    return {
        "execution_speed": round(float(row.execution_speed_weight or 0.0), 6),
        "decision_efficiency": round(float(row.decision_efficiency_weight or 0.0), 6),
        "ai_productivity_boost": round(float(row.ai_productivity_boost_weight or 0.0), 6),
        "focus_quality": round(float(row.focus_quality_weight or 0.0), 6),
        "masterplan_progress": round(float(row.masterplan_progress_weight or 0.0), 6),
    }


def _normalize_weights(
    weights: dict[str, float],
    *,
    min_weight: float,
    max_weight: float,
) -> dict[str, float]:
    """
    Normalize weights to sum to 1.0 while respecting per-weight bounds.
    """
    from apps.analytics.user_score import KPI_WEIGHTS

    bounded = {
        key: max(min_weight, min(max_weight, float(value)))
        for key, value in weights.items()
    }
    total = sum(bounded.values())
    if total <= 0:
        return dict(KPI_WEIGHTS)

    normalized = {key: (value / total) for key, value in bounded.items()}
    normalized = {
        key: max(min_weight, min(max_weight, value))
        for key, value in normalized.items()
    }

    # Iteratively distribute any residual while honoring bounds.
    for _ in range(10):
        residual = 1.0 - sum(normalized.values())
        if abs(residual) < 1e-9:
            break
        adjustable = [
            key
            for key, value in normalized.items()
            if (residual > 0 and value < max_weight - 1e-9)
            or (residual < 0 and value > min_weight + 1e-9)
        ]
        if not adjustable:
            break
        share = residual / len(adjustable)
        for key in adjustable:
            normalized[key] = max(
                min_weight,
                min(max_weight, normalized[key] + share),
            )

    keys = list(normalized.keys())
    rounded = {key: round(normalized[key], 6) for key in keys}
    residual = round(1.0 - sum(rounded.values()), 6)
    if abs(residual) > 0:
        for key in keys:
            candidate = round(rounded[key] + residual, 6)
            if min_weight <= candidate <= max_weight:
                rounded[key] = candidate
                residual = 0.0
                break
    if abs(sum(rounded.values()) - 1.0) > 1e-5:
        return dict(KPI_WEIGHTS)
    return rounded
