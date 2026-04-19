import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from AINDY.core.execution_helper import execute_with_pipeline_sync
from AINDY.db.database import get_db
from AINDY.platform_layer.rate_limiter import limiter
from AINDY.services.auth_service import get_current_user

router = APIRouter(prefix="/observability", tags=["Observability"])


class DrainDlqRequest(BaseModel):
    max_items: int = Field(default=10, ge=1, le=100)
    requeue: bool = False


def _run_flow_observability(flow_name: str, payload: dict, db: Session, user_id: str):
    from AINDY.runtime.flow_engine import run_flow
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
        metadata={"db": db, "disable_memory_capture": True},
    )


# ------------------------------
# SCHEDULER STATUS
# ------------------------------
@router.get("/scheduler/status")
@limiter.limit("60/minute")
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
@limiter.limit("60/minute")
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
@limiter.limit("60/minute")
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
# EXECUTION GRAPH
# ------------------------------
@router.get("/execution_graph/{trace_id}")
@limiter.limit("60/minute")
def get_execution_graph(
    request: Request,
    trace_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])
    def handler(ctx):
        return _run_flow_observability("observability_execution_graph", {"trace_id": trace_id}, db, user_id)
    return _execute_observability(request, "observability_execution_graph", handler, db=db, user_id=user_id,
                                  input_payload={"trace_id": trace_id})


@router.get("/queue/metrics")
@limiter.limit("60/minute")
def get_queue_metrics(
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    from AINDY.core.distributed_queue import get_queue
    from AINDY.worker.worker_loop import get_failure_rate_stats

    user_id = str(current_user["sub"])

    def handler(ctx):
        metrics = dict(get_queue().get_metrics())
        metrics.update(get_failure_rate_stats())
        return metrics

    return _execute_observability(
        request,
        "observability_queue_metrics",
        handler,
        db=db,
        user_id=user_id,
    )


@router.post("/queue/dlq/drain")
@limiter.limit("30/minute")
def drain_queue_dlq(
    request: Request,
    body: DrainDlqRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    from AINDY.worker.worker_loop import drain_dead_letters

    user_id = str(current_user["sub"])
    logger_payload = {
        "user_id": user_id,
        "max_items": body.max_items,
        "requeue": body.requeue,
    }

    def handler(ctx):
        return drain_dead_letters(
            db=db,
            max_items=body.max_items,
            requeue=body.requeue,
        )

    result = _execute_observability(
        request,
        "observability_queue_dlq_drain",
        handler,
        db=db,
        user_id=user_id,
        input_payload=body.model_dump(),
    )
    import logging
    logging.getLogger(__name__).info(
        "[Observability] queue_drain_dlq user_id=%s max_items=%s requeue=%s inspected=%s requeued=%s",
        logger_payload["user_id"],
        logger_payload["max_items"],
        logger_payload["requeue"],
        result.get("inspected"),
        result.get("requeued"),
    )
    return result

