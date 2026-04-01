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

from core.execution_helper import execute_with_pipeline
from db.database import get_db
from services.auth_service import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/flows", tags=["Flow Engine"])


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
        from services.flow_engine import run_flow
        result = run_flow("flow_runs_list", {"status": status, "workflow_type": workflow_type, "limit": limit}, db=db, user_id=str(current_user["sub"]))
        if result.get("status") == "FAILED":
            raise HTTPException(status_code=500, detail="Flow runs list failed")
        return result.get("data")
    return await _execute_flow(request, "flow.runs.list", handler, user_id=str(current_user["sub"]), db=db)


@router.get("/runs/{run_id}")
async def get_flow_run(
    request: Request,
    run_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get a single flow run with full state."""
    def handler(_ctx):
        from services.flow_engine import run_flow
        result = run_flow("flow_run_get", {"run_id": run_id}, db=db, user_id=str(current_user["sub"]))
        if result.get("status") == "FAILED":
            error = result.get("error", "")
            raise HTTPException(404 if "404" in error else 500, error or "Flow run not found")
        return result.get("data")
    return await _execute_flow(request, "flow.runs.get", handler, user_id=str(current_user["sub"]), db=db)


@router.get("/runs/{run_id}/history")
async def get_flow_run_history(
    request: Request,
    run_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get the node execution history for a flow run."""
    def handler(_ctx):
        from services.flow_engine import run_flow
        result = run_flow("flow_run_history", {"run_id": run_id}, db=db, user_id=str(current_user["sub"]))
        if result.get("status") == "FAILED":
            error = result.get("error", "")
            raise HTTPException(404 if "404" in error else 500, error or "Flow run not found")
        return result.get("data")
    return await _execute_flow(request, "flow.runs.history", handler, user_id=str(current_user["sub"]), db=db)


class ResumeRequest(BaseModel):
    event_type: str
    payload: dict = {}


@router.post("/runs/{run_id}/resume")
async def resume_flow_run(
    request: Request,
    run_id: str,
    body: ResumeRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Resume a waiting flow run with an event."""
    def handler(_ctx):
        from services.flow_engine import run_flow
        result = run_flow(
            "flow_run_resume",
            {"run_id": run_id, "event_type": body.event_type, "payload": body.payload},
            db=db,
            user_id=str(current_user["sub"]),
        )
        if result.get("status") == "FAILED":
            error = result.get("error", "")
            if "404" in error:
                raise HTTPException(404, "Flow run not found")
            if "400" in error:
                raise HTTPException(400, error.split(":", 1)[-1] if ":" in error else error)
            raise HTTPException(500, "Resume failed")
        return result.get("data")
    return await _execute_flow(request, "flow.runs.resume", handler, user_id=str(current_user["sub"]), db=db)


@router.get("/registry")
async def get_flow_registry(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """List all registered flows and nodes."""
    def handler(_ctx):
        from services.flow_engine import run_flow
        result = run_flow("flow_registry_get", {}, user_id=str(current_user["sub"]))
        if result.get("status") == "FAILED":
            raise HTTPException(status_code=500, detail="Registry fetch failed")
        return result.get("data")
    return await _execute_flow(request, "flow.registry", handler, user_id=str(current_user["sub"]))
