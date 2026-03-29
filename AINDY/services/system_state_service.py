from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import logging
from typing import Any

from sqlalchemy import func

from db.models.agent_run import AgentRun
from db.models.flow_run import FlowRun
from db.models.request_metric import RequestMetric
from db.models.system_event import SystemEvent
from db.models.system_health_log import SystemHealthLog
from db.models.system_state_snapshot import SystemStateSnapshot

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = 15
_PERSIST_TTL_SECONDS = 60
_STATE_CACHE: dict[str, Any] = {"expires_at": None, "persisted_at": None, "value": None}


@dataclass(frozen=True)
class SystemStateThresholds:
    degraded_failure_rate: float = 0.20
    critical_failure_rate: float = 0.35
    degraded_load: float = 0.65
    critical_load: float = 0.85


def compute_current_state(db, *, force_refresh: bool = False, persist_snapshot: bool = True) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    if not force_refresh and _cache_valid(now):
        return _STATE_CACHE["value"]

    window_start = now - timedelta(hours=1)
    previous_window_start = now - timedelta(hours=2)
    recent_events = (
        db.query(SystemEvent)
        .filter(SystemEvent.timestamp >= window_start)
        .order_by(SystemEvent.timestamp.desc())
        .all()
    )
    previous_event_count = (
        db.query(SystemEvent)
        .filter(SystemEvent.timestamp >= previous_window_start, SystemEvent.timestamp < window_start)
        .count()
    )

    active_flow_runs = (
        db.query(FlowRun)
        .filter(FlowRun.status.in_(("running", "waiting")))
        .count()
    )
    active_agent_runs = (
        db.query(AgentRun)
        .filter(AgentRun.status.in_(("approved", "executing", "pending_approval")))
        .count()
    )
    active_runs = active_flow_runs + active_agent_runs

    request_metrics = (
        db.query(RequestMetric)
        .filter(RequestMetric.created_at >= window_start.replace(tzinfo=None))
        .all()
    )
    avg_request_duration = _avg([row.duration_ms for row in request_metrics])

    flow_durations = [
        _duration_ms(row.created_at, row.completed_at or row.updated_at)
        for row in db.query(FlowRun).filter(FlowRun.created_at >= window_start).all()
    ]
    agent_durations = [
        _duration_ms(row.started_at or row.created_at, row.completed_at or row.started_at or row.created_at)
        for row in db.query(AgentRun).filter(AgentRun.created_at >= window_start).all()
    ]
    avg_execution_time = round(_avg(flow_durations + agent_durations + [avg_request_duration]), 2)

    failure_events = [
        event for event in recent_events
        if ".failed" in event.type or event.type.startswith("error.")
    ]
    failure_rate = round(len(failure_events) / max(1, len(recent_events)), 4)

    dominant_event_types = [
        {"type": event_type, "count": count}
        for event_type, count in Counter(event.type for event in recent_events).most_common(5)
    ]
    repeated_failures = _count_repeated_failures(failure_events)
    spike_detected = int(len(recent_events) > max(previous_event_count * 1.5, 25))
    unusual_patterns = _detect_unusual_patterns(
        repeated_failures=repeated_failures,
        spike_detected=bool(spike_detected),
        dominant_event_types=dominant_event_types,
    )

    system_load = round(
        min(
            1.0,
            (active_runs / 12.0) * 0.4
            + min(1.0, avg_execution_time / 5000.0) * 0.35
            + min(1.0, len(recent_events) / 150.0) * 0.25,
        ),
        4,
    )

    latest_health = db.query(SystemHealthLog).order_by(SystemHealthLog.timestamp.desc()).first()
    health_status = _classify_health(
        failure_rate=failure_rate,
        system_load=system_load,
        latest_health=latest_health.status if latest_health else None,
        thresholds=SystemStateThresholds(),
    )

    snapshot = {
        "created_at": now.isoformat(),
        "active_runs": active_runs,
        "failure_rate": failure_rate,
        "avg_execution_time": avg_execution_time,
        "recent_event_count": len(recent_events),
        "system_load": system_load,
        "dominant_event_types": dominant_event_types,
        "health_status": health_status,
        "recent_events": [_serialize_event(event) for event in recent_events[:20]],
        "repeated_failure_count": repeated_failures,
        "spike_detected": bool(spike_detected),
        "unusual_patterns": unusual_patterns,
    }

    _STATE_CACHE["value"] = snapshot
    _STATE_CACHE["expires_at"] = now + timedelta(seconds=_CACHE_TTL_SECONDS)

    if persist_snapshot and _should_persist(now):
        _persist_snapshot(db, snapshot, now)
        _STATE_CACHE["persisted_at"] = now

    return snapshot


def get_latest_snapshot(db) -> dict[str, Any] | None:
    row = db.query(SystemStateSnapshot).order_by(SystemStateSnapshot.created_at.desc()).first()
    if not row:
        return None
    return {
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "active_runs": row.active_runs,
        "failure_rate": row.failure_rate,
        "avg_execution_time": row.avg_execution_time,
        "recent_event_count": row.recent_event_count,
        "system_load": row.system_load,
        "dominant_event_types": row.dominant_event_types or [],
        "health_status": row.health_status,
        "repeated_failure_count": row.repeated_failures,
        "spike_detected": bool(row.spike_detected),
        "unusual_patterns": row.unusual_patterns or [],
    }


def _classify_health(
    *,
    failure_rate: float,
    system_load: float,
    latest_health: str | None,
    thresholds: SystemStateThresholds,
) -> str:
    if latest_health == "critical":
        return "critical"
    if failure_rate >= thresholds.critical_failure_rate or (
        failure_rate >= thresholds.degraded_failure_rate and system_load >= thresholds.critical_load
    ):
        return "critical"
    if latest_health == "degraded":
        return "degraded"
    if failure_rate >= thresholds.degraded_failure_rate or system_load >= thresholds.degraded_load:
        return "degraded"
    return "healthy"


def _count_repeated_failures(failure_events: list[SystemEvent]) -> int:
    counts = Counter(event.type for event in failure_events)
    return sum(count for count in counts.values() if count >= 3)


def _detect_unusual_patterns(
    *,
    repeated_failures: int,
    spike_detected: bool,
    dominant_event_types: list[dict[str, Any]],
) -> list[str]:
    patterns: list[str] = []
    if spike_detected:
        patterns.append("recent_event_spike")
    if repeated_failures:
        patterns.append("repeated_failures")
    if dominant_event_types:
        dominant_type = dominant_event_types[0]["type"]
        if dominant_type.startswith("error.") or dominant_type.endswith(".failed"):
            patterns.append(f"failure_dominant:{dominant_type}")
    return patterns


def _persist_snapshot(db, snapshot: dict[str, Any], now: datetime) -> None:
    row = SystemStateSnapshot(
        created_at=now.replace(tzinfo=None),
        active_runs=snapshot["active_runs"],
        failure_rate=snapshot["failure_rate"],
        avg_execution_time=snapshot["avg_execution_time"],
        recent_event_count=snapshot["recent_event_count"],
        system_load=snapshot["system_load"],
        dominant_event_types=snapshot["dominant_event_types"],
        health_status=snapshot["health_status"],
        repeated_failures=snapshot["repeated_failure_count"],
        spike_detected=1 if snapshot["spike_detected"] else 0,
        unusual_patterns=snapshot["unusual_patterns"],
    )
    db.add(row)
    db.commit()


def _serialize_event(event: SystemEvent) -> dict[str, Any]:
    return {
        "id": str(event.id),
        "type": event.type,
        "timestamp": event.timestamp.isoformat() if event.timestamp else None,
        "trace_id": event.trace_id,
        "source": getattr(event, "source", None),
    }


def _duration_ms(start, end) -> float:
    if not start or not end:
        return 0.0
    if getattr(start, "tzinfo", None) is None:
        start = start.replace(tzinfo=timezone.utc)
    if getattr(end, "tzinfo", None) is None:
        end = end.replace(tzinfo=timezone.utc)
    return max(0.0, (end - start).total_seconds() * 1000.0)


def _avg(values: list[float]) -> float:
    clean = [float(value) for value in values if value is not None]
    if not clean:
        return 0.0
    return sum(clean) / len(clean)


def _cache_valid(now: datetime) -> bool:
    expires_at = _STATE_CACHE.get("expires_at")
    return bool(_STATE_CACHE.get("value")) and expires_at is not None and now < expires_at


def _should_persist(now: datetime) -> bool:
    persisted_at = _STATE_CACHE.get("persisted_at")
    return persisted_at is None or now >= persisted_at + timedelta(seconds=_PERSIST_TTL_SECONDS)
