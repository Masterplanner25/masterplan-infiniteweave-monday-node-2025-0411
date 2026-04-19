"""
Flow Router — FlowRun visibility + control.

Exposes the execution backbone to authenticated users.
Every workflow execution creates a FlowRun — this router
makes those runs inspectable and controllable.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from AINDY.core.execution_helper import execute_with_pipeline
from AINDY.db.database import get_db
from AINDY.platform_layer.rate_limiter import limiter
from AINDY.services.auth_service import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/flows", tags=["Flow Engine"])


def _flow_failure(result: dict) -> str:
    direct_error = result.get("error")
    if isinstance(direct_error, str) and direct_error:
        return direct_error
    for key in ("data", "result"):
        payload = result.get(key)
        if isinstance(payload, dict):
            nested_error = payload.get("error") or payload.get("message")
            if isinstance(nested_error, str) and nested_error:
                return nested_error
    return ""


async def _execute_flow(request: Request, route_name: str, handler, *, user_id: str, db: Session | None = None):
    metadata = {"source": "flow_router"}
    if db is not None:
        metadata["db"] = db
    return await execute_with_pipeline(
        request=request,
        route_name=route_name,
        handler=handler,
        user_id=user_id,
        metadata=metadata,
    )


@router.get("/runs")
@limiter.limit("60/minute")
async def list_flow_runs(
    request: Request,
    status: Optional[str] = None,
    workflow_type: Optional[str] = None,
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """List flow runs for the current user."""
    def handler(_ctx):
        from AINDY.runtime.flow_engine import run_flow
        result = run_flow("flow_runs_list", {"status": status, "workflow_type": workflow_type, "limit": limit}, db=db, user_id=str(current_user["sub"]))
        if result.get("status") == "FAILED":
            error = _flow_failure(result)
            if error.startswith("HTTP_"):
                code, _, detail = error.partition(":")
                raise HTTPException(status_code=int(code.replace("HTTP_", "")), detail=detail or error)
            raise HTTPException(status_code=500, detail=error or "Flow runs list failed")
        return result.get("data")
    return await _execute_flow(request, "flow.runs.list", handler, user_id=str(current_user["sub"]), db=db)


@router.get("/runs/{run_id}")
@limiter.limit("60/minute")
async def get_flow_run(
    request: Request,
    run_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get a single flow run with full state."""
    def handler(_ctx):
        from AINDY.runtime.flow_engine import run_flow
        result = run_flow("flow_run_get", {"run_id": run_id}, db=db, user_id=str(current_user["sub"]))
        if result.get("status") == "FAILED":
            error = _flow_failure(result)
            raise HTTPException(404 if "404" in error else 500, error or "Flow run not found")
        return result.get("data")
    return await _execute_flow(request, "flow.runs.get", handler, user_id=str(current_user["sub"]), db=db)


@router.get("/runs/{run_id}/history")
@limiter.limit("60/minute")
async def get_flow_run_history(
    request: Request,
    run_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get the node execution history for a flow run."""
    def handler(_ctx):
        from AINDY.runtime.flow_engine import run_flow
        result = run_flow("flow_run_history", {"run_id": run_id}, db=db, user_id=str(current_user["sub"]))
        if result.get("status") == "FAILED":
            error = _flow_failure(result)
            raise HTTPException(404 if "404" in error else 500, error or "Flow run not found")
        return result.get("data")
    return await _execute_flow(request, "flow.runs.history", handler, user_id=str(current_user["sub"]), db=db)


class ResumeRequest(BaseModel):
    event_type: str
    payload: dict = {}


@router.post("/runs/{run_id}/resume")
@limiter.limit("30/minute")
async def resume_flow_run(
    request: Request,
    run_id: str,
    body: ResumeRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Resume a waiting flow run with an event."""
    def handler(_ctx):
        from AINDY.runtime.flow_engine import run_flow
        from AINDY.core.execution_gate import require_execution_unit
        # EU gate: attach to the existing FlowRun being resumed (non-fatal)
        require_execution_unit(
            db=db,
            eu_type="flow",
            user_id=str(current_user["sub"]),
            source_type="flow_run",
            source_id=run_id,
            correlation_id=run_id,
            extra={"workflow_type": "flow_resume", "event_type": body.event_type},
        )
        result = run_flow(
            "flow_run_resume",
            {"run_id": run_id, "event_type": body.event_type, "payload": body.payload},
            db=db,
            user_id=str(current_user["sub"]),
        )
        if result.get("status") == "FAILED":
            error = _flow_failure(result)
            if "404" in error:
                raise HTTPException(404, "Flow run not found")
            if "400" in error:
                raise HTTPException(400, error.split(":", 1)[-1] if ":" in error else error)
            raise HTTPException(500, "Resume failed")
        data = result.get("data") or {}
        if isinstance(data, dict):
            # Use to_envelope with output=None: data IS the output, embedding
            # flow_result_to_envelope() would create a circular reference via output→data.
            from AINDY.core.execution_gate import to_envelope
            data.setdefault("execution_envelope", to_envelope(
                eu_id=result.get("run_id"),
                trace_id=result.get("trace_id"),
                status=str(result.get("status") or "UNKNOWN").upper(),
                output=None,
                error=result.get("error"),
                duration_ms=None,
                attempt_count=None,
            ))
        return data
    return await _execute_flow(request, "flow.runs.resume", handler, user_id=str(current_user["sub"]), db=db)


@router.get("/registry")
@limiter.limit("60/minute")
async def get_flow_registry(
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """List all registered flows and nodes."""
    def handler(_ctx):
        from AINDY.runtime.flow_engine import run_flow
        result = run_flow("flow_registry_get", {}, db=db, user_id=str(current_user["sub"]))
        if result.get("status") == "FAILED":
            raise HTTPException(status_code=500, detail="Registry fetch failed")
        return result.get("data")
    return await _execute_flow(request, "flow.registry", handler, user_id=str(current_user["sub"]), db=db)

