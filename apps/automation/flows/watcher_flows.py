import logging

from AINDY.runtime.flow_engine import FLOW_REGISTRY, register_flow
from AINDY.runtime.flow_helpers import (
    register_nodes,
    register_single_node_flows,
)

logger = logging.getLogger(__name__)


# -- Node functions -----------------------------------------------------------

def watcher_signals_list_node(state, context):
    try:
        from uuid import UUID
        from AINDY.db.models.watcher_signal import WatcherSignal

        db = context.get("db")
        session_id = state.get("session_id")
        signal_type = state.get("signal_type")
        user_id_filter = state.get("user_id_filter")
        limit = state.get("limit", 50)
        offset_val = state.get("offset", 0)

        q = db.query(WatcherSignal)
        if session_id:
            q = q.filter(WatcherSignal.session_id == session_id)
        if user_id_filter:
            q = q.filter(WatcherSignal.user_id == UUID(str(user_id_filter)))
        if signal_type:
            q = q.filter(WatcherSignal.signal_type == signal_type)

        signals = q.order_by(WatcherSignal.signal_timestamp.desc()).offset(offset_val).limit(limit).all()
        data = [
            {
                "id": s.id,
                "signal_type": s.signal_type,
                "session_id": s.session_id,
                "app_name": s.app_name,
                "window_title": s.window_title,
                "activity_type": s.activity_type,
                "signal_timestamp": s.signal_timestamp.isoformat(),
                "received_at": s.received_at.isoformat(),
                "duration_seconds": s.duration_seconds,
                "focus_score": s.focus_score,
                "metadata": s.signal_metadata,
            }
            for s in signals
        ]
        return {"status": "SUCCESS", "output_patch": {"watcher_signals_list_result": data}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}

def watcher_evaluate_trigger_node(state, context):
    try:
        from AINDY.agents.autonomous_controller import evaluate_live_trigger

        db = context.get("db")
        user_id = state.get("user_id")
        trigger_context = {"goal": "watcher_ingest", "importance": 0.40, "goal_alignment": 0.45}
        evaluation = evaluate_live_trigger(db=db, trigger={"trigger_type": "watcher", "source": "watcher_router", "goal": "watcher_ingest"}, user_id=user_id, context=trigger_context)
        return {"status": "SUCCESS", "output_patch": {"watcher_evaluation": evaluation, "watcher_trigger_context": trigger_context, "watcher_decision": evaluation.get("decision", "ignore")}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}

def watcher_record_decision_node(state, context):
    try:
        from AINDY.platform_layer.trace_context import ensure_trace_id
        from AINDY.agents.autonomous_controller import record_decision

        db = context.get("db")
        user_id = state.get("user_id")
        evaluation = state.get("watcher_evaluation") or {}
        trigger_context = state.get("watcher_trigger_context") or {}
        trace_id = str(ensure_trace_id())
        record_decision(db=db, trigger={"trigger_type": "watcher", "source": "watcher_router", "goal": "watcher_ingest"}, evaluation=evaluation, user_id=user_id, trace_id=trace_id, context=trigger_context)
        return {"status": "SUCCESS", "output_patch": {"watcher_trace_id": trace_id}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}

def watcher_defer_job_node(state, context):
    try:
        from AINDY.platform_layer.async_job_service import build_deferred_response, defer_async_job

        user_id = state.get("user_id")
        evaluation = state.get("watcher_evaluation") or {}
        trigger_context = state.get("watcher_trigger_context") or {}
        signals = state.get("signals") or []
        log_id = defer_async_job(
            task_name="watcher.ingest",
            payload={"signals": signals, "user_id": user_id, "__autonomy": {"trigger_type": "watcher", "source": "watcher_router", "context": trigger_context}},
            user_id=user_id,
            source="watcher_router",
            decision=evaluation,
        )
        result = build_deferred_response(log_id, task_name="watcher.ingest", source="watcher_router", decision=evaluation)
        return {"status": "SUCCESS", "output_patch": {"watcher_evaluate_trigger_result": result}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}

def watcher_ignore_node(state, context):
    try:
        from AINDY.agents.autonomous_controller import build_decision_response

        evaluation = state.get("watcher_evaluation") or {}
        trace_id = state.get("watcher_trace_id") or ""
        result = build_decision_response(evaluation, trace_id=trace_id, result={"accepted": 0, "session_ended_count": 0, "orchestration": None})
        return {"status": "SUCCESS", "output_patch": {"watcher_evaluate_trigger_result": result}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}

def watcher_execute_wrap_node(state, context):
    ingest = state.get("watcher_ingest_result") or {}
    result = {"accepted": int(ingest.get("accepted") or 0), "session_ended_count": int(ingest.get("session_ended_count") or 0), "orchestration": ingest.get("orchestration")}
    return {"status": "SUCCESS", "output_patch": {"watcher_evaluate_trigger_result": result}}


# -- Registration -------------------------------------------------------------

def register() -> None:
    register_nodes(
        {
            "watcher_signals_list_node": watcher_signals_list_node,
            "watcher_evaluate_trigger_node": watcher_evaluate_trigger_node,
            "watcher_record_decision_node": watcher_record_decision_node,
            "watcher_defer_job_node": watcher_defer_job_node,
            "watcher_ignore_node": watcher_ignore_node,
            "watcher_execute_wrap_node": watcher_execute_wrap_node,
        }
    )
    register_single_node_flows(
        {
            "watcher_signals_list": "watcher_signals_list_node",
        }
    )

    if "watcher_signals_receive" not in FLOW_REGISTRY:
        register_flow(
            "watcher_signals_receive",
            {
                "start": "watcher_ingest_validate",
                "edges": {
                    "watcher_ingest_validate": ["watcher_ingest_persist"],
                    "watcher_ingest_persist": ["watcher_ingest_orchestrate"],
                },
                "end": ["watcher_ingest_orchestrate"],
            },
        )

    if "watcher_evaluate_trigger" not in FLOW_REGISTRY:
        register_flow(
            "watcher_evaluate_trigger",
            {
                "start": "watcher_evaluate_trigger_node",
                "edges": {
                    "watcher_evaluate_trigger_node": ["watcher_record_decision_node"],
                    "watcher_record_decision_node": [
                        {
                            "condition": lambda s: s.get("watcher_decision") == "execute",
                            "target": "watcher_ingest_validate",
                        },
                        {
                            "condition": lambda s: s.get("watcher_decision") == "defer",
                            "target": "watcher_defer_job_node",
                        },
                        {
                            "condition": lambda s: True,
                            "target": "watcher_ignore_node",
                        },
                    ],
                    "watcher_ingest_validate": ["watcher_ingest_persist"],
                    "watcher_ingest_persist": ["watcher_ingest_orchestrate"],
                    "watcher_ingest_orchestrate": ["watcher_execute_wrap_node"],
                },
                "end": [
                    "watcher_execute_wrap_node",
                    "watcher_defer_job_node",
                    "watcher_ignore_node",
                ],
            },
        )
