from datetime import datetime, timedelta, timezone
import uuid

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from core.execution_helper import execute_with_pipeline
from db.database import get_db
from db.models.background_task_lease import BackgroundTaskLease
from db.models.agent_event import AgentEvent
from db.models.flow_run import FlowRun
from db.models.request_metric import RequestMetric
from db.models.system_event import SystemEvent
from db.models.system_health_log import SystemHealthLog
from services.auth_service import get_current_user
from services.rippletrace_service import (
    build_trace_graph,
    calculate_ripple_span,
    detect_root_event,
    detect_terminal_events,
    generate_trace_insights,
)
import services.scheduler_service as scheduler_service
import services.task_services as task_services


router = APIRouter(prefix="/observability", tags=["Observability"])


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _serialize_request_metric(row: RequestMetric) -> dict:
    return {
        "request_id": row.request_id,
        "trace_id": row.trace_id,
        "method": row.method,
        "path": row.path,
        "status_code": row.status_code,
        "duration_ms": row.duration_ms,
        "created_at": row.created_at,
    }


def _serialize_system_event(row: SystemEvent) -> dict:
    payload = row.payload or {}
    return {
        "id": str(row.id),
        "type": row.type,
        "trace_id": row.trace_id,
        "timestamp": row.timestamp.isoformat() if row.timestamp else None,
        "payload": payload,
    }


def _serialize_agent_projection(row: AgentEvent) -> dict:
    return {
        "id": str(row.id),
        "run_id": str(row.run_id),
        "trace_id": row.correlation_id,
        "event_type": row.event_type,
        "system_event_id": str(row.system_event_id) if getattr(row, "system_event_id", None) else None,
        "timestamp": row.occurred_at.isoformat() if row.occurred_at else None,
        "payload": row.payload or {},
    }


# ------------------------------
# SCHEDULER STATUS
# ------------------------------
@router.get("/scheduler/status")
def get_scheduler_status(
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    def handler(ctx):
        try:
            sched = scheduler_service.get_scheduler()
            scheduler_running = sched.running
        except RuntimeError:
            scheduler_running = False

        lease_row = (
            db.query(BackgroundTaskLease)
            .filter(BackgroundTaskLease.name == task_services._BACKGROUND_LEASE_NAME)
            .first()
        )

        lease = None
        if lease_row:
            lease = {
                "owner_id": lease_row.owner_id,
                "acquired_at": lease_row.acquired_at.isoformat() if lease_row.acquired_at else None,
                "heartbeat_at": lease_row.heartbeat_at.isoformat() if lease_row.heartbeat_at else None,
                "expires_at": lease_row.expires_at.isoformat() if lease_row.expires_at else None,
            }

        return {
            "scheduler_running": scheduler_running,
            "is_leader": task_services.is_background_leader(),
            "lease": lease,
        }

    return execute_with_pipeline(request, "observability_scheduler_status", handler)


# ------------------------------
# REQUEST METRICS
# ------------------------------
@router.get("/requests")
def get_request_metrics(
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    limit: int = Query(50, ge=1, le=200),
    error_limit: int = Query(25, ge=1, le=200),
    window_hours: int = Query(24, ge=1, le=168),
):
    def handler(ctx):
        user_id = uuid.UUID(str(current_user["sub"]))
        window_start = datetime.utcnow() - timedelta(hours=window_hours)

        base_query = db.query(RequestMetric).filter(RequestMetric.user_id == user_id)

        total = base_query.count()
        window_total = base_query.filter(RequestMetric.created_at >= window_start).count()
        error_total = base_query.filter(RequestMetric.status_code >= 500).count()
        window_error_total = base_query.filter(
            RequestMetric.created_at >= window_start,
            RequestMetric.status_code >= 500,
        ).count()

        avg_latency = (
            db.query(func.avg(RequestMetric.duration_ms))
            .filter(RequestMetric.user_id == user_id)
            .scalar()
        )

        recent = base_query.order_by(RequestMetric.created_at.desc()).limit(limit).all()
        recent_errors = (
            base_query.filter(RequestMetric.status_code >= 500)
            .order_by(RequestMetric.created_at.desc())
            .limit(error_limit)
            .all()
        )

        return {
            "summary": {
                "total_requests": total,
                "window_hours": window_hours,
                "window_requests": window_total,
                "total_errors": error_total,
                "window_errors": window_error_total,
                "avg_latency_ms": round(avg_latency or 0.0, 2),
            },
            "recent": [_serialize_request_metric(row) for row in recent],
            "recent_errors": [_serialize_request_metric(row) for row in recent_errors],
        }

    return execute_with_pipeline(request, "observability_requests", handler)


# ------------------------------
# DASHBOARD
# ------------------------------
@router.get("/dashboard")
def get_observability_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    window_hours: int = Query(24, ge=1, le=168),
    request_limit: int = Query(80, ge=1, le=200),
    event_limit: int = Query(60, ge=1, le=200),
    agent_limit: int = Query(30, ge=1, le=100),
    health_limit: int = Query(20, ge=1, le=100),
):
    def handler(ctx):
        user_id = uuid.UUID(str(current_user["sub"]))
        request_window_start = datetime.utcnow() - timedelta(hours=window_hours)
        event_window_start = _utcnow() - timedelta(hours=window_hours)

        request_query = db.query(RequestMetric).filter(RequestMetric.user_id == user_id)

        recent_requests = request_query.order_by(RequestMetric.created_at.desc()).limit(request_limit).all()
        recent_errors = (
            request_query.filter(RequestMetric.status_code >= 500)
            .order_by(RequestMetric.created_at.desc())
            .limit(min(request_limit, 25))
            .all()
        )

        avg_latency = (
            db.query(func.avg(RequestMetric.duration_ms))
            .filter(
                RequestMetric.user_id == user_id,
                RequestMetric.created_at >= request_window_start,
            )
            .scalar()
        )

        window_requests = request_query.filter(RequestMetric.created_at >= request_window_start).count()
        window_errors = request_query.filter(
            RequestMetric.created_at >= request_window_start,
            RequestMetric.status_code >= 500,
        ).count()

        system_events = (
            db.query(SystemEvent)
            .filter(
                SystemEvent.user_id == user_id,
                SystemEvent.timestamp >= event_window_start,
            )
            .order_by(SystemEvent.timestamp.desc())
            .limit(event_limit)
            .all()
        )

        flow_rows = (
            db.query(FlowRun)
            .filter(
                FlowRun.user_id == user_id,
                FlowRun.created_at >= event_window_start,
            )
            .order_by(FlowRun.created_at.desc())
            .limit(100)
            .all()
        )

        return {
            "summary": {
                "window_hours": window_hours,
                "avg_latency_ms": round(avg_latency or 0.0, 2),
                "window_requests": window_requests,
                "window_errors": window_errors,
                "error_rate_pct": round((window_errors / window_requests) * 100, 2) if window_requests else 0.0,
                "active_flows": sum(1 for row in flow_rows if row.status in {"running", "waiting"}),
                "system_event_total": len(system_events),
            }
        }

    return execute_with_pipeline(request, "observability_dashboard", handler)


# ------------------------------
# RIPPLETRACE
# ------------------------------
@router.get("/rippletrace/{trace_id}")
def get_rippletrace_graph(
    request: Request,
    trace_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    def handler(ctx):
        user_id = uuid.UUID(str(current_user["sub"]))

        events = (
            db.query(SystemEvent)
            .filter(SystemEvent.trace_id == trace_id, SystemEvent.user_id == user_id)
            .count()
        )

        if events == 0:
            return {
                "trace_id": trace_id,
                "nodes": [],
                "edges": [],
                "root_event": None,
                "terminal_events": [],
                "ripple_span": {"node_count": 0, "edge_count": 0, "depth": 0, "terminal_count": 0},
            }

        graph = build_trace_graph(db, trace_id)

        return {
            "trace_id": trace_id,
            "nodes": graph["nodes"],
            "edges": graph["edges"],
            "root_event": detect_root_event(db, trace_id),
            "terminal_events": detect_terminal_events(db, trace_id),
            "ripple_span": calculate_ripple_span(db, trace_id),
            "insights": generate_trace_insights(db, trace_id),
        }

    return execute_with_pipeline(request, "observability_rippletrace", handler)
