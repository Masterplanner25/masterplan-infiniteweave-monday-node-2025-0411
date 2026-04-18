from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from apps.rippletrace.models import PingDB
from apps.analytics.models import ScoreSnapshotDB
from apps.rippletrace.services.delta_engine import compute_deltas, drop_point_ids_with_history
from apps.rippletrace.services.learning_engine import get_learning_thresholds, record_prediction


def _normalize(value: Optional[float]) -> float:
    return float(value) if value is not None else 0.0


def _minutes_between(oldest, latest):
    if not oldest or not latest:
        return 1.0
    delta_minutes = (latest - oldest).total_seconds() / 60.0
    return max(delta_minutes, 1.0)


def predict_drop_point(drop_point_id: str, db: Session, record_learning: bool = True) -> dict:
    snapshots = (
        db.query(ScoreSnapshotDB)
        .filter(ScoreSnapshotDB.drop_point_id == drop_point_id)
        .order_by(ScoreSnapshotDB.timestamp.desc())
        .limit(5)
        .all()
    )
    if len(snapshots) < 3:
        return {"drop_point_id": drop_point_id, "status": "insufficient_data"}

    latest = snapshots[0]
    oldest = snapshots[-1]
    delta_minutes = _minutes_between(oldest.timestamp, latest.timestamp)
    velocity_trend = (
        (_normalize(latest.velocity_score) - _normalize(oldest.velocity_score))
        / delta_minutes
    )
    narrative_trend = (
        (_normalize(latest.narrative_score) - _normalize(oldest.narrative_score))
        / delta_minutes
    )

    thresholds = get_learning_thresholds(db)
    velocity_threshold = thresholds.velocity_trend
    narrative_threshold = thresholds.narrative_trend
    early_velocity_rate = thresholds.early_velocity_rate
    early_narrative_ceiling = thresholds.early_narrative_ceiling

    delta_payload = compute_deltas(drop_point_id, db)
    velocity_rate = 0.0
    if isinstance(delta_payload, dict) and "rates" in delta_payload:
        velocity_rate = delta_payload["rates"].get("velocity_rate", 0.0)

    total_pings = (
        db.query(func.count(PingDB.id))
        .filter(PingDB.drop_point_id == drop_point_id)
        .scalar()
        or 0
    )
    latest_narrative = _normalize(latest.narrative_score)

    prediction = "stable"
    if (
        velocity_trend > velocity_threshold
        and narrative_trend > narrative_threshold
    ):
        prediction = "likely_to_spike"
    elif (
        velocity_rate > early_velocity_rate
        and latest_narrative <= early_narrative_ceiling
    ):
        prediction = "emerging_signal"
    elif velocity_trend < 0 and total_pings >= HIGH_PING_THRESHOLD:
        prediction = "plateauing"
    elif velocity_rate < 0:
        prediction = "declining"

    confidence = min(1.0, len(snapshots) / 5.0)

    if record_learning:
        record_prediction(
            db,
            drop_point_id,
            prediction,
            _normalize(latest.velocity_score),
            latest_narrative,
        )

    return {
        "drop_point_id": drop_point_id,
        "prediction": prediction,
        "confidence": round(confidence, 3),
        "velocity_trend": round(velocity_trend, 4),
        "narrative_trend": round(narrative_trend, 4),
        "velocity_rate": round(velocity_rate, 4),
        "latest_narrative_score": round(latest_narrative, 4),
    }


def scan_drop_point_predictions(db: Session, limit: int = 50) -> List[dict]:
    candidate_ids = drop_point_ids_with_history(db)
    predictions: List[dict] = []
    for drop_point_id in candidate_ids[:limit]:
        prediction = predict_drop_point(drop_point_id, db, record_learning=False)
        if prediction.get("status"):
            continue
        predictions.append(prediction)
    return predictions


def prediction_summary(db: Session, limit: int = 50) -> dict:
    predictions = scan_drop_point_predictions(db, limit=limit)
    summary = {
        "total_predicted_spikes": 0,
        "total_declining": 0,
        "total_emerging_signals": 0,
    }
    for prediction in predictions:
        if prediction["prediction"] == "likely_to_spike":
            summary["total_predicted_spikes"] += 1
        if prediction["prediction"] == "declining":
            summary["total_declining"] += 1
        if prediction["prediction"] == "emerging_signal":
            summary["total_emerging_signals"] += 1
    return summary

