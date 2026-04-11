from typing import Dict, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from AINDY.db.models import ScoreSnapshotDB

NARRATIVE_SPIKE_THRESHOLD = 5.0
EMERGING_VELOCITY_THRESHOLD = 0.75
EMERGING_NARRATIVE_CEILING = 20.0


def _normalize(value: Optional[float]) -> float:
    return float(value) if value is not None else 0.0


def _snapshot_to_dict(snapshot: ScoreSnapshotDB) -> dict:
    return {
        "timestamp": snapshot.timestamp.isoformat() if snapshot.timestamp else None,
        "narrative_score": _normalize(snapshot.narrative_score),
        "velocity_score": _normalize(snapshot.velocity_score),
        "spread_score": _normalize(snapshot.spread_score),
    }


def _construct_delta_payload(
    drop_point_id: str, previous: ScoreSnapshotDB, latest: ScoreSnapshotDB
) -> dict:
    narrative_delta = _normalize(latest.narrative_score) - _normalize(
        previous.narrative_score
    )
    velocity_delta = _normalize(latest.velocity_score) - _normalize(
        previous.velocity_score
    )
    spread_delta = _normalize(latest.spread_score) - _normalize(
        previous.spread_score
    )
    delta_minutes = max(
        (latest.timestamp - previous.timestamp).total_seconds() / 60.0, 0.0
    )
    rate_base = max(delta_minutes, 1.0)
    narrative_rate = narrative_delta / rate_base
    velocity_rate = velocity_delta / rate_base

    if velocity_rate > 0:
        momentum = "accelerating"
    elif velocity_rate < 0:
        momentum = "decaying"
    else:
        momentum = "stable"

    signal_spike = narrative_delta > NARRATIVE_SPIKE_THRESHOLD

    return {
        "drop_point_id": drop_point_id,
        "latest_scores": _snapshot_to_dict(latest),
        "previous_scores": _snapshot_to_dict(previous),
        "deltas": {
            "narrative": round(narrative_delta, 4),
            "velocity": round(velocity_delta, 4),
            "spread": round(spread_delta, 4),
        },
        "rates": {
            "narrative_rate": round(narrative_rate, 4),
            "velocity_rate": round(velocity_rate, 4),
        },
        "momentum": momentum,
        "signal_spike": signal_spike,
        "delta_minutes": round(delta_minutes, 2),
    }


def compute_deltas(drop_point_id: str, db: Session) -> dict:
    snapshots = (
        db.query(ScoreSnapshotDB)
        .filter(ScoreSnapshotDB.drop_point_id == drop_point_id)
        .order_by(ScoreSnapshotDB.timestamp.desc())
        .limit(2)
        .all()
    )
    if not snapshots:
        return {"drop_point_id": drop_point_id, "status": "no_snapshots"}
    if len(snapshots) == 1:
        return {
            "drop_point_id": drop_point_id,
            "status": "insufficient_data",
            "latest_scores": _snapshot_to_dict(snapshots[0]),
        }

    previous, latest = snapshots[1], snapshots[0]
    return _construct_delta_payload(drop_point_id, previous, latest)


def drop_point_ids_with_history(db: Session) -> List[str]:
    rows = (
        db.query(ScoreSnapshotDB.drop_point_id)
        .group_by(ScoreSnapshotDB.drop_point_id)
        .having(func.count(ScoreSnapshotDB.id) >= 2)
        .all()
    )
    return [row[0] for row in rows]


def _delta_stats_for_drop(
    drop_point_id: str, db: Session
) -> Optional[Tuple[ScoreSnapshotDB, ScoreSnapshotDB, Dict]]:
    snapshots = (
        db.query(ScoreSnapshotDB)
        .filter(ScoreSnapshotDB.drop_point_id == drop_point_id)
        .order_by(ScoreSnapshotDB.timestamp.desc())
        .limit(2)
        .all()
    )
    if len(snapshots) < 2:
        return None
    previous, latest = snapshots[1], snapshots[0]
    payload = _construct_delta_payload(drop_point_id, previous, latest)
    return previous, latest, payload


def find_momentum_leaders(db: Session) -> dict:
    candidate_ids = drop_point_ids_with_history(db)
    fastest_accelerator = None
    biggest_spike = None
    for drop_id in candidate_ids:
        stats_data = _delta_stats_for_drop(drop_id, db)
        if not stats_data:
            continue
        _, _, payload = stats_data
        velocity_rate = payload["rates"]["velocity_rate"]
        narrative_delta = payload["deltas"]["narrative"]

        if (
            not fastest_accelerator
            or velocity_rate > fastest_accelerator["rates"]["velocity_rate"]
        ):
            fastest_accelerator = payload

        if not biggest_spike or narrative_delta > biggest_spike["deltas"]["narrative"]:
            biggest_spike = payload

    return {
        "fastest_accelerating": fastest_accelerator,
        "biggest_spike": biggest_spike,
    }


def emerging_drops(
    db: Session,
    velocity_threshold: float = EMERGING_VELOCITY_THRESHOLD,
    narrative_ceiling: float = EMERGING_NARRATIVE_CEILING,
    limit: int = 5,
) -> List[dict]:
    emerging = []
    candidate_ids = drop_point_ids_with_history(db)
    for drop_id in candidate_ids:
        stats_data = _delta_stats_for_drop(drop_id, db)
        if not stats_data:
            continue
        _, _, payload = stats_data
        velocity_rate = payload["rates"]["velocity_rate"]
        narrative_score = payload["latest_scores"]["narrative_score"]
        if velocity_rate > velocity_threshold and narrative_score <= narrative_ceiling:
            emerging.append(payload)
            if len(emerging) >= limit:
                break
    return emerging

