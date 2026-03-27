from datetime import datetime, timedelta, timezone
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from db.database import get_db
from db.models.background_task_lease import BackgroundTaskLease
from db.models.agent_event import AgentEvent
from db.models.flow_run import FlowRun
from db.models.request_metric import RequestMetric
from db.models.system_event import SystemEvent
from db.models.system_health_log import SystemHealthLog
from services.auth_service import get_current_user
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


@router.get("/scheduler/status")
def get_scheduler_status(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Return current APScheduler state and background lease info."""
    # Scheduler running state
    try:
        sched = scheduler_service.get_scheduler()
        scheduler_running = sched.running
    except RuntimeError:
        scheduler_running = False

    # Lease row
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


@router.get("/requests")
def get_request_metrics(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    limit: int = Query(50, ge=1, le=200),
    error_limit: int = Query(25, ge=1, le=200),
    window_hours: int = Query(24, ge=1, le=168),
):
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

    recent = (
        base_query.order_by(RequestMetric.created_at.desc())
        .limit(limit)
        .all()
    )

    recent_errors = (
        base_query.filter(RequestMetric.status_code >= 500)
        .order_by(RequestMetric.created_at.desc())
        .limit(error_limit)
        .all()
    )

    summary = {
        "total_requests": total,
        "window_hours": window_hours,
        "window_requests": window_total,
        "total_errors": error_total,
        "window_errors": window_error_total,
        "avg_latency_ms": round(avg_latency or 0.0, 2),
    }

    return {
        "summary": summary,
        "recent": [_serialize_request_metric(row) for row in recent],
        "recent_errors": [_serialize_request_metric(row) for row in recent_errors],
    }


@router.get("/dashboard")
def get_observability_dashboard(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    window_hours: int = Query(24, ge=1, le=168),
    request_limit: int = Query(80, ge=1, le=200),
    event_limit: int = Query(60, ge=1, le=200),
    agent_limit: int = Query(30, ge=1, le=100),
    health_limit: int = Query(20, ge=1, le=100),
):
    user_id = uuid.UUID(str(current_user["sub"]))
    request_window_start = datetime.utcnow() - timedelta(hours=window_hours)
    event_window_start = _utcnow() - timedelta(hours=window_hours)

    request_query = db.query(RequestMetric).filter(RequestMetric.user_id == user_id)
    recent_requests = (
        request_query.order_by(RequestMetric.created_at.desc()).limit(request_limit).all()
    )
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

    error_points_rows = (
        request_query.filter(RequestMetric.created_at >= request_window_start)
        .order_by(RequestMetric.created_at.asc())
        .all()
    )
    error_points = [
        {
            "label": row.created_at.isoformat() if row.created_at else None,
            "errors": 1 if row.status_code >= 500 else 0,
            "requests": 1,
            "error_rate": 100.0 if row.status_code >= 500 else 0.0,
            "path": row.path,
            "trace_id": row.trace_id,
        }
        for row in error_points_rows
    ]

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

    loop_events = [event for event in system_events if event.type.startswith("loop.")]
    loop_activity = [_serialize_system_event(event) for event in loop_events]

    agent_rows = (
        db.query(AgentEvent)
        .filter(AgentEvent.user_id == user_id)
        .order_by(AgentEvent.occurred_at.desc())
        .limit(agent_limit)
        .all()
    )
    agent_timeline = [
        {
            "id": str(row.id),
            "run_id": str(row.run_id),
            "trace_id": row.correlation_id,
            "event_type": row.event_type,
            "timestamp": row.occurred_at.isoformat() if row.occurred_at else None,
            "payload": row.payload or {},
        }
        for row in agent_rows
    ]

    health_rows = (
        db.query(SystemHealthLog)
        .order_by(SystemHealthLog.timestamp.desc())
        .limit(health_limit)
        .all()
    )
    health_logs = [
        {
            "timestamp": row.timestamp.isoformat() if row.timestamp else None,
            "status": row.status,
            "avg_latency_ms": row.avg_latency_ms,
            "components": row.components or {},
            "api_endpoints": row.api_endpoints or {},
        }
        for row in health_rows
    ]
    latest_health = health_logs[0] if health_logs else None

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
    flow_status = {}
    for row in flow_rows:
        key = row.status or "unknown"
        flow_status[key] = flow_status.get(key, 0) + 1

    system_event_counts = {}
    for row in system_events:
        system_event_counts[row.type] = system_event_counts.get(row.type, 0) + 1

    return {
        "summary": {
            "window_hours": window_hours,
            "avg_latency_ms": round(avg_latency or 0.0, 2),
            "window_requests": window_requests,
            "window_errors": window_errors,
            "error_rate_pct": round((window_errors / window_requests) * 100, 2) if window_requests else 0.0,
            "active_flows": sum(1 for row in flow_rows if row.status in {"running", "waiting"}),
            "loop_events": len(loop_activity),
            "agent_events": len(agent_timeline),
            "system_event_total": len(system_events),
            "health_status": latest_health["status"] if latest_health else "unknown",
        },
        "request_metrics": {
            "recent": [_serialize_request_metric(row) for row in recent_requests],
            "recent_errors": [_serialize_request_metric(row) for row in recent_errors],
            "error_rate_series": error_points,
        },
        "loop_activity": loop_activity,
        "agent_timeline": agent_timeline,
        "system_events": {
            "recent": [_serialize_system_event(row) for row in system_events],
            "counts": system_event_counts,
        },
        "system_health": {
            "latest": latest_health,
            "logs": health_logs,
        },
        "flows": {
            "status_counts": flow_status,
            "recent": [
                {
                    "id": row.id,
                    "trace_id": row.trace_id,
                    "flow_name": row.flow_name,
                    "workflow_type": row.workflow_type,
                    "status": row.status,
                    "current_node": row.current_node,
                    "waiting_for": row.waiting_for,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "completed_at": row.completed_at.isoformat() if row.completed_at else None,
                }
                for row in flow_rows[:20]
            ],
        },
    }
