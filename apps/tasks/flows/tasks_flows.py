from AINDY.runtime.flow_engine import FLOW_REGISTRY, register_flow
from AINDY.runtime.flow_helpers import register_nodes, register_single_node_flows


def _syscall_node(name: str, state: dict, context: dict, capability: str) -> dict:
    from AINDY.kernel.syscall_dispatcher import get_dispatcher, make_syscall_ctx_from_flow

    ctx = make_syscall_ctx_from_flow(context, capabilities=[capability])
    result = get_dispatcher().dispatch(name, state, ctx)
    if result["status"] == "error":
        return {"status": "RETRY", "error": result["error"]}
    return {"status": "SUCCESS", "output_patch": result["data"]}


def tasks_list_node(state, context):
    try:
        import uuid
        from apps.tasks.models import Task

        db = context.get("db")
        user_id = uuid.UUID(str(context.get("user_id")))
        tasks = db.query(Task).filter(Task.user_id == user_id).all()
        data = [
            {
                "task_id": t.id,
                "task_name": t.name,
                "category": t.category,
                "priority": t.priority,
                "status": getattr(t, "status", "unknown"),
                "time_spent": t.time_spent,
                "masterplan_id": getattr(t, "masterplan_id", None),
                "parent_task_id": getattr(t, "parent_task_id", None),
                "depends_on": getattr(t, "depends_on", []) or [],
                "dependency_type": getattr(t, "dependency_type", "hard"),
                "automation_type": getattr(t, "automation_type", None),
                "automation_config": getattr(t, "automation_config", None),
            }
            for t in tasks
        ]
        return {"status": "SUCCESS", "output_patch": {"tasks_list_result": data}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def tasks_recurrence_check_node(state, context):
    try:
        import threading
        from apps.tasks.services.task_service import handle_recurrence

        t = threading.Thread(target=handle_recurrence, daemon=True)
        t.start()
        return {"status": "SUCCESS", "output_patch": {"tasks_recurrence_check_result": {
            "message": "Recurrence job started in background."
        }}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def task_create_validate(state, context):
    if not state.get("task_name"):
        return {"status": "FAILURE", "error": "task_name required"}
    return {"status": "SUCCESS", "output_patch": {"validated": True}}


def task_create_execute(state, context):
    return _syscall_node("sys.v1.task.create", state, context, "task.create")


def task_validate(state, context):
    if not state.get("task_name"):
        return {"status": "FAILURE", "error": "task_name required"}
    return {"status": "SUCCESS", "output_patch": {"validated": True}}


def task_complete(state, context):
    return _syscall_node("sys.v1.task.complete", state, context, "task.complete")


def task_orchestrate(state, context):
    result = _syscall_node("sys.v1.task.orchestrate", state, context, "task.orchestrate")
    if result.get("status") == "RETRY":
        return {"status": "FAILURE", "error": result.get("error", "")}
    return result


def task_start_execute(state, context):
    return _syscall_node("sys.v1.task.start", state, context, "task.start")


def task_pause_execute(state, context):
    return _syscall_node("sys.v1.task.pause", state, context, "task.pause")


def watcher_ingest_validate(state, context):
    signals = state.get("signals") or []
    if not isinstance(signals, list) or not signals:
        return {"status": "FAILURE", "error": "signals are required"}
    return {"status": "SUCCESS", "output_patch": {"validated": True}}


def watcher_ingest_persist(state, context):
    return _syscall_node("sys.v1.watcher.ingest", state, context, "watcher.ingest")


def watcher_ingest_orchestrate(state, context):
    try:
        from uuid import UUID

        from AINDY.core.system_event_service import emit_system_event
        from AINDY.platform_layer.registry import get_job

        db = context.get("db")
        session_ended_count = state.get("watcher_session_ended_count") or 0
        batch_user_id = state.get("watcher_batch_user_id")

        eta_recalculated = False
        score_orchestrated = False
        next_action = None

        if session_ended_count > 0:
            event_user_id = UUID(str(batch_user_id)) if batch_user_id else None
            signals = state.get("signals") or []
            ended_signals = [
                signal
                for signal in signals
                if isinstance(signal, dict)
                and signal.get("signal_type") == "session_ended"
            ]
            event_payload = {
                "session_ended_count": session_ended_count,
                "signals": ended_signals,
            }
            if len(ended_signals) == 1:
                signal = ended_signals[0]
                metadata = signal.get("metadata") or {}
                event_payload.update(
                    {
                        "session_duration": metadata.get("session_duration")
                        or metadata.get("duration_seconds"),
                        "focus_score": metadata.get("focus_score"),
                        "session_id": signal.get("session_id"),
                        "activity_type": signal.get("activity_type"),
                    }
                )
            emit_system_event(
                db=db,
                event_type="watcher.session_ended",
                user_id=event_user_id,
                source="watcher_ingest",
                payload=event_payload,
                required=True,
                skip_memory_capture=True,
            )
            eta_recalculated = True
            if batch_user_id:
                execute_infinity_orchestrator = get_job("analytics.infinity_execute")
                if execute_infinity_orchestrator is None:
                    raise RuntimeError("analytics.infinity_execute job is not registered")
                orchestration = execute_infinity_orchestrator(
                    user_id=event_user_id,
                    db=db,
                    trigger_event="session_ended",
                )
                score_orchestrated = True
                next_action = orchestration["next_action"]

        result = dict(state.get("watcher_ingest_result") or {})
        result["orchestration"] = {
            "eta_recalculated": eta_recalculated,
            "score_orchestrated": score_orchestrated,
            "next_action": next_action,
        }
        return {"status": "SUCCESS", "output_patch": {"watcher_ingest_result": result}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


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
        evaluation = evaluate_live_trigger(
            db=db,
            trigger={"trigger_type": "watcher", "source": "watcher_router", "goal": "watcher_ingest"},
            user_id=user_id,
            context=trigger_context,
        )
        return {
            "status": "SUCCESS",
            "output_patch": {
                "watcher_evaluation": evaluation,
                "watcher_trigger_context": trigger_context,
                "watcher_decision": evaluation.get("decision", "ignore"),
            },
        }
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
        record_decision(
            db=db,
            trigger={"trigger_type": "watcher", "source": "watcher_router", "goal": "watcher_ingest"},
            evaluation=evaluation,
            user_id=user_id,
            trace_id=trace_id,
            context=trigger_context,
        )
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
            payload={
                "signals": signals,
                "user_id": user_id,
                "__autonomy": {
                    "trigger_type": "watcher",
                    "source": "watcher_router",
                    "context": trigger_context,
                },
            },
            user_id=user_id,
            source="watcher_router",
            decision=evaluation,
        )
        result = build_deferred_response(
            log_id,
            task_name="watcher.ingest",
            source="watcher_router",
            decision=evaluation,
        )
        return {"status": "SUCCESS", "output_patch": {"watcher_evaluate_trigger_result": result}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def watcher_ignore_node(state, context):
    try:
        from AINDY.agents.autonomous_controller import build_decision_response

        evaluation = state.get("watcher_evaluation") or {}
        trace_id = state.get("watcher_trace_id") or ""
        result = build_decision_response(
            evaluation,
            trace_id=trace_id,
            result={"accepted": 0, "session_ended_count": 0, "orchestration": None},
        )
        return {"status": "SUCCESS", "output_patch": {"watcher_evaluate_trigger_result": result}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def watcher_execute_wrap_node(state, context):
    ingest = state.get("watcher_ingest_result") or {}
    result = {
        "accepted": int(ingest.get("accepted") or 0),
        "session_ended_count": int(ingest.get("session_ended_count") or 0),
        "orchestration": ingest.get("orchestration"),
    }
    return {"status": "SUCCESS", "output_patch": {"watcher_evaluate_trigger_result": result}}


def register() -> None:
    register_nodes(
        {
            "tasks_list_node": tasks_list_node,
            "tasks_recurrence_check_node": tasks_recurrence_check_node,
            "task_create_validate": task_create_validate,
            "task_create_execute": task_create_execute,
            "task_validate": task_validate,
            "task_complete": task_complete,
            "task_orchestrate": task_orchestrate,
            "task_start_execute": task_start_execute,
            "task_pause_execute": task_pause_execute,
            "watcher_ingest_validate": watcher_ingest_validate,
            "watcher_ingest_persist": watcher_ingest_persist,
            "watcher_ingest_orchestrate": watcher_ingest_orchestrate,
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
            "tasks_list": "tasks_list_node",
            "tasks_recurrence_check": "tasks_recurrence_check_node",
            "watcher_signals_list": "watcher_signals_list_node",
        }
    )

    if "task_create" not in FLOW_REGISTRY:
        register_flow(
            "task_create",
            {
                "start": "task_create_validate",
                "edges": {
                    "task_create_validate": ["task_create_execute"],
                },
                "end": ["task_create_execute"],
            },
        )

    if "task_start" not in FLOW_REGISTRY:
        register_flow(
            "task_start",
            {
                "start": "task_start_execute",
                "edges": {},
                "end": ["task_start_execute"],
            },
        )

    if "task_pause" not in FLOW_REGISTRY:
        register_flow(
            "task_pause",
            {
                "start": "task_pause_execute",
                "edges": {},
                "end": ["task_pause_execute"],
            },
        )

    if "task_completion" not in FLOW_REGISTRY:
        register_flow(
            "task_completion",
            {
                "start": "task_validate",
                "edges": {
                    "task_validate": ["task_complete"],
                    "task_complete": ["task_orchestrate"],
                },
                "end": ["task_orchestrate"],
            },
        )

    if "watcher_ingest" not in FLOW_REGISTRY:
        register_flow(
            "watcher_ingest",
            {
                "start": "watcher_ingest_validate",
                "edges": {
                    "watcher_ingest_validate": ["watcher_ingest_persist"],
                    "watcher_ingest_persist": ["watcher_ingest_orchestrate"],
                },
                "end": ["watcher_ingest_orchestrate"],
            },
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
