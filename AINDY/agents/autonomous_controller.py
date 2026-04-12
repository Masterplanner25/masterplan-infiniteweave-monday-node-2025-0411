from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from AINDY.db.models.agent_run import AgentRun
from AINDY.db.models.autonomy_decision import AutonomyDecision
from AINDY.db.models.flow_run import FlowRun
from AINDY.db.models.system_event import SystemEvent
from AINDY.core.execution_signal_helper import queue_system_event
from AINDY.core.execution_envelope import success
from AINDY.domain.goal_service import calculate_goal_alignment
from AINDY.domain.goal_service import rank_goals
from AINDY.memory.memory_scoring_service import get_relevant_memories
from AINDY.core.system_event_types import SystemEventTypes
from AINDY.platform_layer.system_state_service import compute_current_state
from AINDY.utils.uuid_utils import normalize_uuid


DEFAULT_DEFER_SECONDS = 300


def evaluate_trigger(trigger: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    trigger_type = str(trigger.get("trigger_type") or "system").lower()
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
        return _decision(
            "defer",
            priority,
            "system health is critical; deferring non-essential trigger",
        )
    if execution_load >= 0.85 and priority < 0.75:
        return _decision(
            "defer",
            priority,
            "system load is high; deferring lower-priority execution",
        )
    if repeated_failure_pattern and trigger_type in {"schedule", "watcher", "system"} and priority < 0.8:
        return _decision(
            "defer",
            priority,
            "recent ripple patterns show repeated failures for similar work",
        )
    if trigger_type == "watcher" and priority < 0.35:
        return _decision(
            "ignore",
            priority,
            "watcher trigger is low-importance under current conditions",
        )
    if trigger_type == "system" and failure_rate >= 0.35 and success_count == 0 and priority < 0.5:
        return _decision(
            "ignore",
            priority,
            "system trigger is low-value during a failure-heavy period",
        )
    return _decision("execute", priority, "trigger is safe and valuable to execute now")


def evaluate_live_trigger(
    *,
    db,
    trigger: dict[str, Any],
    user_id: str | uuid.UUID | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    merged_context = dict(context or {})
    merged_context["system_state"] = merged_context.get("system_state") or compute_current_state(db)
    merged_context["memory_signals"] = merged_context.get("memory_signals") or get_relevant_memories(
        {
            "user_id": normalize_uuid(user_id) if user_id is not None else None,
            "trigger_event": trigger.get("source") or trigger.get("trigger_type"),
            "goal": trigger.get("goal") or "",
            "current_state": trigger.get("source") or "autonomy_controller",
            "constraints": [],
        },
        db=db,
    )
    merged_context["ripple_patterns"] = merged_context.get("ripple_patterns") or get_recent_ripple_patterns(
        db,
        user_id=user_id,
    )
    merged_context["goals"] = merged_context.get("goals") or rank_goals(
        db,
        str(user_id) if user_id is not None else None,
        system_state=merged_context.get("system_state"),
    )
    if "goal_alignment" not in merged_context:
        merged_context["goal_alignment"] = calculate_goal_alignment(
            merged_context.get("goals") or [],
            trigger.get("goal") or trigger.get("task_name") or trigger.get("source"),
        )
    merged_context["execution_load"] = merged_context.get("execution_load")
    return evaluate_trigger(trigger, merged_context)


def record_decision(
    *,
    db,
    trigger: dict[str, Any],
    evaluation: dict[str, Any],
    user_id: str | uuid.UUID | None = None,
    trace_id: str | None = None,
    automation_log_id: str | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    decision = AutonomyDecision(
        user_id=normalize_uuid(user_id) if user_id is not None else None,
        trigger_type=str(trigger.get("trigger_type") or "system"),
        trigger_source=str(trigger.get("source") or trigger.get("task_name") or "") or None,
        decision=str(evaluation.get("decision") or "defer"),
        priority=float(evaluation.get("priority") or 0.0),
        reason=str(evaluation.get("reason") or "no reason provided"),
        trace_id=trace_id,
        automation_log_id=automation_log_id,
        trigger_payload=_json_safe(trigger),
        context_summary=_summarize_context(context or {}),
    )
    db.add(decision)
    db.commit()
    db.refresh(decision)
    queue_system_event(
        db=db,
        event_type=SystemEventTypes.AUTONOMY_DECISION,
        user_id=user_id,
        trace_id=trace_id,
        source="autonomy",
        payload={
            "decision_id": str(decision.id),
            "trigger_type": decision.trigger_type,
            "trigger_source": decision.trigger_source,
            "decision": decision.decision,
            "priority": decision.priority,
            "reason": decision.reason,
            "automation_log_id": automation_log_id,
        },
        required=True,
    )
    return serialize_decision(decision)


def list_recent_decisions(db, *, user_id: str | uuid.UUID | None = None, limit: int = 50) -> list[dict[str, Any]]:
    query = db.query(AutonomyDecision)
    if user_id is not None:
        query = query.filter(AutonomyDecision.user_id == normalize_uuid(user_id))
    rows = query.order_by(AutonomyDecision.created_at.desc()).limit(limit).all()
    return [serialize_decision(row) for row in rows]


def build_decision_response(
    evaluation: dict[str, Any],
    *,
    trace_id: str,
    result: dict[str, Any] | None = None,
    next_action: Any = None,
) -> dict[str, Any]:
    response = success(
        result=result or {
            "decision": evaluation.get("decision"),
            "priority": evaluation.get("priority"),
            "reason": evaluation.get("reason"),
        },
        events=[],
        trace_id=trace_id,
        next_action=next_action,
    )
    decision = str(evaluation.get("decision") or "success").lower()
    response["status"] = {
        "execute": "EXECUTE",
        "defer": "DEFERRED",
        "ignore": "IGNORED",
    }.get(decision, decision.upper())
    return response


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


def count_active_executions(db, *, user_id: str | uuid.UUID | None = None) -> int:
    flow_query = db.query(FlowRun).filter(FlowRun.status.in_(("running", "waiting")))
    agent_query = db.query(AgentRun).filter(AgentRun.status.in_(("approved", "executing", "pending_approval")))
    if user_id is not None:
        normalized = normalize_uuid(user_id)
        flow_query = flow_query.filter(FlowRun.user_id == normalized)
        agent_query = agent_query.filter(AgentRun.user_id == normalized)
    return flow_query.count() + agent_query.count()


def serialize_decision(row: AutonomyDecision) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "user_id": str(row.user_id) if row.user_id else None,
        "trigger_type": row.trigger_type,
        "trigger_source": row.trigger_source,
        "decision": row.decision,
        "priority": row.priority,
        "reason": row.reason,
        "trace_id": row.trace_id,
        "automation_log_id": row.automation_log_id,
        "trigger_payload": row.trigger_payload or {},
        "context_summary": row.context_summary or {},
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


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


def _json_safe(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def _summarize_context(context: dict[str, Any]) -> dict[str, Any]:
    system_state = context.get("system_state") or {}
    memory_signals = context.get("memory_signals") or []
    ripple_patterns = context.get("ripple_patterns") or []
    goals = context.get("goals") or []
    return {
        "health_status": system_state.get("health_status"),
        "failure_rate": system_state.get("failure_rate"),
        "system_load": system_state.get("system_load"),
        "memory_signal_count": len(memory_signals),
        "failure_signal_count": sum(1 for item in memory_signals if item.get("type") == "failure"),
        "success_signal_count": sum(1 for item in memory_signals if item.get("type") == "success"),
        "ripple_pattern_count": len(ripple_patterns),
        "goal_count": len(goals),
        "goal_alignment": context.get("goal_alignment"),
    }


