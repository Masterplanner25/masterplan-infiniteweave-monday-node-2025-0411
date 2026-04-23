import logging

from AINDY.runtime.flow_engine import FLOW_REGISTRY, register_flow
from AINDY.runtime.flow_helpers import (
    register_nodes,
    register_single_node_flows,
)

logger = logging.getLogger(__name__)


# -- Node functions -----------------------------------------------------------

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


# -- Registration -------------------------------------------------------------

def register() -> None:
    register_nodes(
        {
            "observability_scheduler_status_node": observability_scheduler_status_node,
            "observability_dashboard_node": observability_dashboard_node,
            "observability_requests_node": observability_requests_node,
            "observability_rippletrace_node": observability_rippletrace_node,
        }
    )
    register_single_node_flows(
        {
            "observability_scheduler_status": "observability_scheduler_status_node",
            "observability_requests": "observability_requests_node",
            "observability_dashboard": "observability_dashboard_node",
            "observability_execution_graph": "observability_rippletrace_node",
            "observability_rippletrace": "observability_rippletrace_node",
        }
    )
