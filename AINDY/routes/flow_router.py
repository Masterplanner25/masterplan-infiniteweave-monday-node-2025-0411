"""
Flow Router — FlowRun visibility + control.

Exposes the execution backbone to authenticated users.
Every workflow execution creates a FlowRun — this router
makes those runs inspectable and controllable.
"""
import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db.database import get_db
from db.models.flow_run import FlowHistory, FlowRun
from services.auth_service import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/flows", tags=["Flow Engine"])


@router.get("/runs")
async def list_flow_runs(
    status: Optional[str] = None,
    workflow_type: Optional[str] = None,
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    List flow runs for the current user.
    Shows all workflow executions — running, waiting, succeeded, failed.
    """
    query = db.query(FlowRun).filter(
        FlowRun.user_id == UUID(str(current_user["sub"]))
    )
    if status:
        query = query.filter(FlowRun.status == status)
    if workflow_type:
        query = query.filter(FlowRun.workflow_type == workflow_type)

    runs = query.order_by(FlowRun.created_at.desc()).limit(limit).all()

    return {
        "runs": [
            {
                "id": r.id,
                "flow_name": r.flow_name,
                "workflow_type": r.workflow_type,
                "status": r.status,
                "trace_id": r.trace_id,
                "current_node": r.current_node,
                "waiting_for": r.waiting_for,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "completed_at": r.completed_at.isoformat()
                if r.completed_at
                else None,
                "error_message": r.error_message,
            }
            for r in runs
        ],
        "count": len(runs),
    }


@router.get("/runs/{run_id}")
async def get_flow_run(
    run_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get a single flow run with full state."""
    run = (
        db.query(FlowRun)
        .filter(
            FlowRun.id == run_id,
            FlowRun.user_id == UUID(str(current_user["sub"])),
        )
        .first()
    )

    if not run:
        raise HTTPException(404, "Flow run not found")

    return {
        "id": run.id,
        "flow_name": run.flow_name,
        "workflow_type": run.workflow_type,
        "status": run.status,
        "trace_id": run.trace_id,
        "current_node": run.current_node,
        "waiting_for": run.waiting_for,
        "state": run.state,
        "error_message": run.error_message,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "updated_at": run.updated_at.isoformat() if run.updated_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }


@router.get("/runs/{run_id}/history")
async def get_flow_run_history(
    run_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Get the node execution history for a flow run.
    Shows every node that executed, its status, input/output, and execution time.
    """
    # Verify ownership
    run = (
        db.query(FlowRun)
        .filter(
            FlowRun.id == run_id,
            FlowRun.user_id == UUID(str(current_user["sub"])),
        )
        .first()
    )

    if not run:
        raise HTTPException(404, "Flow run not found")

    history = (
        db.query(FlowHistory)
        .filter(FlowHistory.flow_run_id == run_id)
        .order_by(FlowHistory.created_at.asc())
        .all()
    )

    return {
        "run_id": run_id,
        "trace_id": run.trace_id,
        "flow_name": run.flow_name,
        "workflow_type": run.workflow_type,
        "history": [
            {
                "id": h.id,
                "node_name": h.node_name,
                "status": h.status,
                "execution_time_ms": h.execution_time_ms,
                "output_patch": h.output_patch,
                "error_message": h.error_message,
                "created_at": h.created_at.isoformat() if h.created_at else None,
            }
            for h in history
        ],
        "node_count": len(history),
    }


class ResumeRequest(BaseModel):
    event_type: str
    payload: dict = {}


@router.post("/runs/{run_id}/resume")
async def resume_flow_run(
    run_id: str,
    body: ResumeRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Resume a waiting flow run with an event.

    Used when a flow is in WAIT state waiting for user input or an external
    event. Send the event payload here to resume execution.
    """
    run = (
        db.query(FlowRun)
        .filter(
            FlowRun.id == run_id,
            FlowRun.user_id == UUID(str(current_user["sub"])),
        )
        .first()
    )

    if not run:
        raise HTTPException(404, "Flow run not found")

    if run.status != "waiting":
        raise HTTPException(
            400,
            f"Flow run is '{run.status}', not 'waiting'. Cannot resume.",
        )

    if run.waiting_for != body.event_type:
        raise HTTPException(
            400,
            f"Flow run waiting for '{run.waiting_for}', not '{body.event_type}'",
        )

    from services.flow_engine import route_event

    results = route_event(
        event_type=body.event_type,
        payload=body.payload,
        db=db,
        user_id=UUID(str(current_user["sub"])),
    )

    return {"run_id": run_id, "resumed": True, "results": results}


@router.get("/registry")
async def get_flow_registry(
    current_user: dict = Depends(get_current_user),
):
    """
    List all registered flows and nodes.
    Shows the execution backbone topology.
    """
    from services.flow_engine import FLOW_REGISTRY, NODE_REGISTRY

    return {
        "flows": {
            name: {
                "start": flow["start"],
                "end": flow.get("end", []),
                "node_count": len(flow.get("edges", {})) + 1,
            }
            for name, flow in FLOW_REGISTRY.items()
        },
        "nodes": list(NODE_REGISTRY.keys()),
        "flow_count": len(FLOW_REGISTRY),
        "node_count": len(NODE_REGISTRY),
    }
