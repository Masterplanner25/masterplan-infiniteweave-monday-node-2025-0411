import uuid
from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from db.models import LearningRecordDB, LearningThresholdDB, ScoreSnapshotDB

DEFAULT_VELOCITY_TREND = 0.35
DEFAULT_NARRATIVE_TREND = 1.0
DEFAULT_EARLY_VELOCITY_RATE = 0.2
DEFAULT_EARLY_NARRATIVE_CEILING = 30.0
LEARNING_LOOKBACK = 20
SPIKE_DELTA = 5.0


def get_learning_thresholds(db: Session) -> LearningThresholdDB:
    record = db.query(LearningThresholdDB).first()
    if record:
        return record
    record = LearningThresholdDB(
        id=str(uuid.uuid4()),
        velocity_trend=DEFAULT_VELOCITY_TREND,
        narrative_trend=DEFAULT_NARRATIVE_TREND,
        early_velocity_rate=DEFAULT_EARLY_VELOCITY_RATE,
        early_narrative_ceiling=DEFAULT_EARLY_NARRATIVE_CEILING,
        last_updated=datetime.utcnow(),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def record_prediction(
    db: Session,
    drop_point_id: str,
    prediction: str,
    velocity_at_prediction: float,
    narrative_at_prediction: float,
):
    learning = LearningRecordDB(
        id=str(uuid.uuid4()),
        drop_point_id=drop_point_id,
        prediction=prediction,
        predicted_at=datetime.utcnow(),
        velocity_at_prediction=velocity_at_prediction,
        narrative_at_prediction=narrative_at_prediction,
    )
    db.add(learning)
    db.commit()
    db.refresh(learning)
    return learning


def evaluate_outcome(drop_point_id: str, db: Session) -> Dict:
    record = (
        db.query(LearningRecordDB)
        .filter(
            LearningRecordDB.drop_point_id == drop_point_id,
            LearningRecordDB.actual_outcome.is_(None),
        )
        .order_by(LearningRecordDB.predicted_at.desc())
        .first()
    )
    if not record:
        return {"status": "no_prediction"}

    future_snapshots = (
        db.query(ScoreSnapshotDB)
        .filter(ScoreSnapshotDB.drop_point_id == drop_point_id)
        .filter(ScoreSnapshotDB.timestamp > record.predicted_at)
        .order_by(ScoreSnapshotDB.timestamp.asc())
        .all()
    )
    if not future_snapshots:
        return {"status": "no_future_data"}

    latest = future_snapshots[-1]
    delta = (latest.narrative_score or 0.0) - record.narrative_at_prediction
    velocity_delta = (latest.velocity_score or 0.0) - record.velocity_at_prediction

    if delta > SPIKE_DELTA:
        actual = "spiked"
    elif velocity_delta < 0:
        actual = "declined"
    else:
        actual = "stable"

    record.actual_outcome = actual
    record.evaluated_at = datetime.utcnow()
    record.was_correct = record.prediction == actual
    db.commit()
    db.refresh(record)
    return {
        "drop_point_id": drop_point_id,
        "prediction": record.prediction,
        "actual_outcome": actual,
        "was_correct": record.was_correct,
    }


def adjust_thresholds(db: Session, lookback: int = LEARNING_LOOKBACK) -> Dict:
    records = (
        db.query(LearningRecordDB)
        .filter(LearningRecordDB.actual_outcome.isnot(None))
        .order_by(LearningRecordDB.predicted_at.desc())
        .limit(lookback)
        .all()
    )
    if not records:
        return {"status": "no_data"}

    threshold = get_learning_thresholds(db)
    evaluated = [r for r in records if r.was_correct is not None]
    correct = sum(1 for r in evaluated if r.was_correct)
    accuracy = correct / len(evaluated) if evaluated else 0.0

    false_pos = sum(
        1
        for r in evaluated
        if r.prediction == "likely_to_spike" and r.actual_outcome != "spiked"
    )
    false_neg = sum(
        1
        for r in evaluated
        if r.prediction != "likely_to_spike" and r.actual_outcome == "spiked"
    )

    if false_pos > false_neg:
        threshold.velocity_trend += 0.05
        threshold.narrative_trend += 0.5
    elif false_neg > false_pos:
        threshold.velocity_trend = max(0.05, threshold.velocity_trend - 0.05)
        threshold.narrative_trend = max(0.5, threshold.narrative_trend - 0.5)

    threshold.last_updated = datetime.utcnow()
    db.commit()
    db.refresh(threshold)
    return {
        "accuracy": round(accuracy, 3),
        "false_positives": false_pos,
        "false_negatives": false_neg,
        "thresholds": {
            "velocity_trend": round(threshold.velocity_trend, 3),
            "narrative_trend": round(threshold.narrative_trend, 3),
        },
    }


def learning_stats(db: Session) -> Dict:
    records = db.query(LearningRecordDB).all()
    total = len(records)
    evaluated = [r for r in records if r.actual_outcome]
    correct = sum(1 for r in evaluated if r.was_correct)
    accuracy = correct / len(evaluated) if evaluated else 0.0
    false_pos = sum(
        1 for r in evaluated if r.prediction == "likely_to_spike" and r.actual_outcome != "spiked"
    )
    false_neg = sum(
        1 for r in evaluated if r.prediction != "likely_to_spike" and r.actual_outcome == "spiked"
    )
    return {
        "total_predictions": total,
        "evaluated": len(evaluated),
        "accuracy": round(accuracy, 3),
        "false_positive_rate": round(false_pos / len(evaluated), 3) if evaluated else 0.0,
        "false_negative_rate": round(false_neg / len(evaluated), 3) if evaluated else 0.0,
    }

