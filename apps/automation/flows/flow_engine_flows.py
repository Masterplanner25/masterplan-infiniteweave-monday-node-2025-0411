import logging

from AINDY.runtime.flow_engine import FLOW_REGISTRY, register_flow
from apps.automation.flows._flow_registration import (
    register_nodes,
    register_single_node_flows,
)

logger = logging.getLogger(__name__)


# -- Node functions -----------------------------------------------------------

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


# -- Registration -------------------------------------------------------------

def register() -> None:
    register_nodes(
        {
            "flow_runs_list_node": flow_runs_list_node,
            "flow_run_get_node": flow_run_get_node,
            "flow_run_history_node": flow_run_history_node,
            "flow_run_resume_node": flow_run_resume_node,
            "flow_registry_get_node": flow_registry_get_node,
        }
    )
    register_single_node_flows(
        {
            "flow_runs_list": "flow_runs_list_node",
            "flow_run_get": "flow_run_get_node",
            "flow_run_history": "flow_run_history_node",
            "flow_run_resume": "flow_run_resume_node",
            "flow_registry_get": "flow_registry_get_node",
        }
    )
