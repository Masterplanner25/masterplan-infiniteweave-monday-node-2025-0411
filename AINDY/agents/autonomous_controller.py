from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from AINDY.db.models.flow_run import FlowRun
from AINDY.core.execution_signal_helper import queue_system_event
from AINDY.core.execution_envelope import success
from AINDY.core.system_event_types import SystemEventTypes
from AINDY.platform_layer.registry import get_symbol, get_trigger_evaluator
from AINDY.utils.uuid_utils import normalize_uuid


DEFAULT_DEFER_SECONDS = 300


def _autonomy_decision_model():
    model = get_symbol("AutonomyDecision")
    if model is None:
        raise RuntimeError("AutonomyDecision model not registered")
    return model


def evaluate_trigger(trigger: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    trigger_type = str(trigger.get("trigger_type") or "system").lower()
    evaluator = get_trigger_evaluator(trigger_type)
    if evaluator is None:
        return _decision("defer", 0.0, "no trigger evaluator registered")
    try:
        result = evaluator({"trigger_type": trigger_type, "trigger": trigger, "context": dict(context or {})})
    except Exception:
        return _decision("defer", 0.0, "trigger evaluator failed")
    return _normalize_evaluation(result)


def evaluate_live_trigger(
    *,
    db,
    trigger: dict[str, Any],
    user_id: str | uuid.UUID | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    merged_context = dict(context or {})
    merged_context["db"] = db
    merged_context["user_id"] = str(user_id) if user_id is not None else None
    return evaluate_trigger(trigger, merged_context)


def record_decision(
    *,
    db,
    trigger: dict[str, Any],
    evaluation: dict[str, Any],
    user_id: str | uuid.UUID | None = None,
    trace_id: str | None = None,
    job_log_id: str | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    AutonomyDecision = _autonomy_decision_model()
    decision = AutonomyDecision(
        user_id=normalize_uuid(user_id) if user_id is not None else None,
        trigger_type=str(trigger.get("trigger_type") or "system"),
        trigger_source=str(trigger.get("source") or "") or None,
        decision=str(evaluation.get("decision") or "defer"),
        priority=float(evaluation.get("priority") or 0.0),
        reason=str(evaluation.get("reason") or "no reason provided"),
        trace_id=trace_id,
        job_log_id=job_log_id,
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
            "job_log_id": job_log_id,
        },
        required=True,
    )
    return serialize_decision(decision)


def list_recent_decisions(db, *, user_id: str | uuid.UUID | None = None, limit: int = 50) -> list[dict[str, Any]]:
    AutonomyDecision = _autonomy_decision_model()
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


def count_active_executions(db, *, user_id: str | uuid.UUID | None = None) -> int:
    from AINDY.db.models import AgentRun

    flow_query = db.query(FlowRun).filter(FlowRun.status.in_(("running", "waiting")))
    agent_query = db.query(AgentRun).filter(AgentRun.status.in_(("approved", "executing", "pending_approval")))
    if user_id is not None:
        normalized = normalize_uuid(user_id)
        flow_query = flow_query.filter(FlowRun.user_id == normalized)
        agent_query = agent_query.filter(AgentRun.user_id == normalized)
    return flow_query.count() + agent_query.count()


def serialize_decision(row: Any) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "user_id": str(row.user_id) if row.user_id else None,
        "trigger_type": row.trigger_type,
        "trigger_source": row.trigger_source,
        "decision": row.decision,
        "priority": row.priority,
        "reason": row.reason,
        "trace_id": row.trace_id,
        "job_log_id": row.job_log_id,
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


def _normalize_evaluation(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return _decision("defer", 0.0, "trigger evaluator returned invalid result")
    decision = str(value.get("decision") or "defer").lower()
    if decision not in {"execute", "defer", "ignore"}:
        decision = "defer"
    try:
        priority = float(value.get("priority") or 0.0)
    except (TypeError, ValueError):
        priority = 0.0
    return _decision(
        decision,
        max(0.0, min(1.0, priority)),
        str(value.get("reason") or "trigger evaluator returned no reason"),
    )


def _json_safe(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def _summarize_context(context: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for key, value in context.items():
        if key == "db":
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            summary[str(key)] = value
        elif isinstance(value, (list, tuple, set)):
            summary[f"{key}_count"] = len(value)
        elif isinstance(value, dict):
            summary[f"{key}_keys"] = sorted(str(item) for item in value.keys())[:20]
    return summary


