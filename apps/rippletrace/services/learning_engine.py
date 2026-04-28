from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Dict

from sqlalchemy.orm import Session

DEFAULT_VELOCITY_TREND = 0.35
DEFAULT_NARRATIVE_TREND = 1.0
DEFAULT_EARLY_VELOCITY_RATE = 0.2
DEFAULT_EARLY_NARRATIVE_CEILING = 30.0
LEARNING_LOOKBACK = 20
SPIKE_DELTA = 5.0


def get_learning_thresholds(db: Session):
    from apps.automation.public import ensure_learning_thresholds

    return ensure_learning_thresholds(
        db,
        velocity_trend=DEFAULT_VELOCITY_TREND,
        narrative_trend=DEFAULT_NARRATIVE_TREND,
        early_velocity_rate=DEFAULT_EARLY_VELOCITY_RATE,
        early_narrative_ceiling=DEFAULT_EARLY_NARRATIVE_CEILING,
    )


def record_prediction(
    db: Session,
    drop_point_id: str,
    prediction: str,
    velocity_at_prediction: float,
    narrative_at_prediction: float,
):
    from apps.automation.public import create_learning_record

    return create_learning_record(
        db,
        drop_point_id=drop_point_id,
        prediction=prediction,
        predicted_at=datetime.now(timezone.utc),
        velocity_at_prediction=velocity_at_prediction,
        narrative_at_prediction=narrative_at_prediction,
    )


def evaluate_outcome(drop_point_id: str, db: Session) -> Dict:
    from apps.automation.public import get_latest_learning_record, update_learning_record
    from apps.analytics.public import list_score_snapshots

    record = get_latest_learning_record(db, drop_point_id=drop_point_id, pending_only=True)
    if not record:
        return {"status": "no_prediction"}

    future_snapshots = list_score_snapshots(
        drop_point_id,
        db,
        ascending=True,
        after_timestamp=record.get("predicted_at"),
    )
    if not future_snapshots:
        return {"status": "no_future_data"}

    latest = future_snapshots[-1]
    delta = float(latest.get("narrative_score") or 0.0) - float(record.get("narrative_at_prediction") or 0.0)
    velocity_delta = float(latest.get("velocity_score") or 0.0) - float(record.get("velocity_at_prediction") or 0.0)

    if delta > SPIKE_DELTA:
        actual = "spiked"
    elif velocity_delta < 0:
        actual = "declined"
    else:
        actual = "stable"

    updated = update_learning_record(
        db,
        record_id=record["id"],
        actual_outcome=actual,
        evaluated_at=datetime.now(timezone.utc),
        was_correct=record.get("prediction") == actual,
    ) or record
    return {
        "drop_point_id": drop_point_id,
        "prediction": updated.get("prediction"),
        "actual_outcome": actual,
        "was_correct": updated.get("was_correct"),
    }


def adjust_thresholds(db: Session, lookback: int = LEARNING_LOOKBACK) -> Dict:
    from apps.automation.public import list_learning_records, update_learning_thresholds

    records = list_learning_records(db, limit=lookback, evaluated_only=True)
    if not records:
        return {"status": "no_data"}

    threshold = get_learning_thresholds(db)
    evaluated = [r for r in records if r.get("was_correct") is not None]
    correct = sum(1 for r in evaluated if r.get("was_correct"))
    accuracy = correct / len(evaluated) if evaluated else 0.0

    false_pos = sum(
        1
        for r in evaluated
        if r.get("prediction") == "likely_to_spike" and r.get("actual_outcome") != "spiked"
    )
    false_neg = sum(
        1
        for r in evaluated
        if r.get("prediction") != "likely_to_spike" and r.get("actual_outcome") == "spiked"
    )

    if false_pos > false_neg:
        threshold["velocity_trend"] += 0.05
        threshold["narrative_trend"] += 0.5
    elif false_neg > false_pos:
        threshold["velocity_trend"] = max(0.05, float(threshold.get("velocity_trend") or 0.0) - 0.05)
        threshold["narrative_trend"] = max(0.5, float(threshold.get("narrative_trend") or 0.0) - 0.5)

    threshold = update_learning_thresholds(
        db,
        threshold_id=threshold["id"],
        velocity_trend=threshold["velocity_trend"],
        narrative_trend=threshold["narrative_trend"],
        last_updated=datetime.now(timezone.utc),
    ) or threshold
    return {
        "accuracy": round(accuracy, 3),
        "false_positives": false_pos,
        "false_negatives": false_neg,
        "thresholds": {
            "velocity_trend": round(float(threshold.get("velocity_trend") or 0.0), 3),
            "narrative_trend": round(float(threshold.get("narrative_trend") or 0.0), 3),
        },
    }


def learning_stats(db: Session) -> Dict:
    from apps.automation.public import list_learning_records

    records = list_learning_records(db)
    total = len(records)
    evaluated = [r for r in records if r.get("actual_outcome")]
    correct = sum(1 for r in evaluated if r.get("was_correct"))
    accuracy = correct / len(evaluated) if evaluated else 0.0
    false_pos = sum(
        1 for r in evaluated if r.get("prediction") == "likely_to_spike" and r.get("actual_outcome") != "spiked"
    )
    false_neg = sum(
        1 for r in evaluated if r.get("prediction") != "likely_to_spike" and r.get("actual_outcome") == "spiked"
    )
    return {
        "total_predictions": total,
        "evaluated": len(evaluated),
        "accuracy": round(accuracy, 3),
        "false_positive_rate": round(false_pos / len(evaluated), 3) if evaluated else 0.0,
        "false_negative_rate": round(false_neg / len(evaluated), 3) if evaluated else 0.0,
    }
