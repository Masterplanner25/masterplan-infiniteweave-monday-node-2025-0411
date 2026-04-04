"""
Agent Router — Sprint N+4 Agentics Phase 1+2 / Sprint N+5 Phase 3 / Sprint N+7 Observability

Endpoints:
  POST   /agent/run                       — create a new agent run (goal → plan)
  GET    /agent/runs                      — list user's runs
  GET    /agent/runs/{run_id}             — get run detail
  POST   /agent/runs/{run_id}/approve     — approve + execute a pending run
  POST   /agent/runs/{run_id}/reject      — reject a pending run
  POST   /agent/runs/{run_id}/recover     — manually recover a stuck run (N+7)
  POST   /agent/runs/{run_id}/replay      — replay a run with same plan (N+7)
  GET    /agent/runs/{run_id}/steps       — list steps for a run
  GET    /agent/tools                     — list available tools
  GET    /agent/trust                     — get trust settings
  PUT    /agent/trust                     — update trust settings
  GET    /agent/suggestions               — KPI-based tool suggestions (Phase 3)
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db.database import get_db
from services.auth_service import get_current_user
from utils.uuid_utils import normalize_uuid

logger = logging.getLogger(__name__)


def _run_to_response(run) -> dict:
    from agents.agent_runtime import _run_to_dict

    return _run_to_dict(run)


def _current_user_id(current_user):
    try:
        return normalize_uuid(current_user["sub"])
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid authenticated user id") from exc


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


def _run_flow_agent(flow_name: str, payload: dict, db, user_id):
    """Run a flow and interpret special response markers from agent nodes."""
    from runtime.flow_engine import run_flow
    result = run_flow(flow_name, payload, db=db, user_id=str(user_id))
    data = result.get("data") or {}

    if isinstance(data, dict):
        # 202 deferred
        if data.get("_http_status") == 202:
            return JSONResponse(status_code=202, content=data.get("_http_response", {}))
        # autonomy ignore/defer decision
        if "_decision_response" in data:
            return data["_decision_response"]

    if result.get("status") == "FAILED":
        error = _flow_failure(result)
        if error.startswith("HTTP_"):
            parts = error.split(":", 1)
            status_code = int(parts[0].replace("HTTP_", ""))
            detail = parts[1] if len(parts) > 1 else error
            raise HTTPException(status_code=status_code, detail=detail)
        if "uuid" in error.lower() or "invalid" in error.lower():
            detail = "Invalid run_id" if "run_id" in flow_name or "agent_run_" in flow_name else error
            raise HTTPException(status_code=400, detail=detail)
        raise HTTPException(status_code=500, detail=error or f"{flow_name} failed")

    return data


router = APIRouter(prefix="/agent", tags=["Agent"])


# ── Request / Response Models ─────────────────────────────────────────────────

class RunRequest(BaseModel):
    goal: str


class TrustSettingsUpdate(BaseModel):
    auto_execute_low: Optional[bool] = None
    auto_execute_medium: Optional[bool] = None
    allowed_auto_grant_tools: Optional[list[str]] = None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/run")
def create_agent_run(
    body: RunRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Submit a plain-English goal. Returns generated plan + execution status."""
    if not body.goal or not body.goal.strip():
        raise HTTPException(status_code=400, detail="goal is required")
    user_id = _current_user_id(current_user)
    return _run_flow_agent("agent_run_create", {"goal": body.goal.strip()}, db, user_id)


@router.get("/runs")
def list_agent_runs(
    status: Optional[str] = None,
    limit: int = 20,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List the current user's agent runs, newest first."""
    user_id = _current_user_id(current_user)
    return _run_flow_agent("agent_runs_list", {"status": status, "limit": limit}, db, user_id)


@router.get("/runs/{run_id}")
def get_agent_run(
    run_id: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get a single agent run by ID."""
    user_id = _current_user_id(current_user)
    return _run_flow_agent("agent_run_get", {"run_id": run_id}, db, user_id)


@router.post("/runs/{run_id}/approve")
def approve_agent_run(
    run_id: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Approve a pending_approval run. Immediately executes the plan."""
    user_id = _current_user_id(current_user)
    return _run_flow_agent("agent_run_approve", {"run_id": run_id}, db, user_id)


@router.post("/runs/{run_id}/reject")
def reject_agent_run(
    run_id: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Reject a pending_approval run without executing it."""
    user_id = _current_user_id(current_user)
    return _run_flow_agent("agent_run_reject", {"run_id": run_id}, db, user_id)


@router.post("/runs/{run_id}/recover")
def recover_agent_run(
    run_id: str,
    force: bool = False,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Manually recover a stuck AgentRun."""
    user_id = _current_user_id(current_user)
    return _run_flow_agent("agent_run_recover", {"run_id": run_id, "force": force}, db, user_id)


@router.post("/runs/{run_id}/replay")
def replay_agent_run(
    run_id: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Replay an existing run using the same plan."""
    user_id = _current_user_id(current_user)
    return _run_flow_agent("agent_run_replay", {"run_id": run_id}, db, user_id)


@router.get("/runs/{run_id}/steps")
def get_run_steps(
    run_id: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return execution steps for a completed run."""
    user_id = _current_user_id(current_user)
    return _run_flow_agent("agent_run_steps", {"run_id": run_id}, db, user_id)


@router.get("/runs/{run_id}/events")
def get_run_events(
    run_id: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return the unified event timeline for a run."""
    user_id = _current_user_id(current_user)
    return _run_flow_agent("agent_run_events", {"run_id": run_id}, db, user_id)


@router.get("/tools")
def list_tools(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all registered tools with risk levels and descriptions."""
    user_id = _current_user_id(current_user)
    return _run_flow_agent("agent_tools_list", {}, db, user_id)


@router.get("/trust")
def get_trust_settings(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get the current user's agent trust settings."""
    user_id = _current_user_id(current_user)
    return _run_flow_agent("agent_trust_get", {}, db, user_id)


@router.get("/suggestions")
def get_tool_suggestions(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return up to 3 KPI-driven tool suggestions for the current user."""
    user_id = _current_user_id(current_user)
    return _run_flow_agent("agent_suggestions_get", {}, db, user_id)


@router.put("/trust")
def update_trust_settings(
    body: TrustSettingsUpdate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update the current user's agent trust settings."""
    user_id = _current_user_id(current_user)
    return _run_flow_agent("agent_trust_update", {
        "auto_execute_low": body.auto_execute_low,
        "auto_execute_medium": body.auto_execute_medium,
        "allowed_auto_grant_tools": body.allowed_auto_grant_tools,
    }, db, user_id)

