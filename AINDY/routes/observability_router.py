import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from core.execution_helper import execute_with_pipeline_sync
from db.database import get_db
from services.auth_service import get_current_user

router = APIRouter(prefix="/observability", tags=["Observability"])


def _run_flow_observability(flow_name: str, payload: dict, db: Session, user_id: str):
    from runtime.flow_engine import run_flow
    result = run_flow(flow_name, payload, db=db, user_id=user_id)
    if result.get("status") == "FAILED":
        error = result.get("error", "")
        if error.startswith("HTTP_"):
            parts = error.split(":", 1)
            code = int(parts[0].replace("HTTP_", ""))
            msg = parts[1] if len(parts) > 1 else error
            raise HTTPException(status_code=code, detail=msg)
        raise HTTPException(status_code=500, detail=error or f"{flow_name} failed")
    return result.get("data")


def _execute_observability(request: Request, route_name: str, handler, *, db: Session, user_id: str, input_payload=None):
    return execute_with_pipeline_sync(
        request=request,
        route_name=route_name,
        handler=handler,
        user_id=user_id,
        input_payload=input_payload,
        metadata={"db": db},
    )


# ------------------------------
# SCHEDULER STATUS
# ------------------------------
@router.get("/scheduler/status")
def get_scheduler_status(
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])
    def handler(ctx):
        return _run_flow_observability("observability_scheduler_status", {}, db, user_id)
    return _execute_observability(request, "observability_scheduler_status", handler, db=db, user_id=user_id)


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
    user_id = str(current_user["sub"])
    def handler(ctx):
        return _run_flow_observability(
            "observability_requests",
            {"limit": limit, "error_limit": error_limit, "window_hours": window_hours},
            db, user_id,
        )
    return _execute_observability(request, "observability_requests", handler, db=db, user_id=user_id)


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
    user_id = str(current_user["sub"])
    def handler(ctx):
        return _run_flow_observability(
            "observability_dashboard",
            {"window_hours": window_hours, "request_limit": request_limit, "event_limit": event_limit},
            db, user_id,
        )
    return _execute_observability(request, "observability_dashboard", handler, db=db, user_id=user_id)


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
    user_id = str(current_user["sub"])
    def handler(ctx):
        return _run_flow_observability("observability_rippletrace", {"trace_id": trace_id}, db, user_id)
    return _execute_observability(request, "observability_rippletrace", handler, db=db, user_id=user_id,
                                  input_payload={"trace_id": trace_id})

