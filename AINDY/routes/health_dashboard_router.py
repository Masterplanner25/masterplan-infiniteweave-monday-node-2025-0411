from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from core.execution_helper import execute_with_pipeline_sync
from db.database import get_db
from db.models.system_health_log import SystemHealthLog
from services.auth_service import get_current_user

router = APIRouter(prefix="/dashboard", tags=["Health Dashboard"], dependencies=[Depends(get_current_user)])


def _execute_health_dashboard(request: Request, route_name: str, handler, *, db: Session, user_id: str):
    return execute_with_pipeline_sync(
        request=request,
        route_name=route_name,
        handler=handler,
        user_id=user_id,
        metadata={"db": db, "source": "health_dashboard_router"},
    )

@router.get("/health")
def get_health_logs(request: Request, limit: int = 20, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
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
    def handler(_ctx):
        return {"count": len(formatted), "logs": formatted}
    return _execute_health_dashboard(request, "dashboard.health", handler, db=db, user_id=str(current_user["sub"]))
