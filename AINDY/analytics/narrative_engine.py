from datetime import datetime
from typing import Dict, List, Optional, Set

from sqlalchemy.orm import Session

from db.models import DropPointDB, PingDB, ScoreSnapshotDB
from analytics.causal_engine import get_causal_chain
from analytics.delta_engine import compute_deltas
from analytics.prediction_engine import predict_drop_point
from analytics.recommendation_engine import recommend_for_drop_point


def _split_terms(value: Optional[str]) -> Set[str]:
    if not value:
        return set()
    return {term.strip().lower() for term in value.split(",") if term.strip()}


def _datetime_from_iso(value: Optional[str]) -> datetime:
    if not value:
        return datetime.min
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return datetime.min


def generate_story_summary(narrative_data: Dict) -> str:
    if not narrative_data.get("timeline"):
        return "No narrative data available yet."
    timeline = narrative_data["timeline"][:3]
    sentences = []
    for event in timeline:
        timestamp = event.get("timestamp", "unknown time")
        sentences.append(f"{event.get('event', 'Event')} occurred at {timestamp}.")
    interpretation = narrative_data.get("interpretation", {})
    insight = interpretation.get("insight", "No insight available.")
    recommended = interpretation.get("recommended_action", "No action recommended.")
    sentences.append(insight)
    sentences.append(f"Recommended action: {recommended}.")
    return " ".join(sentences)


def generate_narrative(drop_point_id: str, db: Session) -> Dict:
    drop_point = (
        db.query(DropPointDB).filter(DropPointDB.id == drop_point_id).first()
    )
    if not drop_point:
        return {"drop_point_id": drop_point_id, "status": "not_found"}

    pings = (
        db.query(PingDB)
        .filter(PingDB.drop_point_id == drop_point_id)
        .order_by(PingDB.date_detected.asc())
        .all()
    )
    snapshots = (
        db.query(ScoreSnapshotDB)
        .filter(ScoreSnapshotDB.drop_point_id == drop_point_id)
        .order_by(ScoreSnapshotDB.timestamp.asc())
        .all()
    )

    delta_info = compute_deltas(drop_point_id, db)
    prediction = predict_drop_point(drop_point_id, db, record_learning=False)
    recommendation = recommend_for_drop_point(drop_point_id, db, log_prediction=False)
    causal_chain = get_causal_chain(drop_point_id, db)

    timeline: List[Dict] = []
    if drop_point.date_dropped:
        timeline.append(
            {
                "timestamp": drop_point.date_dropped.isoformat(),
                "event": "DropPoint created",
                "details": drop_point.title,
            }
        )

    for ping in pings:
        timeline.append(
            {
                "timestamp": ping.date_detected.isoformat()
                if ping.date_detected
                else None,
                "event": "Ping detected",
                "platform": ping.source_platform,
                "summary": ping.connection_summary,
            }
        )

    for snapshot in snapshots:
        timeline.append(
            {
                "timestamp": snapshot.timestamp.isoformat()
                if snapshot.timestamp
                else None,
                "event": "Score snapshot",
                "narrative_score": snapshot.narrative_score,
                "velocity_score": snapshot.velocity_score,
                "spread_score": snapshot.spread_score,
            }
        )

    if delta_info.get("signal_spike"):
        timeline.append(
            {
                "timestamp": datetime.utcnow().isoformat(),
                "event": "Spike detected",
                "details": "Narrative score spiked in latest window",
            }
        )

    timeline.sort(key=lambda ev: _datetime_from_iso(ev.get("timestamp")))

    inflection_points: List[Dict] = []
    if pings:
        first_ping = pings[0]
        inflection_points.append(
            {
                "type": "first_ping",
                "timestamp": first_ping.date_detected.isoformat()
                if first_ping.date_detected
                else None,
                "value": first_ping.source_platform,
            }
        )

    max_delta = 0.0
    spike_snapshot: Optional[ScoreSnapshotDB] = None
    for prev, curr in zip(snapshots, snapshots[1:]):
        delta = (curr.narrative_score or 0.0) - (prev.narrative_score or 0.0)
        if delta > max_delta:
            max_delta = delta
            spike_snapshot = curr
    if spike_snapshot:
        inflection_points.append(
            {
                "type": "narrative_spike",
                "timestamp": spike_snapshot.timestamp.isoformat()
                if spike_snapshot.timestamp
                else None,
                "value": max_delta,
            }
        )

    peak_velocity = None
    if snapshots:
        peak_velocity = max(
            snapshots, key=lambda s: s.velocity_score or 0.0, default=None
        )
        if peak_velocity:
            inflection_points.append(
                {
                    "type": "peak_velocity",
                    "timestamp": peak_velocity.timestamp.isoformat()
                    if peak_velocity.timestamp
                    else None,
                    "value": peak_velocity.velocity_score,
                }
            )

    decline_snapshot = None
    for prev, curr in zip(snapshots, snapshots[1:]):
        if (curr.velocity_score or 0.0) < (prev.velocity_score or 0.0):
            decline_snapshot = curr
            break
    if decline_snapshot:
        inflection_points.append(
            {
                "type": "decline_started",
                "timestamp": decline_snapshot.timestamp.isoformat()
                if decline_snapshot.timestamp
                else None,
                "value": decline_snapshot.velocity_score,
            }
        )

    causal_story = {
        "influenced_by": [
            {
                "drop_point_id": entry["drop_point_id"],
                "confidence": entry["confidence"],
                "reason": entry["reason"],
            }
            for entry in causal_chain.get("upstream_causes", [])
        ],
        "led_to": [
            {
                "drop_point_id": entry["drop_point_id"],
                "confidence": entry["confidence"],
                "reason": entry["reason"],
            }
            for entry in causal_chain.get("downstream_effects", [])
        ],
    }

    current_state = delta_info.get("momentum") or prediction.get("prediction") or "stable"
    interpretation = {
        "current_state": current_state,
        "insight": f"Prediction engine signals {prediction.get('prediction')} with confidence {prediction.get('confidence')}.",
        "recommended_action": recommendation.get("action"),
    }

    narrative_data = {
        "drop_point_id": drop_point_id,
        "timeline": timeline,
        "inflection_points": inflection_points,
        "causal_story": causal_story,
        "interpretation": interpretation,
        "summary": "",
        "delta": delta_info,
        "prediction": prediction,
        "recommendation": recommendation,
        "score_snapshots": [
            {
                "timestamp": snapshot.timestamp.isoformat()
                if snapshot.timestamp
                else None,
                "narrative_score": snapshot.narrative_score,
                "velocity_score": snapshot.velocity_score,
            }
            for snapshot in snapshots
        ],
    }

    narrative_data["summary"] = generate_story_summary(narrative_data)
    return narrative_data


def narrative_summary(db: Session, limit: int = 3) -> List[Dict]:
    drop_points = (
        db.query(DropPointDB)
        .order_by(DropPointDB.narrative_score.desc().nulls_last())
        .limit(limit)
        .all()
    )
    return [generate_narrative(dp.id, db) for dp in drop_points if dp]

