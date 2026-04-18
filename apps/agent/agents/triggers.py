"""App-owned trigger evaluation rules."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from AINDY.db.models.system_event import SystemEvent
from AINDY.memory.memory_scoring_service import get_relevant_memories
from AINDY.platform_layer.registry import get_job, register_trigger_evaluator
from AINDY.platform_layer.system_state_service import compute_current_state
from AINDY.utils.uuid_utils import normalize_uuid

DEFAULT_DEFER_SECONDS = 300


def evaluate_autonomy_trigger(payload: dict[str, Any]) -> dict[str, Any]:
    trigger = payload.get("trigger") if isinstance(payload.get("trigger"), dict) else {}
    context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
    trigger_type = str(payload.get("trigger_type") or trigger.get("trigger_type") or "system").lower()
    context = _enrich_context(trigger=trigger, trigger_type=trigger_type, context=context)

    importance = float(trigger.get("importance") or _default_importance(trigger_type))
    system_state = context.get("system_state") or {}
    memory_signals = context.get("memory_signals") or []
    ripple_patterns = context.get("ripple_patterns") or []
    execution_load = float(
        context.get("execution_load")
        if context.get("execution_load") is not None
        else system_state.get("system_load") or 0.0
    )
    goal_alignment_value = context.get("goal_alignment")
    goal_alignment = float(
        goal_alignment_value
        if goal_alignment_value is not None
        else _default_goal_alignment(trigger_type)
    )
    health_status = str(system_state.get("health_status") or "healthy").lower()
    failure_rate = float(system_state.get("failure_rate") or 0.0)

    failure_count = sum(1 for item in memory_signals if item.get("type") == "failure")
    success_count = sum(1 for item in memory_signals if item.get("type") == "success")
    high_impact_failures = [
        item for item in memory_signals
        if item.get("type") == "failure" and float(item.get("impact_score") or 0.0) >= 1.0
    ]
    high_impact_successes = [
        item for item in memory_signals
        if item.get("type") == "success" and float(item.get("impact_score") or 0.0) >= 1.0
    ]
    repeated_failure_pattern = any(
        pattern.get("failure_events", 0) >= 2 or pattern.get("repeated_failure")
        for pattern in ripple_patterns
    )

    priority = (
        importance * 0.35
        + goal_alignment * 0.20
        + min(1.0, len(high_impact_successes) / 3.0) * 0.20
        + (1.0 - min(1.0, execution_load)) * 0.10
        + (0.15 if health_status == "healthy" else 0.05 if health_status == "degraded" else 0.0)
    )
    priority -= min(0.30, failure_count * 0.06)
    priority -= min(0.20, len(high_impact_failures) * 0.08)
    if repeated_failure_pattern:
        priority -= 0.10
    if failure_rate >= 0.30:
        priority -= 0.10
    priority = max(0.0, min(1.0, round(priority, 4)))

    if health_status == "critical" and importance < 0.9:
        return _decision("defer", priority, "system health is critical; deferring non-essential trigger")
    if execution_load >= 0.85 and priority < 0.75:
        return _decision("defer", priority, "system load is high; deferring lower-priority execution")
    if repeated_failure_pattern and trigger_type in {"schedule", "watcher", "system"} and priority < 0.8:
        return _decision("defer", priority, "recent ripple patterns show repeated failures for similar work")
    if trigger_type == "watcher" and priority < 0.35:
        return _decision("ignore", priority, "watcher trigger is low-importance under current conditions")
    if trigger_type == "system" and failure_rate >= 0.35 and success_count == 0 and priority < 0.5:
        return _decision("ignore", priority, "system trigger is low-value during a failure-heavy period")
    return _decision("execute", priority, "trigger is safe and valuable to execute now")


def _enrich_context(*, trigger: dict[str, Any], trigger_type: str, context: dict[str, Any]) -> dict[str, Any]:
    db = context.get("db")
    user_id = context.get("user_id")
    if db is None:
        return context

    enriched = dict(context)
    enriched["system_state"] = enriched.get("system_state") or compute_current_state(db)
    enriched["memory_signals"] = enriched.get("memory_signals") or get_relevant_memories(
        {
            "user_id": normalize_uuid(user_id) if user_id is not None else None,
            "trigger_event": trigger.get("source") or trigger_type,
            "goal": trigger.get("goal") or "",
            "current_state": trigger.get("source") or "autonomy_controller",
            "constraints": [],
        },
        db=db,
    )
    enriched["ripple_patterns"] = enriched.get("ripple_patterns") or get_recent_ripple_patterns(db, user_id=user_id)
    rank_goals = get_job("goals.rank")
    enriched["goals"] = enriched.get("goals") or (
        rank_goals(db, str(user_id) if user_id is not None else None, system_state=enriched.get("system_state"))
        if rank_goals
        else []
    )
    if "goal_alignment" not in enriched:
        calculate_goal_alignment = get_job("goals.calculate_alignment")
        enriched["goal_alignment"] = (
            calculate_goal_alignment(
                enriched.get("goals") or [],
                trigger.get("goal") or trigger.get("task_name") or trigger.get("source"),
            )
            if calculate_goal_alignment
            else _default_goal_alignment(trigger_type)
        )
    enriched["execution_load"] = enriched.get("execution_load")
    return enriched


def get_recent_ripple_patterns(db, *, user_id: str | uuid.UUID | None = None, limit: int = 6) -> list[dict[str, Any]]:
    window_start = datetime.now(timezone.utc) - timedelta(hours=3)
    query = (
        db.query(SystemEvent)
        .filter(SystemEvent.timestamp >= window_start, SystemEvent.trace_id.isnot(None))
        .order_by(SystemEvent.timestamp.desc())
    )
    if user_id is not None:
        query = query.filter(SystemEvent.user_id == normalize_uuid(user_id))

    events = query.limit(100).all()
    grouped: dict[str, list[SystemEvent]] = {}
    for event in events:
        grouped.setdefault(str(event.trace_id), []).append(event)

    patterns: list[dict[str, Any]] = []
    for trace_id, trace_events in list(grouped.items())[:limit]:
        failure_events = [
            event for event in trace_events
            if ".failed" in event.type or event.type.startswith("error.")
        ]
        patterns.append(
            {
                "trace_id": trace_id,
                "event_count": len(trace_events),
                "failure_events": len(failure_events),
                "repeated_failure": len(failure_events) >= 2,
                "dominant_type": trace_events[0].type if trace_events else None,
            }
        )
    return patterns


def _decision(kind: str, priority: float, reason: str) -> dict[str, Any]:
    return {
        "decision": kind,
        "priority": round(priority, 4),
        "reason": reason,
        "defer_seconds": DEFAULT_DEFER_SECONDS if kind == "defer" else 0,
    }


def _default_importance(trigger_type: str) -> float:
    return {
        "user": 0.95,
        "system": 0.65,
        "schedule": 0.55,
        "watcher": 0.40,
    }.get(trigger_type, 0.50)


def _default_goal_alignment(trigger_type: str) -> float:
    return {
        "user": 0.90,
        "system": 0.65,
        "schedule": 0.55,
        "watcher": 0.45,
    }.get(trigger_type, 0.50)


def register() -> None:
    register_trigger_evaluator("default", evaluate_autonomy_trigger)
