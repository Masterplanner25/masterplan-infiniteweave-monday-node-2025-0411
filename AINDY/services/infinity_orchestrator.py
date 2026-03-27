"""
Infinity orchestrator.

System invariant:
  every score update must flow through this service and produce
  a persisted LoopAdjustment with a non-empty next_action.
"""
from __future__ import annotations

from services.infinity_loop import run_loop, serialize_adjustment
from services.infinity_service import calculate_infinity_score, orchestrator_score_context
from services.system_event_service import emit_system_event
from utils.trace_context import get_current_trace_id


def execute(user_id: str, trigger_event: str, db):
    trace_id = get_current_trace_id() or f"loop:{trigger_event}"
    emit_system_event(
        db=db,
        event_type="loop.started",
        user_id=user_id,
        trace_id=trace_id,
        payload={"trigger_event": trigger_event},
        required=True,
    )
    with orchestrator_score_context():
        score = calculate_infinity_score(
            user_id=user_id,
            db=db,
            trigger_event=trigger_event,
        )

    if not score:
        raise RuntimeError("Infinity orchestrator failed to recalculate score")

    score_snapshot = {
        "master_score": score.get("master_score"),
        "execution_speed": score.get("kpis", {}).get("execution_speed"),
        "decision_efficiency": score.get("kpis", {}).get("decision_efficiency"),
        "ai_productivity_boost": score.get("kpis", {}).get("ai_productivity_boost"),
        "focus_quality": score.get("kpis", {}).get("focus_quality"),
        "masterplan_progress": score.get("kpis", {}).get("masterplan_progress"),
        "confidence": score.get("metadata", {}).get("confidence"),
    }
    adjustment = run_loop(
        user_id=user_id,
        trigger_event=trigger_event,
        db=db,
        score_snapshot=score_snapshot,
    )
    if not adjustment:
        raise RuntimeError("Infinity orchestrator failed to create loop adjustment")

    serialized = serialize_adjustment(adjustment)
    if not serialized:
        raise RuntimeError("Infinity orchestrator failed to serialize loop adjustment")

    next_action = (serialized.get("adjustment_payload") or {}).get("next_action")
    if not next_action:
        raise RuntimeError("Infinity loop invariant violated: next_action is empty")

    emit_system_event(
        db=db,
        event_type="loop.decision",
        user_id=user_id,
        trace_id=serialized.get("trace_id") or trace_id,
        payload={
            "trigger_event": trigger_event,
            "adjustment_id": serialized.get("id"),
            "next_action": next_action,
            "adjustment": serialized,
        },
        required=True,
    )

    return {
        "score": score,
        "adjustment": serialized,
        "next_action": next_action,
    }
