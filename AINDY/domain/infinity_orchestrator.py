"""
Infinity orchestrator.

System invariant:
  every score update must flow through this service and produce
  a persisted LoopAdjustment with a non-empty next_action.
"""
from __future__ import annotations

import logging

from AINDY.core.execution_signal_helper import queue_system_event
emit_system_event = queue_system_event
from AINDY.domain.identity_boot_service import get_recent_memory, get_user_metrics
from AINDY.domain.goal_service import rank_goals
from AINDY.domain.infinity_loop import evaluate_pending_adjustment, run_loop, serialize_adjustment
from AINDY.domain.infinity_service import calculate_infinity_score, orchestrator_score_context
from AINDY.memory.memory_scoring_service import get_relevant_memories
from AINDY.domain.social_performance_service import get_social_performance_signals
from AINDY.platform_layer.system_state_service import compute_current_state
from AINDY.domain.task_services import get_task_graph_context
from AINDY.utils.trace_context import get_current_trace_id

logger = logging.getLogger(__name__)


def execute(user_id: str, trigger_event: str, db):
    trace_id = get_current_trace_id() or f"loop:{trigger_event}"
    memory_nodes = get_recent_memory(user_id, db, context="infinity_loop")
    metrics = get_user_metrics(user_id, db)
    memory_signals = get_relevant_memories(
        {
            "user_id": user_id,
            "trigger_event": trigger_event,
            "current_state": "infinity_loop",
            "goal": "select next_action",
            "constraints": [],
        },
        db=db,
    )
    try:
        system_state = compute_current_state(db)
    except Exception as exc:
        logger.warning("[InfinityOrchestrator] system state lookup failed for %s: %s", user_id, exc)
        system_state = {}
    try:
        goals = rank_goals(db, user_id, system_state=system_state)
    except Exception as exc:
        logger.warning("[InfinityOrchestrator] goal ranking failed for %s: %s", user_id, exc)
        goals = []
    try:
        task_graph = get_task_graph_context(db, user_id)
    except Exception as exc:
        logger.warning("[InfinityOrchestrator] task graph lookup failed for %s: %s", user_id, exc)
        task_graph = {}
    try:
        social_signals = get_social_performance_signals(user_id=str(user_id))
    except Exception as exc:
        logger.warning("[InfinityOrchestrator] social signal lookup failed for %s: %s", user_id, exc)
        social_signals = []
    loop_context = {
        "user_id": str(user_id),
        "memory": memory_nodes,
        "metrics": metrics,
        "memory_signals": memory_signals,
        "system_state": system_state,
        "goals": goals,
        "task_graph": task_graph,
        "social_signals": social_signals,
    }
    emit_system_event(
        db=db,
        event_type="loop.started",
        user_id=user_id,
        trace_id=trace_id,
        payload={
            "trigger_event": trigger_event,
            "loop_context": {
                "user_id": str(user_id),
                "memory_count": len(memory_nodes),
                "memory_signal_count": len(memory_signals),
                "health_status": system_state.get("health_status"),
                "goal_count": len(goals),
                "ready_task_count": len(task_graph.get("ready") or []),
                "blocked_task_count": len(task_graph.get("blocked") or []),
                "social_signal_count": len(social_signals),
                "has_metrics": metrics is not None,
            },
        },
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
    prior_evaluation = evaluate_pending_adjustment(
        user_id=user_id,
        trigger_event=trigger_event,
        actual_score=score_snapshot.get("master_score"),
        db=db,
    )
    try:
        adjustment = run_loop(
            user_id=user_id,
            trigger_event=trigger_event,
            db=db,
            score_snapshot=score_snapshot,
            loop_context=loop_context,
        )
    except TypeError as exc:
        if "loop_context" not in str(exc):
            raise
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
            "memory_signals": memory_signals,
            "system_state": {
                "health_status": system_state.get("health_status"),
                "failure_rate": system_state.get("failure_rate"),
                "system_load": system_state.get("system_load"),
            },
            "goals": goals[:3],
            "social_signals": social_signals[:3],
            "task_graph": {
                "critical_path": task_graph.get("critical_path", [])[:5],
                "blocked": task_graph.get("blocked", [])[:5],
            },
            "prior_evaluation": prior_evaluation,
            "adjustment": serialized,
        },
        required=True,
    )

    adjustment_payload = serialized.get("adjustment_payload") or {}
    memory_summary = adjustment_payload.get("memory_summary") or {}
    memory_adjustment = adjustment_payload.get("memory_adjustment") or {}
    score_metadata = score.setdefault("metadata", {})
    score_metadata["memory_context_count"] = len(memory_nodes)
    score_metadata["memory_signal_count"] = len(memory_signals)
    score_metadata["memory_influence"] = {
        "memory_adjustment": memory_adjustment,
        "memory_summary": memory_summary,
    }

    return {
        "score": score,
        "prior_evaluation": prior_evaluation,
        "adjustment": serialized,
        "next_action": next_action,
        "memory_context_count": len(memory_nodes),
        "memory_signal_count": len(memory_signals),
        "memory_influence": {
            "memory_adjustment": memory_adjustment,
            "memory_summary": memory_summary,
        },
    }


