from __future__ import annotations

from datetime import datetime, timezone
from math import log
from typing import List, Optional
import logging
import time
import uuid

from sqlalchemy import func
from sqlalchemy.orm import Session

from apps.rippletrace.models import DropPointDB, PingDB

logger = logging.getLogger(__name__)
SEMANTIC_KEYWORDS = {"similar", "echo", "same idea"}
INFERRED_KEYWORDS = {"unexpected", "random", "coincidence"}


def classify_connection_type(summary: Optional[str]) -> str:
    if not summary:
        return "direct"
    lower_summary = summary.lower()
    # Relationship intelligence tags connection summaries with semantic or inferred signals.
    if any(keyword in lower_summary for keyword in SEMANTIC_KEYWORDS):
        return "semantic"
    if any(keyword in lower_summary for keyword in INFERRED_KEYWORDS):
        return "inferred"
    return "direct"


def _minutes_difference(start: Optional[datetime], end: Optional[datetime]) -> float:
    if not start or not end:
        return 0.0
    delta = (end - start).total_seconds() / 60.0
    return max(round(delta, 2), 0.0)


def _map_drop_point_schema(drop_point: DropPointDB) -> dict:
    return {
        "id": drop_point.id,
        "title": drop_point.title,
        "platform": drop_point.platform,
        "drop_date": drop_point.date_dropped.isoformat()
        if drop_point.date_dropped
        else None,
        "narrative_score": drop_point.narrative_score or 0.0,
        "velocity_score": drop_point.velocity_score or 0.0,
        "spread_score": drop_point.spread_score or 0.0,
    }


def _write_snapshot_with_retry(
    db: Session,
    *,
    drop_point_id: str,
    max_retries: int = 3,
    **kwargs,
) -> dict:
    from apps.analytics.public import create_score_snapshot

    last_exc = None
    for attempt in range(max_retries):
        try:
            return create_score_snapshot(drop_point_id=drop_point_id, db=db, **kwargs)
        except Exception as exc:
            last_exc = exc
            logger.warning(
                "[threadweaver] snapshot write attempt %d/%d failed for %s: %s",
                attempt + 1,
                max_retries,
                drop_point_id,
                exc,
            )
            if attempt < max_retries - 1:
                time.sleep(0.1 * (2**attempt))
    raise last_exc


def _analyze_drop_point_internal(drop_point_id: str, db: Session) -> Optional[dict]:
    drop_point = (
        db.query(DropPointDB).filter(DropPointDB.id == drop_point_id).first()
    )
    if not drop_point:
        return None

    pings: List[PingDB] = (
        db.query(PingDB)
        .filter(PingDB.drop_point_id == drop_point_id)
        .order_by(PingDB.date_detected.asc())
        .all()
    )

    total_pings = len(pings)
    platforms = {ping.source_platform for ping in pings if ping.source_platform}

    first_ping_time = None
    last_ping_time = None
    if pings:
        created_times = [ping.date_detected for ping in pings if ping.date_detected]
        if created_times:
            first_ping_time = min(created_times)
            last_ping_time = max(created_times)

    time_to_first_ping = _minutes_difference(drop_point.date_dropped, first_ping_time)
    lifespan_minutes = _minutes_difference(first_ping_time, last_ping_time)

    semantic_hits = sum(1 for ping in pings if ping.connection_type == "semantic")
    inferred_hits = sum(1 for ping in pings if ping.connection_type == "inferred")

    velocity_score = (
        round(total_pings / max(lifespan_minutes, 1.0), 4) if total_pings else 0.0
    )
    spread_score = len(platforms)

    # Narrative score rewards the volume plus bonuses for semantic/inferred connections
    base = total_pings + (semantic_hits * 2) + inferred_hits
    narrative_score = round(base * log(total_pings + 1), 4) if total_pings else 0.0

    drop_point.velocity_score = velocity_score
    drop_point.spread_score = spread_score
    drop_point.narrative_score = narrative_score

    _write_snapshot_with_retry(
        db,
        drop_point_id=drop_point_id,
        timestamp=datetime.now(timezone.utc),
        narrative_score=narrative_score,
        velocity_score=velocity_score,
        spread_score=spread_score,
        snapshot_id=str(uuid.uuid4()),
    )
    db.add(drop_point)
    db.commit()
    db.refresh(drop_point)

    return {
        "drop_point_id": drop_point_id,
        "total_pings": total_pings,
        "unique_platforms": spread_score,
        "first_ping_time": first_ping_time.isoformat() if first_ping_time else None,
        "last_ping_time": last_ping_time.isoformat() if last_ping_time else None,
        "time_to_first_ping": time_to_first_ping,
        "lifespan_minutes": lifespan_minutes,
        "velocity_score": velocity_score,
        "spread_score": spread_score,
        "narrative_score": narrative_score,
    }


def analyze_drop_point(drop_point_id: str, db: Session) -> Optional[dict]:
    try:
        result = _analyze_drop_point_internal(drop_point_id, db)
    except Exception:
        try:
            from AINDY.platform_layer.metrics import rippletrace_drop_points_processed_total

            rippletrace_drop_points_processed_total.labels(status="failure").inc()
        except Exception:
            pass
        raise
    try:
        from AINDY.platform_layer.metrics import rippletrace_drop_points_processed_total

        rippletrace_drop_points_processed_total.labels(status="success").inc()
    except Exception:
        pass
    return result


def analyze_drop_points(drop_point_ids: List[str], db: Session) -> dict:
    results = {"processed": 0, "failed": 0, "errors": []}
    for drop_point_id in drop_point_ids:
        try:
            _analyze_drop_point_internal(drop_point_id, db)
            results["processed"] += 1
            try:
                from AINDY.platform_layer.metrics import (
                    rippletrace_drop_points_processed_total,
                )

                rippletrace_drop_points_processed_total.labels(status="success").inc()
            except Exception:
                pass
        except Exception as exc:
            results["failed"] += 1
            results["errors"].append(
                {
                    "drop_point_id": drop_point_id,
                    "error": str(exc),
                }
            )
            logger.warning(
                "[threadweaver] drop_point %s failed (skipping): %s",
                drop_point_id,
                exc,
            )
            try:
                from AINDY.platform_layer.metrics import (
                    rippletrace_drop_points_processed_total,
                )

                rippletrace_drop_points_processed_total.labels(status="failure").inc()
            except Exception:
                pass
    return results


def get_dashboard_snapshot(db: Session) -> dict:
    total_drop_points = (
        db.query(func.count(DropPointDB.id)).scalar() or 0
    )
    total_pings = db.query(func.count(PingDB.id)).scalar() or 0

    avg_pings_per_drop = (
        round(total_pings / total_drop_points, 2) if total_drop_points else 0.0
    )

    top_drop_point = (
        db.query(DropPointDB)
        .filter(DropPointDB.narrative_score.isnot(None))
        .order_by(DropPointDB.narrative_score.desc())
        .first()
    )
    fastest_spreading_drop = (
        db.query(DropPointDB)
        .filter(DropPointDB.velocity_score.isnot(None))
        .order_by(DropPointDB.velocity_score.desc())
        .first()
    )

    return {
        "total_drop_points": total_drop_points,
        "total_pings": total_pings,
        "avg_pings_per_drop": avg_pings_per_drop,
        "top_drop_point": _map_drop_point_schema(top_drop_point)
        if top_drop_point
        else None,
        "fastest_spreading_drop": _map_drop_point_schema(fastest_spreading_drop)
        if fastest_spreading_drop
        else None,
    }


def get_top_drop_points(db: Session, limit: int = 5) -> List[dict]:
    drop_points = (
        db.query(DropPointDB)
        .filter(DropPointDB.narrative_score.isnot(None))
        .order_by(DropPointDB.narrative_score.desc())
        .limit(limit)
        .all()
    )
    return [_map_drop_point_schema(dp) for dp in drop_points]

