from AINDY.runtime.flow_engine import FLOW_REGISTRY, register_flow
from apps.automation.flows._flow_registration import register_nodes, register_single_node_flows


def agent_run_create_node(state, context):
    try:
        from AINDY.agents.agent_runtime import create_run, execute_run, to_execution_response
        from AINDY.agents.autonomous_controller import build_decision_response, evaluate_live_trigger, record_decision
        from AINDY.platform_layer.async_job_service import defer_async_job
        from AINDY.platform_layer.trace_context import ensure_trace_id
        from AINDY.utils.uuid_utils import normalize_uuid
        from AINDY.core.execution_dispatcher import async_heavy_execution_enabled
        from AINDY.platform_layer.async_job_service import submit_autonomous_async_job

        db = context.get("db")
        user_id = normalize_uuid(context.get("user_id"))
        goal = state.get("goal", "").strip()

        if async_heavy_execution_enabled():
            trigger_context = {"goal": goal, "importance": 0.95}
            response = submit_autonomous_async_job(
                task_name="agent.create_run",
                payload={"goal": goal, "user_id": str(user_id)},
                user_id=user_id,
                source="agent_router",
                trigger_type="user",
                trigger_context=trigger_context,
                db=db,
            )
            return {"status": "SUCCESS", "output_patch": {"agent_run_create_result": {"_http_status": 202, "_http_response": response}}}

        trace_id = ensure_trace_id()
        trigger_context = {"goal": goal, "importance": 0.95}
        trigger = {"trigger_type": "user", "source": "agent_router", "goal": goal}
        evaluation = evaluate_live_trigger(db=db, trigger=trigger, user_id=user_id, context=trigger_context)
        record_decision(db=db, trigger=trigger, evaluation=evaluation, user_id=user_id, trace_id=trace_id, context=trigger_context)

        if evaluation["decision"] == "ignore":
            return {"status": "SUCCESS", "output_patch": {"agent_run_create_result": {"_decision_response": build_decision_response(evaluation, trace_id=trace_id)}}}
        if evaluation["decision"] == "defer":
            log_id = defer_async_job(
                task_name="agent.create_run",
                payload={"goal": goal, "user_id": str(user_id), "__autonomy": {"trigger_type": "user", "source": "agent_router", "context": trigger_context}},
                user_id=user_id,
                source="agent_router",
                decision=evaluation,
            )
            return {"status": "SUCCESS", "output_patch": {"agent_run_create_result": {
                "_http_status": 202,
                "_http_response": build_decision_response(
                    evaluation,
                    trace_id=log_id,
                    result={"automation_log_id": log_id, "decision": "defer", "reason": evaluation["reason"]},
                    next_action={"type": "poll_automation_log", "automation_log_id": log_id},
                ),
            }}}

        run = create_run(goal=goal, user_id=user_id, db=db)
        if not run:
            return {"status": "FAILURE", "error": "HTTP_500:Failed to generate plan"}
        if run["status"] == "approved":
            run = execute_run(run_id=run["run_id"], user_id=user_id, db=db) or run
        return {"status": "SUCCESS", "output_patch": {"agent_run_create_result": to_execution_response(run, db)}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def agent_runs_list_node(state, context):
    try:
        from AINDY.db.models.agent_run import AgentRun
        from AINDY.agents.agent_runtime import run_to_dict
        from AINDY.utils.uuid_utils import normalize_uuid

        db = context.get("db")
        user_id = normalize_uuid(context.get("user_id"))
        status_filter = state.get("status")
        limit = state.get("limit", 20)
        query = db.query(AgentRun).filter(AgentRun.user_id == user_id)
        if status_filter:
            query = query.filter(AgentRun.status == status_filter)
        runs = query.order_by(AgentRun.created_at.desc()).limit(limit).all()
        rows = []
        for run in runs:
            row = run_to_dict(run)
            row["goal"] = row.get("objective")
            rows.append(row)
        return {"status": "SUCCESS", "output_patch": {"agent_runs_list_result": rows}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def agent_run_get_node(state, context):
    try:
        from AINDY.db.models.agent_run import AgentRun
        from AINDY.agents.agent_runtime import run_to_dict
        from AINDY.utils.uuid_utils import normalize_uuid

        db = context.get("db")
        user_id = normalize_uuid(context.get("user_id"))
        try:
            run_id = normalize_uuid(state.get("run_id"))
        except Exception:
            return {"status": "FAILURE", "error": "HTTP_400:Invalid run_id"}
        run = db.query(AgentRun).filter(AgentRun.id == run_id).first()
        if not run:
            return {"status": "FAILURE", "error": "HTTP_404:Run not found"}
        if run.user_id != user_id:
            return {"status": "FAILURE", "error": "HTTP_403:Not authorized"}
        row = run_to_dict(run)
        row["goal"] = row.get("objective")
        return {"status": "SUCCESS", "output_patch": {"agent_run_get_result": row}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def agent_run_approve_node(state, context):
    try:
        from AINDY.agents.agent_runtime import approve_run, to_execution_response
        from AINDY.agents.autonomous_controller import build_decision_response, evaluate_live_trigger, record_decision
        from AINDY.platform_layer.async_job_service import defer_async_job
        from AINDY.platform_layer.trace_context import ensure_trace_id
        from AINDY.utils.uuid_utils import normalize_uuid

        db = context.get("db")
        user_id = normalize_uuid(context.get("user_id"))
        run_id = state.get("run_id")

        trace_id = ensure_trace_id()
        trigger_context = {"goal": f"approve_run:{run_id}", "importance": 0.9}
        trigger = {"trigger_type": "user", "source": "agent_router.approve", "goal": f"approve_run:{run_id}"}
        evaluation = evaluate_live_trigger(db=db, trigger=trigger, user_id=user_id, context=trigger_context)
        record_decision(db=db, trigger=trigger, evaluation=evaluation, user_id=user_id, trace_id=trace_id, context=trigger_context)

        if evaluation["decision"] == "ignore":
            return {"status": "SUCCESS", "output_patch": {"agent_run_approve_result": {"_decision_response": build_decision_response(evaluation, trace_id=trace_id)}}}
        if evaluation["decision"] == "defer":
            log_id = defer_async_job(
                task_name="agent.approve_run",
                payload={"run_id": run_id, "user_id": str(user_id), "__autonomy": {"trigger_type": "user", "source": "agent_router.approve", "context": trigger_context}},
                user_id=user_id,
                source="agent_router",
                decision=evaluation,
            )
            return {"status": "SUCCESS", "output_patch": {"agent_run_approve_result": {
                "_http_status": 202,
                "_http_response": build_decision_response(
                    evaluation,
                    trace_id=log_id,
                    result={"automation_log_id": log_id, "decision": "defer", "reason": evaluation["reason"]},
                    next_action={"type": "poll_automation_log", "automation_log_id": log_id},
                ),
            }}}

        run = approve_run(run_id=run_id, user_id=user_id, db=db)
        if not run:
            return {"status": "FAILURE", "error": "HTTP_404:Run not found or not approvable"}
        return {"status": "SUCCESS", "output_patch": {"agent_run_approve_result": to_execution_response(run, db)}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def agent_run_reject_node(state, context):
    try:
        from AINDY.agents.agent_runtime import reject_run, to_execution_response
        from AINDY.utils.uuid_utils import normalize_uuid

        db = context.get("db")
        user_id = normalize_uuid(context.get("user_id"))
        run = reject_run(run_id=state.get("run_id"), user_id=user_id, db=db)
        if not run:
            return {"status": "FAILURE", "error": "HTTP_404:Run not found or not rejectable"}
        return {"status": "SUCCESS", "output_patch": {"agent_run_reject_result": to_execution_response(run, db)}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def agent_run_recover_node(state, context):
    try:
        from AINDY.agents.agent_runtime import to_execution_response
        from AINDY.agents.stuck_run_service import recover_stuck_agent_run
        from AINDY.utils.uuid_utils import normalize_uuid

        db = context.get("db")
        user_id = normalize_uuid(context.get("user_id"))
        result = recover_stuck_agent_run(
            run_id=state.get("run_id"), user_id=user_id, db=db, force=state.get("force", False)
        )
        if result["ok"]:
            return {"status": "SUCCESS", "output_patch": {"agent_run_recover_result": to_execution_response(result["run"], db)}}
        error_code = result.get("error_code", "internal_error")
        http_map = {"not_found": 404, "forbidden": 403, "wrong_status": 409, "too_recent": 409}
        http_status = http_map.get(error_code, 500)
        detail = result.get("detail", error_code)
        return {"status": "FAILURE", "error": f"HTTP_{http_status}:{detail}"}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def agent_run_replay_node(state, context):
    try:
        from AINDY.agents.agent_runtime import replay_run, to_execution_response
        from AINDY.utils.uuid_utils import normalize_uuid

        db = context.get("db")
        user_id = normalize_uuid(context.get("user_id"))
        new_run = replay_run(run_id=state.get("run_id"), user_id=user_id, db=db)
        if not new_run:
            return {"status": "FAILURE", "error": "HTTP_404:Run not found or not replayable"}
        return {"status": "SUCCESS", "output_patch": {"agent_run_replay_result": to_execution_response(new_run, db)}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def agent_run_steps_node(state, context):
    try:
        from AINDY.db.models.agent_run import AgentRun, AgentStep
        from AINDY.utils.uuid_utils import normalize_uuid

        db = context.get("db")
        user_id = normalize_uuid(context.get("user_id"))
        run_id = normalize_uuid(state.get("run_id"))
        run = db.query(AgentRun).filter(AgentRun.id == run_id).first()
        if not run:
            return {"status": "FAILURE", "error": "HTTP_404:Run not found"}
        if run.user_id != user_id:
            return {"status": "FAILURE", "error": "HTTP_403:Not authorized"}
        steps = db.query(AgentStep).filter(AgentStep.run_id == run_id).order_by(AgentStep.step_index.asc()).all()
        data = [
            {
                "step_index": s.step_index,
                "tool_name": s.tool_name,
                "description": s.description,
                "risk_level": s.risk_level,
                "status": s.status,
                "result": s.result,
                "error_message": s.error_message,
                "execution_ms": s.execution_ms,
                "executed_at": s.executed_at.isoformat() if s.executed_at else None,
            }
            for s in steps
        ]
        return {"status": "SUCCESS", "output_patch": {"agent_run_steps_result": data}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def agent_run_events_node(state, context):
    try:
        from AINDY.db.models.agent_run import AgentRun
        from AINDY.agents.agent_runtime import get_run_events
        from AINDY.utils.uuid_utils import normalize_uuid

        db = context.get("db")
        user_id = normalize_uuid(context.get("user_id"))
        run_id = state.get("run_id")
        try:
            normalized_run_id = normalize_uuid(run_id)
        except Exception:
            return {"status": "FAILURE", "error": "HTTP_400:Invalid run_id"}
        result = get_run_events(run_id=run_id, user_id=user_id, db=db)
        if result is None:
            run = db.query(AgentRun).filter(AgentRun.id == normalized_run_id).first()
            if not run:
                return {"status": "FAILURE", "error": "HTTP_404:Run not found"}
            return {"status": "FAILURE", "error": "HTTP_403:Not authorized"}
        return {"status": "SUCCESS", "output_patch": {"agent_run_events_result": result}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def agent_tools_list_node(state, context):
    try:
        from AINDY.agents.agent_tools import TOOL_REGISTRY

        data = [
            {
                "name": name,
                "risk": entry["risk"],
                "description": entry["description"],
                "capability": entry.get("capability"),
                "required_capability": entry.get("required_capability"),
                "category": entry.get("category"),
                "egress_scope": entry.get("egress_scope"),
            }
            for name, entry in TOOL_REGISTRY.items()
        ]
        return {"status": "SUCCESS", "output_patch": {"agent_tools_list_result": data}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def agent_trust_get_node(state, context):
    try:
        from AINDY.db.models.agent_run import AgentTrustSettings
        from AINDY.agents.capability_service import get_auto_grantable_tools
        from AINDY.utils.uuid_utils import normalize_uuid

        db = context.get("db")
        user_id = normalize_uuid(context.get("user_id"))
        trust = db.query(AgentTrustSettings).filter(AgentTrustSettings.user_id == user_id).first()
        result = {
            "user_id": str(user_id),
            "auto_execute_low": trust.auto_execute_low if trust else False,
            "auto_execute_medium": trust.auto_execute_medium if trust else False,
            "allowed_auto_grant_tools": (
                trust.allowed_auto_grant_tools
                if trust and trust.allowed_auto_grant_tools is not None
                else get_auto_grantable_tools(user_id=user_id, db=db)
            ),
            "note": "High-risk plans always require approval regardless of trust settings.",
        }
        return {"status": "SUCCESS", "output_patch": {"agent_trust_get_result": result}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def agent_trust_update_node(state, context):
    try:
        from datetime import datetime, timezone
        from AINDY.db.models.agent_run import AgentTrustSettings
        from AINDY.agents.agent_tools import TOOL_REGISTRY
        from AINDY.utils.uuid_utils import normalize_uuid

        db = context.get("db")
        user_id = normalize_uuid(context.get("user_id"))
        trust = db.query(AgentTrustSettings).filter(AgentTrustSettings.user_id == user_id).first()
        if not trust:
            trust = AgentTrustSettings(user_id=user_id)
            db.add(trust)
        auto_low = state.get("auto_execute_low")
        auto_medium = state.get("auto_execute_medium")
        allowed_tools = state.get("allowed_auto_grant_tools")
        if auto_low is not None:
            trust.auto_execute_low = auto_low
        if auto_medium is not None:
            trust.auto_execute_medium = auto_medium
        if allowed_tools is not None:
            trust.allowed_auto_grant_tools = sorted({
                t for t in allowed_tools
                if t in TOOL_REGISTRY and TOOL_REGISTRY[t]["risk"] in {"low", "medium"} and t != "genesis.message"
            })
        trust.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(trust)
        result = {
            "user_id": str(user_id),
            "auto_execute_low": trust.auto_execute_low,
            "auto_execute_medium": trust.auto_execute_medium,
            "allowed_auto_grant_tools": trust.allowed_auto_grant_tools or [],
            "note": "High-risk plans always require approval regardless of trust settings.",
        }
        return {"status": "SUCCESS", "output_patch": {"agent_trust_update_result": result}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def agent_suggestions_get_node(state, context):
    try:
        from AINDY.agents.agent_tools import suggest_tools
        from apps.analytics.services.infinity_service import get_user_kpi_snapshot
        from AINDY.utils.uuid_utils import normalize_uuid

        db = context.get("db")
        user_id = normalize_uuid(context.get("user_id"))
        snapshot = get_user_kpi_snapshot(user_id=user_id, db=db)
        result = suggest_tools(kpi_snapshot=snapshot, user_id=user_id, db=db)
        return {"status": "SUCCESS", "output_patch": {"agent_suggestions_get_result": result}}
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


def flow_runs_list_node(state, context):
    try:
        from uuid import UUID
        from AINDY.db.models.flow_run import FlowRun

        db = context.get("db")
        user_id = UUID(str(context.get("user_id")))
        status_filter = state.get("status")
        workflow_type = state.get("workflow_type")
        limit = state.get("limit", 20)
        query = db.query(FlowRun).filter(FlowRun.user_id == user_id, FlowRun.flow_name != "flow_runs_list")
        if status_filter:
            query = query.filter(FlowRun.status == status_filter)
        if workflow_type:
            query = query.filter(FlowRun.workflow_type == workflow_type)
        runs = query.order_by(FlowRun.created_at.desc()).limit(limit).all()
        data = {
            "runs": [
                {
                    "id": r.id,
                    "flow_name": r.flow_name,
                    "workflow_type": r.workflow_type,
                    "status": r.status,
                    "trace_id": r.trace_id,
                    "current_node": r.current_node,
                    "waiting_for": r.waiting_for,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "completed_at": r.completed_at.isoformat() if r.completed_at else None,
                    "error_message": r.error_message,
                }
                for r in runs
            ],
            "count": len(runs),
        }
        return {"status": "SUCCESS", "output_patch": {"flow_runs_list_result": data}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def flow_run_get_node(state, context):
    try:
        from uuid import UUID
        from AINDY.db.models.flow_run import FlowRun

        db = context.get("db")
        user_id = UUID(str(context.get("user_id")))
        run_id = state.get("run_id")
        run = db.query(FlowRun).filter(FlowRun.id == run_id, FlowRun.user_id == user_id).first()
        if not run:
            return {"status": "FAILURE", "error": "HTTP_404:Flow run not found"}
        result = {
            "id": run.id,
            "flow_name": run.flow_name,
            "workflow_type": run.workflow_type,
            "status": run.status,
            "trace_id": run.trace_id,
            "current_node": run.current_node,
            "waiting_for": run.waiting_for,
            "state": run.state,
            "error_message": run.error_message,
            "created_at": run.created_at.isoformat() if run.created_at else None,
            "updated_at": run.updated_at.isoformat() if run.updated_at else None,
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        }
        return {"status": "SUCCESS", "output_patch": {"flow_run_get_result": result}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def flow_run_history_node(state, context):
    try:
        from uuid import UUID
        from AINDY.db.models.flow_run import FlowHistory, FlowRun

        db = context.get("db")
        user_id = UUID(str(context.get("user_id")))
        run_id = state.get("run_id")
        run = db.query(FlowRun).filter(FlowRun.id == run_id, FlowRun.user_id == user_id).first()
        if not run:
            return {"status": "FAILURE", "error": "HTTP_404:Flow run not found"}
        history = db.query(FlowHistory).filter(FlowHistory.flow_run_id == run_id).order_by(FlowHistory.created_at.asc()).all()
        result = {
            "run_id": run_id,
            "trace_id": run.trace_id,
            "flow_name": run.flow_name,
            "workflow_type": run.workflow_type,
            "history": [
                {
                    "id": h.id,
                    "node_name": h.node_name,
                    "status": h.status,
                    "execution_time_ms": h.execution_time_ms,
                    "output_patch": h.output_patch,
                    "error_message": h.error_message,
                    "created_at": h.created_at.isoformat() if h.created_at else None,
                }
                for h in history
            ],
            "node_count": len(history),
        }
        return {"status": "SUCCESS", "output_patch": {"flow_run_history_result": result}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def flow_run_resume_node(state, context):
    try:
        from uuid import UUID
        from AINDY.db.models.flow_run import FlowRun
        from AINDY.runtime.flow_engine import route_event

        db = context.get("db")
        user_id = UUID(str(context.get("user_id")))
        run_id = state.get("run_id")
        event_type = state.get("event_type")
        payload = state.get("payload", {})
        run = db.query(FlowRun).filter(FlowRun.id == run_id, FlowRun.user_id == user_id).first()
        if not run:
            return {"status": "FAILURE", "error": "HTTP_404:Flow run not found"}
        if run.status != "waiting":
            return {"status": "FAILURE", "error": f"HTTP_400:Flow run is '{run.status}', not 'waiting'. Cannot resume."}
        if run.waiting_for != event_type:
            return {"status": "FAILURE", "error": f"HTTP_400:Flow run waiting for '{run.waiting_for}', not '{event_type}'"}
        results = route_event(event_type=event_type, payload=payload, db=db, user_id=user_id)
        return {"status": "SUCCESS", "output_patch": {"flow_run_resume_result": {"run_id": run_id, "resumed": True, "results": results}}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def flow_registry_get_node(state, context):
    try:
        from AINDY.runtime.flow_engine import FLOW_REGISTRY as FLOWS, NODE_REGISTRY

        result = {
            "flows": {
                name: {
                    "start": flow["start"],
                    "end": flow.get("end", []),
                    "node_count": len(flow.get("edges", {})) + 1,
                }
                for name, flow in FLOWS.items()
            },
            "nodes": list(NODE_REGISTRY.keys()),
            "flow_count": len(FLOWS),
            "node_count": len(NODE_REGISTRY),
        }
        return {"status": "SUCCESS", "output_patch": {"flow_registry_get_result": result}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def automation_logs_list_node(state, context):
    try:
        from uuid import UUID
        from apps.automation.models import AutomationLog

        db = context.get("db")
        user_id = UUID(str(context.get("user_id")))
        status = state.get("status")
        source_filter = state.get("source_filter")
        limit = state.get("limit", 50)
        query = db.query(AutomationLog).filter(AutomationLog.user_id == user_id)
        if status:
            query = query.filter(AutomationLog.status == status)
        if source_filter:
            query = query.filter(AutomationLog.source == source_filter)
        logs = query.order_by(AutomationLog.created_at.desc()).limit(limit).all()

        def _s(log):
            return {
                "id": log.id, "source": log.source, "task_name": log.task_name,
                "payload": log.payload, "status": log.status,
                "attempt_count": log.attempt_count, "max_attempts": log.max_attempts,
                "error_message": log.error_message, "result": log.result,
                "created_at": log.created_at.isoformat() if log.created_at else None,
                "started_at": log.started_at.isoformat() if log.started_at else None,
                "completed_at": log.completed_at.isoformat() if log.completed_at else None,
                "scheduled_for": log.scheduled_for.isoformat() if log.scheduled_for else None,
            }

        return {"status": "SUCCESS", "output_patch": {"automation_logs_list_result": {"logs": [_s(log) for log in logs], "count": len(logs), "filters": {"status": status, "source": source_filter}}}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def automation_log_get_node(state, context):
    try:
        from uuid import UUID
        from apps.automation.models import AutomationLog

        db = context.get("db")
        user_id = UUID(str(context.get("user_id")))
        log_id = state.get("log_id")
        log = db.query(AutomationLog).filter(AutomationLog.id == log_id, AutomationLog.user_id == user_id).first()
        if not log:
            return {"status": "FAILURE", "error": "HTTP_404:Automation log not found"}

        def _s(log):
            return {
                "id": log.id, "source": log.source, "task_name": log.task_name,
                "payload": log.payload, "status": log.status,
                "attempt_count": log.attempt_count, "max_attempts": log.max_attempts,
                "error_message": log.error_message, "result": log.result,
                "created_at": log.created_at.isoformat() if log.created_at else None,
                "started_at": log.started_at.isoformat() if log.started_at else None,
                "completed_at": log.completed_at.isoformat() if log.completed_at else None,
                "scheduled_for": log.scheduled_for.isoformat() if log.scheduled_for else None,
            }

        return {"status": "SUCCESS", "output_patch": {"automation_log_get_result": _s(log)}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def automation_log_replay_node(state, context):
    try:
        from uuid import UUID
        from apps.automation.models import AutomationLog

        db = context.get("db")
        user_id = UUID(str(context.get("user_id")))
        log_id = state.get("log_id")
        log = db.query(AutomationLog).filter(AutomationLog.id == log_id, AutomationLog.user_id == user_id).first()
        if not log:
            return {"status": "FAILURE", "error": "HTTP_404:Automation log not found"}
        if log.status not in ("failed", "retrying"):
            return {"status": "FAILURE", "error": f"HTTP_400:Cannot replay log with status '{log.status}'. Only failed or retrying logs can be replayed."}
        from AINDY.platform_layer.scheduler_service import replay_task

        result = replay_task(log_id)
        if not result:
            return {"status": "FAILURE", "error": "HTTP_500:Replay failed - task function not registered. Check task registry."}
        return {"status": "SUCCESS", "output_patch": {"automation_log_replay_result": {"log_id": log_id, "status": "replay_scheduled", "message": "Task replay has been scheduled. Check GET /automation/logs/{id} for status updates."}}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def automation_scheduler_status_node(state, context):
    try:
        from AINDY.platform_layer.scheduler_service import get_scheduler

        try:
            scheduler = get_scheduler()
            jobs = scheduler.get_jobs()
            running = scheduler.running
        except RuntimeError as exc:
            return {"status": "FAILURE", "error": f"HTTP_503:{exc}"}
        return {"status": "SUCCESS", "output_patch": {"automation_scheduler_status_result": {
            "running": running,
            "job_count": len(jobs),
            "jobs": [{"id": job.id, "name": job.name, "next_run": job.next_run_time.isoformat() if job.next_run_time else None, "trigger": str(job.trigger)} for job in jobs],
        }}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def automation_task_trigger_node(state, context):
    try:
        from apps.tasks.services.task_service import get_task_by_id, queue_task_automation

        db = context.get("db")
        user_id = context.get("user_id")
        task_id = state.get("task_id")
        automation_type = state.get("automation_type")
        automation_config = state.get("automation_config")
        task = get_task_by_id(db, task_id, user_id)
        if not task:
            return {"status": "FAILURE", "error": "HTTP_404:Task not found"}
        if automation_type is not None:
            task.automation_type = automation_type
        if automation_config is not None:
            task.automation_config = automation_config
        db.commit()
        db.refresh(task)
        if not task.automation_type:
            return {"status": "FAILURE", "error": "HTTP_422:task_automation_not_configured"}
        dispatch = queue_task_automation(db=db, task=task, user_id=user_id, reason="manual_trigger")
        if not dispatch:
            return {"status": "FAILURE", "error": "HTTP_500:task_automation_dispatch_failed"}
        return {"status": "SUCCESS", "output_patch": {"automation_task_trigger_result": dispatch}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def memory_node_create_node(state, context):
    try:
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO

        db = context.get("db")
        user_id = str(context.get("user_id"))
        dao = MemoryNodeDAO(db)
        result = dao.save(
            content=state.get("content"),
            source=state.get("source"),
            tags=state.get("tags", []),
            user_id=user_id,
            node_type=state.get("node_type"),
            extra=state.get("extra", {}),
        )
        return {"status": "SUCCESS", "output_patch": {"memory_node_create_result": result}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def memory_node_get_node(state, context):
    try:
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO
        from AINDY.utils.uuid_utils import normalize_uuid

        db = context.get("db")
        user_id = normalize_uuid(context.get("user_id"))
        dao = MemoryNodeDAO(db)
        node = dao.get_by_id(state.get("node_id"), user_id=user_id)
        if not node:
            return {"status": "FAILURE", "error": "HTTP_404:Memory node not found"}
        if user_id is not None and str(node.get("user_id")) != str(user_id):
            return {"status": "FAILURE", "error": "HTTP_404:Memory node not found"}
        return {"status": "SUCCESS", "output_patch": {"memory_node_get_result": node}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def memory_node_update_node(state, context):
    try:
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO

        db = context.get("db")
        user_id = str(context.get("user_id"))
        dao = MemoryNodeDAO(db)
        updated = dao.update(
            node_id=state.get("node_id"),
            user_id=user_id,
            content=state.get("content"),
            tags=state.get("tags"),
            node_type=state.get("node_type"),
            source=state.get("source"),
        )
        if not updated:
            return {"status": "FAILURE", "error": "HTTP_404:Memory node not found"}
        return {"status": "SUCCESS", "output_patch": {"memory_node_update_result": dao._node_to_dict(updated)}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def memory_node_history_node(state, context):
    try:
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO

        db = context.get("db")
        user_id = str(context.get("user_id"))
        node_id = state.get("node_id")
        limit = state.get("limit", 20)
        dao = MemoryNodeDAO(db)
        history = dao.get_history(node_id=node_id, user_id=user_id, limit=limit)
        return {"status": "SUCCESS", "output_patch": {"memory_node_history_result": {"node_id": node_id, "history": history, "count": len(history)}}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def memory_node_links_node(state, context):
    try:
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO

        db = context.get("db")
        user_id = str(context.get("user_id"))
        node_id = state.get("node_id")
        direction = state.get("direction", "both")
        if direction not in ("in", "out", "both"):
            return {"status": "FAILURE", "error": "HTTP_422:direction must be 'in', 'out', or 'both'"}
        dao = MemoryNodeDAO(db)
        if not dao.get_by_id(node_id, user_id=user_id):
            return {"status": "FAILURE", "error": "HTTP_404:Memory node not found"}
        return {"status": "SUCCESS", "output_patch": {"memory_node_links_result": {"nodes": dao.get_linked_nodes(node_id, direction=direction, user_id=user_id)}}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def memory_nodes_search_tags_node(state, context):
    try:
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO

        db = context.get("db")
        user_id = str(context.get("user_id"))
        tags_str = state.get("tags", "")
        mode = state.get("mode", "AND")
        limit = state.get("limit", 50)
        if mode.upper() not in ("AND", "OR"):
            return {"status": "FAILURE", "error": "HTTP_422:mode must be 'AND' or 'OR'"}
        tag_list = [t.strip() for t in tags_str.split(",") if t.strip()] if tags_str else []
        dao = MemoryNodeDAO(db)
        return {"status": "SUCCESS", "output_patch": {"memory_nodes_search_tags_result": {"nodes": dao.get_by_tags(tag_list, limit=limit, mode=mode, user_id=user_id)}}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def memory_link_create_node(state, context):
    try:
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO

        db = context.get("db")
        user_id = str(context.get("user_id"))
        dao = MemoryNodeDAO(db)
        source_id = state.get("source_id")
        target_id = state.get("target_id")
        if not dao.get_by_id(source_id, user_id=user_id):
            return {"status": "FAILURE", "error": "HTTP_404:Source node not found"}
        if not dao.get_by_id(target_id, user_id=user_id):
            return {"status": "FAILURE", "error": "HTTP_404:Target node not found"}
        try:
            result = dao.create_link(source_id, target_id, state.get("link_type", "related"), state.get("weight", 0.5), user_id=user_id)
        except ValueError as ve:
            return {"status": "FAILURE", "error": f"HTTP_422:Invalid memory link: {ve}"}
        return {"status": "SUCCESS", "output_patch": {"memory_link_create_result": result}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def memory_node_traverse_node(state, context):
    try:
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO

        db = context.get("db")
        user_id = str(context.get("user_id"))
        node_id = state.get("node_id")
        max_depth = min(state.get("max_depth", 3), 5)
        dao = MemoryNodeDAO(db)
        result = dao.traverse(
            start_node_id=node_id,
            max_depth=max_depth,
            link_type=state.get("link_type"),
            user_id=user_id,
            min_strength=state.get("min_strength", 0.0),
        )
        if not result["found"]:
            return {"status": "FAILURE", "error": "HTTP_404:Memory node not found"}
        return {"status": "SUCCESS", "output_patch": {"memory_node_traverse_result": result}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def memory_nodes_expand_node(state, context):
    try:
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO

        db = context.get("db")
        user_id = str(context.get("user_id"))
        node_ids = state.get("node_ids", [])
        if len(node_ids) > 10:
            return {"status": "FAILURE", "error": "HTTP_400:Maximum 10 nodes per expansion request"}
        dao = MemoryNodeDAO(db)
        result = dao.expand(
            node_ids=node_ids,
            user_id=user_id,
            include_linked=state.get("include_linked", True),
            include_similar=state.get("include_similar", True),
            limit_per_node=state.get("limit_per_node", 3),
        )
        return {"status": "SUCCESS", "output_patch": {"memory_nodes_expand_result": result}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def memory_nodes_search_similar_node(state, context):
    try:
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO
        from AINDY.memory.embedding_service import generate_query_embedding

        db = context.get("db")
        user_id = str(context.get("user_id"))
        query = state.get("query", "")
        query_embedding = generate_query_embedding(query)
        dao = MemoryNodeDAO(db)
        results = dao.find_similar(
            query_embedding=query_embedding,
            limit=state.get("limit", 5),
            user_id=user_id,
            node_type=state.get("node_type"),
            min_similarity=state.get("min_similarity", 0.0),
        )
        return {"status": "SUCCESS", "output_patch": {"memory_nodes_search_similar_result": {"query": query, "results": results, "count": len(results)}}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def memory_recall_node(state, context):
    try:
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO
        from AINDY.runtime.memory import MemoryOrchestrator, memory_items_to_dicts

        db = context.get("db")
        user_id = str(context.get("user_id"))
        query = state.get("query")
        tags = state.get("tags")
        if not query and not tags:
            return {"status": "FAILURE", "error": "HTTP_400:Provide at least one of: query, tags"}
        metadata = {"tags": tags, "node_type": state.get("node_type"), "limit": state.get("limit", 5)}
        if state.get("node_type") is None:
            metadata["node_types"] = []
        orchestrator = MemoryOrchestrator(MemoryNodeDAO)
        context_obj = orchestrator.get_context(user_id=user_id, query=query or "", task_type="analysis", db=db, max_tokens=1200, metadata=metadata)
        results = memory_items_to_dicts(context_obj.items)
        return {"status": "SUCCESS", "output_patch": {"memory_recall_result": {"query": query, "tags": tags, "results": results, "count": len(results), "scoring_version": "v2", "formula": {"semantic": 0.40, "graph": 0.15, "recency": 0.15, "success_rate": 0.20, "usage_frequency": 0.10, "note": "adaptive_weight multiplier applied; tag_score adds up to +0.1"}}}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def memory_recall_v3_node(state, context):
    try:
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO
        from AINDY.runtime.memory import MemoryOrchestrator, memory_items_to_dicts

        db = context.get("db")
        user_id = str(context.get("user_id"))
        query = state.get("query")
        tags = state.get("tags")
        if not query and not tags:
            return {"status": "FAILURE", "error": "HTTP_400:Provide at least one of: query, tags"}
        metadata = {"tags": tags, "node_type": state.get("node_type"), "limit": state.get("limit", 5)}
        if state.get("node_type") is None:
            metadata["node_types"] = []
        orchestrator = MemoryOrchestrator(MemoryNodeDAO)
        context_obj = orchestrator.get_context(user_id=user_id, query=query or "", task_type="analysis", db=db, max_tokens=1200, metadata=metadata)
        results = memory_items_to_dicts(context_obj.items)
        formula = {"semantic": 0.40, "graph": 0.15, "recency": 0.15, "success_rate": 0.20, "usage_frequency": 0.10, "note": "adaptive_weight multiplier applied; tag_score adds up to +0.1"}
        if state.get("expand_results") and context_obj.ids:
            dao = MemoryNodeDAO(db)
            expansion = dao.expand(node_ids=context_obj.ids[:3], user_id=user_id, include_linked=True, include_similar=True, limit_per_node=2)
            result = {"query": query, "tags": tags, "results": results, "expanded": expansion.get("expanded_nodes", []), "expansion_map": expansion.get("expansion_map", {}), "total_context_nodes": len(results) + len(expansion.get("expanded_nodes", [])), "scoring_version": "v2", "formula": formula}
        else:
            result = {"query": query, "tags": tags, "results": results, "count": len(results), "scoring_version": "v2", "formula": formula}
        return {"status": "SUCCESS", "output_patch": {"memory_recall_v3_result": result}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def memory_recall_federated_node(state, context):
    try:
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO
        from AINDY.utils.uuid_utils import normalize_uuid

        db = context.get("db")
        user_id = normalize_uuid(context.get("user_id"))
        query = state.get("query")
        tags = state.get("tags")
        if not query and not tags:
            return {"status": "FAILURE", "error": "HTTP_400:Provide at least one of: query, tags"}
        dao = MemoryNodeDAO(db)
        result = dao.recall_federated(query=query, tags=tags, agent_namespaces=state.get("agent_namespaces"), limit=state.get("limit", 5), user_id=user_id)
        return {"status": "SUCCESS", "output_patch": {"memory_recall_federated_result": result}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def memory_agents_list_node(state, context):
    try:
        from AINDY.db.models.agent import Agent
        from AINDY.memory.memory_persistence import MemoryNodeModel
        from AINDY.utils.uuid_utils import normalize_uuid

        db = context.get("db")
        user_id = normalize_uuid(context.get("user_id"))
        agents = db.query(Agent).filter(Agent.is_active.is_(True)).all()
        result_list = []
        for agent in agents:
            node_count = db.query(MemoryNodeModel).filter(MemoryNodeModel.source_agent == agent.memory_namespace, MemoryNodeModel.user_id == user_id).count()
            shared_count = db.query(MemoryNodeModel).filter(MemoryNodeModel.source_agent == agent.memory_namespace, MemoryNodeModel.user_id == user_id, MemoryNodeModel.is_shared.is_(True)).count()
            result_list.append({"id": agent.id, "name": agent.name, "agent_type": agent.agent_type, "description": agent.description, "memory_namespace": agent.memory_namespace, "is_active": agent.is_active, "memory_stats": {"total_nodes": node_count, "shared_nodes": shared_count, "private_nodes": node_count - shared_count}})
        return {"status": "SUCCESS", "output_patch": {"memory_agents_list_result": {"agents": result_list, "total": len(result_list)}}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def memory_node_share_node(state, context):
    try:
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO
        from AINDY.utils.uuid_utils import normalize_uuid

        db = context.get("db")
        user_id = normalize_uuid(context.get("user_id"))
        node_id = state.get("node_id")
        dao = MemoryNodeDAO(db)
        node = dao.share_memory(node_id=node_id, user_id=user_id)
        if not node:
            return {"status": "FAILURE", "error": "HTTP_404:Memory node not found"}
        return {"status": "SUCCESS", "output_patch": {"memory_node_share_result": {"node_id": node_id, "is_shared": node.is_shared, "source_agent": node.source_agent, "message": "Memory node is now shared with all agents."}}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def memory_agent_recall_node(state, context):
    try:
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO
        from AINDY.utils.uuid_utils import normalize_uuid

        db = context.get("db")
        user_id = normalize_uuid(context.get("user_id"))
        namespace = state.get("namespace", "")
        dao = MemoryNodeDAO(db)
        results = dao.recall_from_agent(agent_namespace=namespace, query=state.get("query"), limit=state.get("limit", 5), user_id=user_id, include_private=False)
        return {"status": "SUCCESS", "output_patch": {"memory_agent_recall_result": {"agent_namespace": namespace, "query": state.get("query"), "results": results, "count": len(results)}}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def memory_node_feedback_node(state, context):
    try:
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO

        db = context.get("db")
        user_id = str(context.get("user_id"))
        node_id = state.get("node_id")
        outcome = state.get("outcome")
        dao = MemoryNodeDAO(db)
        node = dao.record_feedback(node_id=node_id, outcome=outcome, user_id=user_id)
        if not node:
            return {"status": "FAILURE", "error": "HTTP_404:Memory node not found"}
        return {"status": "SUCCESS", "output_patch": {"memory_node_feedback_result": {"node_id": node_id, "outcome": outcome, "success_count": node.success_count, "failure_count": node.failure_count, "usage_count": node.usage_count, "adaptive_weight": node.weight, "success_rate": dao.get_success_rate(node), "message": {"success": "Weight boosted - memory reinforced", "failure": "Weight reduced - memory suppressed", "neutral": "Usage recorded - no weight change"}[outcome]}}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def memory_node_performance_node(state, context):
    try:
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO

        db = context.get("db")
        user_id = str(context.get("user_id"))
        node_id = state.get("node_id")
        dao = MemoryNodeDAO(db)
        node = dao._get_model_by_id(node_id, user_id=user_id)
        if not node:
            return {"status": "FAILURE", "error": "HTTP_404:Memory node not found"}
        success_rate = dao.get_success_rate(node)
        usage_freq = dao.get_usage_frequency_score(node)
        graph_score = dao.get_graph_connectivity_score(node_id)
        total_feedback = (node.success_count or 0) + (node.failure_count or 0)
        return {"status": "SUCCESS", "output_patch": {"memory_node_performance_result": {"node_id": node_id, "content_preview": (node.content or "")[:100], "node_type": node.node_type, "performance": {"success_count": node.success_count or 0, "failure_count": node.failure_count or 0, "usage_count": node.usage_count or 0, "success_rate": round(success_rate, 3), "adaptive_weight": round(node.weight or 1.0, 3), "last_outcome": node.last_outcome, "last_used_at": node.last_used_at.isoformat() if node.last_used_at else None, "total_feedback_signals": total_feedback, "graph_connectivity": round(graph_score, 3), "usage_frequency_score": round(usage_freq, 3)}, "resonance_v2_preview": {"note": "Scores shown for this node in isolation. Actual resonance depends on query context.", "success_rate_component": round(success_rate * 0.20, 4), "usage_freq_component": round(usage_freq * 0.10, 4), "graph_component": round(graph_score * 0.15, 4), "adaptive_weight": round(node.weight or 1.0, 3)}}}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def memory_suggest_node(state, context):
    try:
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO

        db = context.get("db")
        user_id = str(context.get("user_id"))
        query = state.get("query")
        tags = state.get("tags")
        if not query and not tags:
            return {"status": "FAILURE", "error": "HTTP_400:Provide at least one of: query, tags"}
        dao = MemoryNodeDAO(db)
        result = dao.suggest(query=query, tags=tags, context=state.get("context"), user_id=user_id, limit=state.get("limit", 3))
        return {"status": "SUCCESS", "output_patch": {"memory_suggest_result": result}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def memory_nodus_execute_node(state, context):
    try:
        from AINDY.core.execution_envelope import success
        from AINDY.runtime.nodus_execution_service import execute_nodus_task_payload
        from AINDY.runtime.nodus_security import NodusSecurityError
        from AINDY.platform_layer.trace_context import ensure_trace_id
        from AINDY.platform_layer.user_ids import require_user_id

        db = context.get("db")
        user_id = str(require_user_id(context.get("user_id")))
        try:
            result = execute_nodus_task_payload(
                task_name=state.get("task_name"),
                task_code=state.get("task_code"),
                db=db,
                user_id=user_id,
                session_tags=state.get("session_tags", []),
                allowed_operations=state.get("allowed_operations"),
                execution_id=state.get("execution_id"),
                capability_token=state.get("capability_token"),
            )
            if isinstance(result, dict) and {"status", "result", "events", "next_action", "trace_id"}.issubset(result.keys()):
                return {"status": "SUCCESS", "output_patch": {"memory_nodus_execute_result": result}}
            return {"status": "SUCCESS", "output_patch": {"memory_nodus_execute_result": success(result, [], ensure_trace_id())}}
        except NodusSecurityError as exc:
            return {"status": "FAILURE", "error": f"HTTP_403:nodus_security_violation: {exc}"}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def observability_scheduler_status_node(state, context):
    try:
        import AINDY.platform_layer.scheduler_service as _sched_svc
        import apps.tasks.services.task_service as _task_svc
        from AINDY.db.models.background_task_lease import BackgroundTaskLease

        db = context.get("db")
        try:
            sched = _sched_svc.get_scheduler()
            scheduler_running = sched.running
        except RuntimeError:
            scheduler_running = False
        lease_row = db.query(BackgroundTaskLease).filter(BackgroundTaskLease.name == _task_svc._BACKGROUND_LEASE_NAME).first()
        lease = None
        if lease_row:
            lease = {
                "owner_id": lease_row.owner_id,
                "acquired_at": lease_row.acquired_at.isoformat() if lease_row.acquired_at else None,
                "heartbeat_at": lease_row.heartbeat_at.isoformat() if lease_row.heartbeat_at else None,
                "expires_at": lease_row.expires_at.isoformat() if lease_row.expires_at else None,
            }
        return {"status": "SUCCESS", "output_patch": {"observability_scheduler_status_result": {"scheduler_running": scheduler_running, "is_leader": _task_svc.is_background_leader(), "lease": lease}}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def observability_dashboard_node(state, context):
    try:
        import uuid as _uuid
        from collections import Counter
        from datetime import datetime, timedelta, timezone
        from sqlalchemy import func
        from AINDY.db.models.agent_event import AgentEvent
        from AINDY.db.models.flow_run import FlowRun
        from AINDY.db.models.request_metric import RequestMetric
        from AINDY.db.models.system_event import SystemEvent
        from AINDY.db.models.system_health_log import SystemHealthLog

        db = context.get("db")
        user_id = _uuid.UUID(str(context.get("user_id")))
        window_hours = state.get("window_hours", 24)
        event_limit = state.get("event_limit", 60)
        agent_limit = state.get("agent_limit", 30)
        health_limit = state.get("health_limit", 20)
        request_window_start = datetime.now(timezone.utc) - timedelta(hours=window_hours)
        event_window_start = datetime.now(timezone.utc) - timedelta(hours=window_hours)
        req_q = db.query(RequestMetric).filter(RequestMetric.user_id == user_id)
        avg_latency = db.query(func.avg(RequestMetric.duration_ms)).filter(RequestMetric.user_id == user_id, RequestMetric.created_at >= request_window_start).scalar()
        window_requests = req_q.filter(RequestMetric.created_at >= request_window_start).count()
        window_errors = req_q.filter(RequestMetric.created_at >= request_window_start, RequestMetric.status_code >= 500).count()
        recent_requests = req_q.order_by(RequestMetric.created_at.desc()).limit(20).all()
        recent_request_errors = req_q.filter(RequestMetric.status_code >= 500).order_by(RequestMetric.created_at.desc()).limit(20).all()
        system_events = db.query(SystemEvent).filter(SystemEvent.user_id == user_id, SystemEvent.timestamp >= event_window_start).order_by(SystemEvent.timestamp.desc()).limit(event_limit).all()
        visible_system_events = [event for event in system_events if not str(event.type or "").startswith("execution.")]
        agent_events = db.query(AgentEvent).filter(AgentEvent.user_id == user_id, AgentEvent.occurred_at >= event_window_start).order_by(AgentEvent.occurred_at.desc()).limit(agent_limit).all()
        health_logs = db.query(SystemHealthLog).filter(SystemHealthLog.timestamp >= request_window_start).order_by(SystemHealthLog.timestamp.desc()).limit(health_limit).all()
        flow_rows = db.query(FlowRun).filter(FlowRun.user_id == user_id, FlowRun.created_at >= event_window_start, FlowRun.flow_name != "observability_dashboard").order_by(FlowRun.created_at.desc()).limit(100).all()
        flow_status_counts = Counter(str(row.status or "unknown") for row in flow_rows)
        system_event_counts = Counter(str(event.type or "unknown") for event in visible_system_events)
        latest_health = health_logs[0] if health_logs else None
        return {"status": "SUCCESS", "output_patch": {"observability_dashboard_result": {
            "summary": {
                "window_hours": window_hours,
                "avg_latency_ms": round(avg_latency or 0.0, 2),
                "window_requests": window_requests,
                "window_errors": window_errors,
                "error_rate_pct": round((window_errors / window_requests) * 100, 2) if window_requests else 0.0,
                "active_flows": sum(1 for r in flow_rows if r.status in {"running", "waiting"}),
                "loop_events": sum(1 for event in visible_system_events if str(event.type).startswith("loop.")),
                "agent_events": len(agent_events),
                "system_event_total": len(visible_system_events),
                "health_status": str(getattr(latest_health, "status", "unknown")),
            },
            "loop_activity": [{"type": event.type, "trace_id": event.trace_id, "timestamp": event.timestamp.isoformat() if event.timestamp else None, "payload": event.payload or {}} for event in visible_system_events if str(event.type).startswith("loop.")],
            "agent_timeline": [{"run_id": str(event.run_id), "event_type": event.event_type, "correlation_id": event.correlation_id, "occurred_at": event.occurred_at.isoformat() if event.occurred_at else None, "payload": event.payload or {}} for event in agent_events],
            "system_events": {"counts": dict(system_event_counts), "recent": [{"type": event.type, "trace_id": event.trace_id, "timestamp": event.timestamp.isoformat() if event.timestamp else None} for event in visible_system_events[:20]]},
            "system_health": {
                "latest": ({"status": latest_health.status, "timestamp": latest_health.timestamp.isoformat() if latest_health.timestamp else None, "components": latest_health.components or {}, "api_endpoints": latest_health.api_endpoints or {}, "avg_latency_ms": latest_health.avg_latency_ms} if latest_health else None),
                "recent": [{"status": row.status, "timestamp": row.timestamp.isoformat() if row.timestamp else None, "avg_latency_ms": row.avg_latency_ms} for row in health_logs],
            },
            "request_metrics": {
                "recent": [{"request_id": row.request_id, "trace_id": row.trace_id, "method": row.method, "path": row.path, "status_code": row.status_code, "duration_ms": row.duration_ms, "created_at": row.created_at.isoformat() if row.created_at else None} for row in recent_requests],
                "recent_errors": [{"request_id": row.request_id, "trace_id": row.trace_id, "method": row.method, "path": row.path, "status_code": row.status_code, "duration_ms": row.duration_ms, "created_at": row.created_at.isoformat() if row.created_at else None} for row in recent_request_errors],
            },
            "flows": {"status_counts": dict(flow_status_counts), "recent": [{"id": str(row.id), "trace_id": row.trace_id, "flow_name": row.flow_name, "workflow_type": row.workflow_type, "status": row.status, "current_node": row.current_node, "created_at": row.created_at.isoformat() if row.created_at else None} for row in flow_rows[:20]]},
        }}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def observability_requests_node(state, context):
    try:
        import uuid as _uuid
        from datetime import datetime, timedelta, timezone
        from sqlalchemy import func
        from AINDY.db.models.request_metric import RequestMetric

        db = context.get("db")
        user_id = _uuid.UUID(str(context.get("user_id")))
        limit = state.get("limit", 50)
        error_limit = state.get("error_limit", 25)
        window_hours = state.get("window_hours", 24)
        window_start = datetime.now(timezone.utc) - timedelta(hours=window_hours)
        base = db.query(RequestMetric).filter(RequestMetric.user_id == user_id)
        total = base.count()
        window_total = base.filter(RequestMetric.created_at >= window_start).count()
        error_total = base.filter(RequestMetric.status_code >= 500).count()
        window_error_total = base.filter(RequestMetric.created_at >= window_start, RequestMetric.status_code >= 500).count()
        avg_latency = db.query(func.avg(RequestMetric.duration_ms)).filter(RequestMetric.user_id == user_id).scalar()
        recent = base.order_by(RequestMetric.created_at.desc()).limit(limit).all()
        recent_errors = base.filter(RequestMetric.status_code >= 500).order_by(RequestMetric.created_at.desc()).limit(error_limit).all()

        def _s(row):
            return {"request_id": row.request_id, "trace_id": row.trace_id, "method": row.method, "path": row.path, "status_code": row.status_code, "duration_ms": row.duration_ms, "created_at": row.created_at}

        return {"status": "SUCCESS", "output_patch": {"observability_requests_result": {"summary": {"total_requests": total, "window_hours": window_hours, "window_requests": window_total, "total_errors": error_total, "window_errors": window_error_total, "avg_latency_ms": round(avg_latency or 0.0, 2)}, "recent": [_s(r) for r in recent], "recent_errors": [_s(r) for r in recent_errors]}}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def observability_rippletrace_node(state, context):
    try:
        import uuid as _uuid
        from AINDY.db.models.system_event import SystemEvent
        from apps.rippletrace.services.rippletrace_service import build_trace_graph, calculate_ripple_span, detect_root_event, detect_terminal_events, generate_trace_insights

        db = context.get("db")
        user_id = _uuid.UUID(str(context.get("user_id")))
        trace_id = state.get("trace_id")
        event_count = db.query(SystemEvent).filter(SystemEvent.trace_id == trace_id, SystemEvent.user_id == user_id).count()
        if event_count == 0:
            result = {"trace_id": trace_id, "nodes": [], "edges": [], "root_event": None, "terminal_events": [], "ripple_span": {"node_count": 0, "edge_count": 0, "depth": 0, "terminal_count": 0}}
        else:
            graph = build_trace_graph(db, trace_id)
            result = {"trace_id": trace_id, "nodes": graph["nodes"], "edges": graph["edges"], "root_event": detect_root_event(db, trace_id), "terminal_events": detect_terminal_events(db, trace_id), "ripple_span": calculate_ripple_span(db, trace_id), "insights": generate_trace_insights(db, trace_id)}
        return {"status": "SUCCESS", "output_patch": {"observability_rippletrace_result": result}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def dashboard_overview_node(state, context):
    try:
        import uuid
        from datetime import datetime, timezone
        from apps.authorship.models import AuthorDB
        from apps.rippletrace.models import PingDB

        db = context.get("db")
        user_id = uuid.UUID(str(context.get("user_id")))
        authors = db.query(AuthorDB).filter(AuthorDB.user_id == user_id).order_by(AuthorDB.joined_at.desc()).limit(10).all()
        author_list = [{"id": a.id, "name": a.name, "platform": a.platform, "last_seen": a.last_seen.isoformat() if a.last_seen else None, "notes": a.notes} for a in authors]
        ripples = db.query(PingDB).filter(PingDB.user_id == user_id).order_by(PingDB.date_detected.desc()).limit(10).all()
        ripple_list = [{"ping_type": r.ping_type, "source_platform": r.source_platform, "summary": r.connection_summary, "date_detected": r.date_detected.isoformat() if r.date_detected else None} for r in ripples]
        result = {"status": "ok", "overview": {"system_timestamp": datetime.now(timezone.utc).isoformat(), "author_count": len(author_list), "recent_authors": author_list, "recent_ripples": ripple_list}}
        return {"status": "SUCCESS", "output_patch": {"dashboard_overview_result": result}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def autonomy_decisions_list_node(state, context):
    try:
        from AINDY.agents.autonomous_controller import list_recent_decisions

        db = context.get("db")
        user_id = context.get("user_id")
        limit = int(state.get("limit") or 50)
        decisions = list_recent_decisions(db, user_id=user_id, limit=limit)
        return {"status": "SUCCESS", "output_patch": {"autonomy_decisions_list_result": decisions}}
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


def health_dashboard_list_node(state, context):
    try:
        from AINDY.db.models.system_health_log import SystemHealthLog

        db = context.get("db")
        limit = int(state.get("limit") or 20)
        logs = db.query(SystemHealthLog).order_by(SystemHealthLog.timestamp.desc()).limit(limit).all()
        formatted = [{"timestamp": log.timestamp.isoformat(), "status": log.status, "avg_latency_ms": log.avg_latency_ms, "components": log.components, "api_endpoints": log.api_endpoints} for log in logs]
        return {"status": "SUCCESS", "output_patch": {"health_dashboard_list_result": {"count": len(formatted), "logs": formatted}}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def register() -> None:
    register_nodes(
        {
            "agent_run_create_node": agent_run_create_node,
            "agent_runs_list_node": agent_runs_list_node,
            "agent_run_get_node": agent_run_get_node,
            "agent_run_approve_node": agent_run_approve_node,
            "agent_run_reject_node": agent_run_reject_node,
            "agent_run_recover_node": agent_run_recover_node,
            "agent_run_replay_node": agent_run_replay_node,
            "agent_run_steps_node": agent_run_steps_node,
            "agent_run_events_node": agent_run_events_node,
            "agent_tools_list_node": agent_tools_list_node,
            "agent_trust_get_node": agent_trust_get_node,
            "agent_trust_update_node": agent_trust_update_node,
            "agent_suggestions_get_node": agent_suggestions_get_node,
            "watcher_signals_list_node": watcher_signals_list_node,
            "flow_runs_list_node": flow_runs_list_node,
            "flow_run_get_node": flow_run_get_node,
            "flow_run_history_node": flow_run_history_node,
            "flow_run_resume_node": flow_run_resume_node,
            "flow_registry_get_node": flow_registry_get_node,
            "memory_node_create_node": memory_node_create_node,
            "memory_node_get_node": memory_node_get_node,
            "memory_node_update_node": memory_node_update_node,
            "memory_node_history_node": memory_node_history_node,
            "memory_node_links_node": memory_node_links_node,
            "memory_nodes_search_tags_node": memory_nodes_search_tags_node,
            "memory_link_create_node": memory_link_create_node,
            "memory_node_traverse_node": memory_node_traverse_node,
            "memory_nodes_expand_node": memory_nodes_expand_node,
            "memory_nodes_search_similar_node": memory_nodes_search_similar_node,
            "memory_recall_node": memory_recall_node,
            "memory_recall_v3_node": memory_recall_v3_node,
            "memory_recall_federated_node": memory_recall_federated_node,
            "memory_agents_list_node": memory_agents_list_node,
            "memory_node_share_node": memory_node_share_node,
            "memory_agent_recall_node": memory_agent_recall_node,
            "memory_node_feedback_node": memory_node_feedback_node,
            "memory_node_performance_node": memory_node_performance_node,
            "memory_suggest_node": memory_suggest_node,
            "memory_nodus_execute_node": memory_nodus_execute_node,
            "automation_logs_list_node": automation_logs_list_node,
            "automation_log_get_node": automation_log_get_node,
            "automation_log_replay_node": automation_log_replay_node,
            "automation_scheduler_status_node": automation_scheduler_status_node,
            "automation_task_trigger_node": automation_task_trigger_node,
            "observability_scheduler_status_node": observability_scheduler_status_node,
            "observability_requests_node": observability_requests_node,
            "observability_dashboard_node": observability_dashboard_node,
            "observability_rippletrace_node": observability_rippletrace_node,
            "dashboard_overview_node": dashboard_overview_node,
            "autonomy_decisions_list_node": autonomy_decisions_list_node,
            "watcher_evaluate_trigger_node": watcher_evaluate_trigger_node,
            "watcher_record_decision_node": watcher_record_decision_node,
            "watcher_defer_job_node": watcher_defer_job_node,
            "watcher_ignore_node": watcher_ignore_node,
            "watcher_execute_wrap_node": watcher_execute_wrap_node,
            "health_dashboard_list_node": health_dashboard_list_node,
        }
    )
    register_single_node_flows(
        {
            "agent_run_create": "agent_run_create_node",
            "agent_runs_list": "agent_runs_list_node",
            "agent_run_get": "agent_run_get_node",
            "agent_run_approve": "agent_run_approve_node",
            "agent_run_reject": "agent_run_reject_node",
            "agent_run_recover": "agent_run_recover_node",
            "agent_run_replay": "agent_run_replay_node",
            "agent_run_steps": "agent_run_steps_node",
            "agent_run_events": "agent_run_events_node",
            "agent_tools_list": "agent_tools_list_node",
            "agent_trust_get": "agent_trust_get_node",
            "agent_trust_update": "agent_trust_update_node",
            "agent_suggestions_get": "agent_suggestions_get_node",
            "autonomy_decisions_list": "autonomy_decisions_list_node",
            "dashboard_overview": "dashboard_overview_node",
            "health_dashboard_list": "health_dashboard_list_node",
            "watcher_signals_list": "watcher_signals_list_node",
            "flow_runs_list": "flow_runs_list_node",
            "flow_run_get": "flow_run_get_node",
            "flow_run_history": "flow_run_history_node",
            "flow_run_resume": "flow_run_resume_node",
            "flow_registry_get": "flow_registry_get_node",
            "memory_node_create": "memory_node_create_node",
            "memory_node_get": "memory_node_get_node",
            "memory_node_update": "memory_node_update_node",
            "memory_node_history": "memory_node_history_node",
            "memory_node_links": "memory_node_links_node",
            "memory_nodes_search_tags": "memory_nodes_search_tags_node",
            "memory_link_create": "memory_link_create_node",
            "memory_node_traverse": "memory_node_traverse_node",
            "memory_nodes_expand": "memory_nodes_expand_node",
            "memory_nodes_search_similar": "memory_nodes_search_similar_node",
            "memory_recall": "memory_recall_node",
            "memory_recall_v3": "memory_recall_v3_node",
            "memory_recall_federated": "memory_recall_federated_node",
            "memory_agents_list": "memory_agents_list_node",
            "memory_node_share": "memory_node_share_node",
            "memory_agent_recall": "memory_agent_recall_node",
            "memory_node_feedback": "memory_node_feedback_node",
            "memory_node_performance": "memory_node_performance_node",
            "memory_suggest": "memory_suggest_node",
            "memory_nodus_execute": "memory_nodus_execute_node",
            "automation_logs_list": "automation_logs_list_node",
            "automation_log_get": "automation_log_get_node",
            "automation_log_replay": "automation_log_replay_node",
            "automation_scheduler_status": "automation_scheduler_status_node",
            "automation_task_trigger": "automation_task_trigger_node",
            "observability_scheduler_status": "observability_scheduler_status_node",
            "observability_requests": "observability_requests_node",
            "observability_dashboard": "observability_dashboard_node",
            "observability_execution_graph": "observability_rippletrace_node",
            "observability_rippletrace": "observability_rippletrace_node",
        }
    )

    if "memory_execute_loop" not in FLOW_REGISTRY:
        register_flow(
            "memory_execute_loop",
            {
                "start": "memory_execution_validate",
                "edges": {
                    "memory_execution_validate": ["memory_execution_run"],
                    "memory_execution_run": ["memory_execution_orchestrate"],
                },
                "end": ["memory_execution_orchestrate"],
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
