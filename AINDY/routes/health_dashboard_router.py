from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from db.database import get_db
from db.models.system_health_log import SystemHealthLog

router = APIRouter(prefix="/dashboard", tags=["Health Dashboard"])

@router.get("/health")
def get_health_logs(limit: int = 20, db: Session = Depends(get_db)):
    """
    Returns the latest system health logs for dashboard visualization.
    """
    logs = (
        db.query(SystemHealthLog)
        .order_by(SystemHealthLog.timestamp.desc())
        .limit(limit)
        .all()
    )

    formatted = [
        {
            "timestamp": log.timestamp.isoformat(),
            "status": log.status,
            "avg_latency_ms": log.avg_latency_ms,
            "components": log.components,
            "api_endpoints": log.api_endpoints,
        }
        for log in logs
    ]
    return {"count": len(formatted), "logs": formatted}
