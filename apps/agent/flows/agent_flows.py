import logging

from AINDY.runtime.flow_engine import FLOW_REGISTRY, register_flow
from AINDY.runtime.flow_helpers import (
    register_nodes,
    register_single_node_flows,
)

logger = logging.getLogger(__name__)


# -- Node functions -----------------------------------------------------------

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
        from apps.agent.models.agent_run import AgentRun
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
        from apps.agent.models.agent_run import AgentRun
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
        from apps.agent.models.agent_run import AgentRun, AgentStep
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
        from apps.agent.models.agent_run import AgentRun
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
        from apps.agent.models.agent_run import AgentTrustSettings
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
        from apps.agent.models.agent_run import AgentTrustSettings
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
        from AINDY.kernel.syscall_dispatcher import get_dispatcher, make_syscall_ctx_from_flow
        from AINDY.utils.uuid_utils import normalize_uuid

        db = context.get("db")
        user_id = normalize_uuid(context.get("user_id"))
        syscall_ctx = make_syscall_ctx_from_flow(context, capabilities=["analytics.read"])
        syscall_ctx.metadata["_db"] = db
        result = get_dispatcher().dispatch(
            "sys.v1.analytics.get_kpi_snapshot",
            {"user_id": str(user_id)},
            syscall_ctx,
        )
        snapshot = result.get("data") if result.get("status") == "success" else None
        suggestions = suggest_tools(kpi_snapshot=snapshot, user_id=user_id, db=db)
        return {"status": "SUCCESS", "output_patch": {"agent_suggestions_get_result": suggestions}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


# -- Registration -------------------------------------------------------------

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
        }
    )
