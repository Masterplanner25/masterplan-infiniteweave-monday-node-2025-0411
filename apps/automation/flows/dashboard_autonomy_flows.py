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
