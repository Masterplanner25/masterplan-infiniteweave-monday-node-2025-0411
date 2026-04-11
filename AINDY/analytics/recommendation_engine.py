from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from AINDY.db.models import ScoreSnapshotDB
from AINDY.analytics.delta_engine import compute_deltas, drop_point_ids_with_history
from AINDY.analytics.prediction_engine import predict_drop_point

RECOMMENDATION_TEMPLATES = {
    "likely_to_spike": {
        "action": "amplify",
        "recommendations": [
            "Post follow-up content within 24 hours",
            "Cross-post to additional platforms",
            "Engage with responses to accelerate spread",
        ],
        "priority": "high",
    },
    "emerging_signal": {
        "action": "nurture",
        "recommendations": [
            "Expand on this topic",
            "Create a deeper breakdown",
            "Tag related entities to increase visibility",
        ],
        "priority": "medium",
    },
    "plateauing": {
        "action": "revive",
        "recommendations": [
            "Reframe or repost with a new angle",
            "Introduce new context or data",
            "Link this DropPoint to a new post",
        ],
        "priority": "medium",
    },
    "declining": {
        "action": "archive_or_replace",
        "recommendations": [
            "Move on to new DropPoint",
            "Extract insights and reuse later",
            "Do not invest additional effort",
        ],
        "priority": "low",
    },
}


def _normalize(value: Optional[float]) -> float:
    return float(value) if value is not None else 0.0


def _latest_snapshot(drop_point_id: str, db: Session) -> Optional[ScoreSnapshotDB]:
    return (
        db.query(ScoreSnapshotDB)
        .filter(ScoreSnapshotDB.drop_point_id == drop_point_id)
        .order_by(ScoreSnapshotDB.timestamp.desc())
        .limit(1)
        .first()
    )


def recommend_for_drop_point(drop_point_id: str, db: Session, log_prediction: bool = True) -> Dict:
    prediction = predict_drop_point(drop_point_id, db, record_learning=log_prediction)
    if prediction.get("status"):
        return {
            "drop_point_id": drop_point_id,
            "action": "monitor",
            "priority": "low",
            "recommendations": ["Collect more data"],
            "prediction": prediction.get("prediction"),
            "confidence": prediction.get("confidence", 0.0),
        }

    delta_payload = compute_deltas(drop_point_id, db)
    latest_snapshot = _latest_snapshot(drop_point_id, db)
    velocity_score = _normalize(latest_snapshot.velocity_score if latest_snapshot else None)
    narrative_score = _normalize(latest_snapshot.narrative_score if latest_snapshot else None)

    template = RECOMMENDATION_TEMPLATES.get(prediction["prediction"])
    next_best_action_score = round(
        min(1.0, prediction.get("confidence", 0.0) + abs(delta_payload.get("rates", {}).get("velocity_rate", 0.0))),
        3,
    )

    if not template:
        return {
            "drop_point_id": drop_point_id,
            "action": "monitor",
            "priority": "low",
            "recommendations": ["Collect more data"],
            "prediction": prediction["prediction"],
            "confidence": prediction.get("confidence", 0.0),
            "velocity_score": velocity_score,
            "narrative_score": narrative_score,
        }

    return {
        "drop_point_id": drop_point_id,
        "action": template["action"],
        "priority": template["priority"],
        "recommendations": template["recommendations"],
        "prediction": prediction["prediction"],
        "confidence": prediction.get("confidence", 0.0),
        "prediction_confidence": prediction.get("confidence", 0.0),
        "velocity_score": velocity_score,
        "narrative_score": narrative_score,
        "delta_minutes": delta_payload.get("delta_minutes"),
        "next_best_action_score": next_best_action_score,
    }


def recommendations_summary(db: Session, limit: int = 20) -> Dict[str, List[Dict]]:
    candidates = drop_point_ids_with_history(db)[:limit]
    summary = {"high_priority_actions": [], "medium_priority_actions": [], "low_priority_actions": []}
    for drop_point_id in candidates:
        rec = recommend_for_drop_point(drop_point_id, db, log_prediction=False)
        bucket = rec.get("priority", "low")
        item = {
            "drop_point_id": drop_point_id,
            "action": rec["action"],
            "reason": (
                f"{rec['prediction']} with confidence {rec.get('confidence', 0.0):.2f}"
                if rec.get("prediction")
                else "Awaiting data"
            ),
            "next_best_action_score": rec.get("next_best_action_score", 0.0),
        }
        if bucket == "high":
            summary["high_priority_actions"].append(item)
        elif bucket == "medium":
            summary["medium_priority_actions"].append(item)
        else:
            summary["low_priority_actions"].append(item)
    return summary


def system_recommendations(db: Session, limit: int = 20) -> List[Dict]:
    return [
        recommend_for_drop_point(dp_id, db, log_prediction=False)
        for dp_id in drop_point_ids_with_history(db)[:limit]
    ]

