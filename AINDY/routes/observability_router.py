from datetime import datetime, timedelta
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from db.database import get_db
from db.models.request_metric import RequestMetric
from services.auth_service import get_current_user


router = APIRouter(prefix="/observability", tags=["Observability"])


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

    def _serialize(row: RequestMetric) -> dict:
        return {
            "request_id": row.request_id,
            "method": row.method,
            "path": row.path,
            "status_code": row.status_code,
            "duration_ms": row.duration_ms,
            "created_at": row.created_at,
        }

    return {
        "summary": summary,
        "recent": [_serialize(row) for row in recent],
        "recent_errors": [_serialize(row) for row in recent_errors],
    }
