import logging

from AINDY.runtime.flow_engine import FLOW_REGISTRY, register_flow
from AINDY.runtime.flow_helpers import (
    register_nodes,
    register_single_node_flows,
)

logger = logging.getLogger(__name__)


# -- Node functions -----------------------------------------------------------

def dashboard_overview_node(state, context):
    try:
        from datetime import datetime, timezone

        from AINDY.kernel.syscall_dispatcher import (
            SyscallContext,
            get_dispatcher,
            make_syscall_ctx_from_flow,
        )

        user_id = str(context.get("user_id") or "")
        base_ctx = make_syscall_ctx_from_flow(
            context,
            capabilities=["authorship.read", "rippletrace.read"],
        )
        ctx = SyscallContext(
            execution_unit_id=base_ctx.execution_unit_id,
            user_id=base_ctx.user_id,
            capabilities=base_ctx.capabilities,
            trace_id=base_ctx.trace_id,
            memory_context=base_ctx.memory_context,
            metadata={
                **(base_ctx.metadata or {}),
                "_db": context.get("db"),
            },
        )
        dispatcher = get_dispatcher()

        authors_result = dispatcher.dispatch(
            "sys.v1.authorship.list_authors",
            {"user_id": user_id, "limit": 10},
            ctx,
        )
        author_list = authors_result.get("data", {}).get("authors", []) if authors_result.get("status") == "success" else []

        pings_result = dispatcher.dispatch(
            "sys.v1.rippletrace.list_recent_pings",
            {"user_id": user_id, "limit": 10},
            ctx,
        )
        ripple_list = pings_result.get("data", {}).get("pings", []) if pings_result.get("status") == "success" else []

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


# -- Registration -------------------------------------------------------------

def register() -> None:
    register_nodes(
        {
            "dashboard_overview_node": dashboard_overview_node,
            "autonomy_decisions_list_node": autonomy_decisions_list_node,
            "health_dashboard_list_node": health_dashboard_list_node,
        }
    )
    register_single_node_flows(
        {
            "autonomy_decisions_list": "autonomy_decisions_list_node",
            "dashboard_overview": "dashboard_overview_node",
            "health_dashboard_list": "health_dashboard_list_node",
        }
    )
