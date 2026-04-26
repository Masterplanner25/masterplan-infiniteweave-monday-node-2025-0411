from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from apps.analytics.public import (
    list_score_snapshot_drop_point_ids,
    list_score_snapshots,
)

NARRATIVE_SPIKE_THRESHOLD = 5.0
EMERGING_VELOCITY_THRESHOLD = 0.75
EMERGING_NARRATIVE_CEILING = 20.0


def _normalize(value: Optional[float]) -> float:
    return float(value) if value is not None else 0.0


def _datetime_from_iso(value: str | None) -> datetime:
    if not value:
        return datetime.min
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.min


def _value(snapshot, key: str):
    if isinstance(snapshot, dict):
        return snapshot.get(key)
    return getattr(snapshot, key, None)


def _snapshot_to_dict(snapshot: dict) -> dict:
    return {
        "timestamp": (
            _value(snapshot, "timestamp").isoformat()
            if isinstance(_value(snapshot, "timestamp"), datetime)
            else _value(snapshot, "timestamp")
        ),
        "narrative_score": _normalize(_value(snapshot, "narrative_score")),
        "velocity_score": _normalize(_value(snapshot, "velocity_score")),
        "spread_score": _normalize(_value(snapshot, "spread_score")),
    }


def _construct_delta_payload(drop_point_id: str, previous: dict, latest: dict) -> dict:
    narrative_delta = _normalize(_value(latest, "narrative_score")) - _normalize(
        _value(previous, "narrative_score")
    )
    velocity_delta = _normalize(_value(latest, "velocity_score")) - _normalize(
        _value(previous, "velocity_score")
    )
    spread_delta = _normalize(_value(latest, "spread_score")) - _normalize(
        _value(previous, "spread_score")
    )
    delta_minutes = max(
        (
            _datetime_from_iso(
                _value(latest, "timestamp").isoformat()
                if isinstance(_value(latest, "timestamp"), datetime)
                else _value(latest, "timestamp")
            )
            - _datetime_from_iso(
                _value(previous, "timestamp").isoformat()
                if isinstance(_value(previous, "timestamp"), datetime)
                else _value(previous, "timestamp")
            )
        ).total_seconds()
        / 60.0,
        0.0,
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
    snapshots = list_score_snapshots(drop_point_id, db, limit=2)
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
    return list_score_snapshot_drop_point_ids(db, min_count=2)


def _delta_stats_for_drop(
    drop_point_id: str, db: Session
) -> Optional[Tuple[dict, dict, Dict]]:
    snapshots = list_score_snapshots(drop_point_id, db, limit=2)
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
