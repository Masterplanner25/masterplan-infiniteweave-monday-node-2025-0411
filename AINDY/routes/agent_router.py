"""
Agent Router — Sprint N+4 Agentics Phase 1+2 / Sprint N+5 Phase 3

Endpoints:
  POST   /agent/run                     — create a new agent run (goal → plan)
  GET    /agent/runs                    — list user's runs
  GET    /agent/runs/{run_id}           — get run detail
  POST   /agent/runs/{run_id}/approve   — approve + execute a pending run
  POST   /agent/runs/{run_id}/reject    — reject a pending run
  GET    /agent/runs/{run_id}/steps     — list steps for a run
  GET    /agent/tools                   — list available tools
  GET    /agent/trust                   — get trust settings
  PUT    /agent/trust                   — update trust settings
  GET    /agent/suggestions             — KPI-based tool suggestions (Phase 3)
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db.database import get_db
from services.auth_service import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=["Agent"])


# ── Request / Response Models ─────────────────────────────────────────────────

class RunRequest(BaseModel):
    goal: str


class TrustSettingsUpdate(BaseModel):
    auto_execute_low: Optional[bool] = None
    auto_execute_medium: Optional[bool] = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_run_or_404(run_id: str, user_id: str, db: Session):
    from db.models.agent_run import AgentRun
    run = db.query(AgentRun).filter(AgentRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.user_id != user_id:
        raise HTTPException(status_code=403, detail="Not authorized")
    return run


def _run_to_response(run) -> dict:
    return {
        "run_id": str(run.id),
        "goal": run.goal,
        "executive_summary": run.executive_summary,
        "overall_risk": run.overall_risk,
        "status": run.status,
        "steps_total": run.steps_total,
        "steps_completed": run.steps_completed,
        "plan": run.plan,
        "result": run.result,
        "error_message": run.error_message,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "approved_at": run.approved_at.isoformat() if run.approved_at else None,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/run")
def create_agent_run(
    body: RunRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Submit a plain-English goal.
    Returns the generated plan + status (pending_approval or approved).
    If auto-execute applies, execution begins immediately.
    """
    from services.agent_runtime import create_run, execute_run

    if not body.goal or not body.goal.strip():
        raise HTTPException(status_code=400, detail="goal is required")

    user_id = str(current_user["sub"])
    run = create_run(goal=body.goal.strip(), user_id=user_id, db=db)

    if not run:
        raise HTTPException(status_code=500, detail="Failed to generate plan")

    # Auto-execute if trust gate approved it
    if run["status"] == "approved":
        run = execute_run(run_id=run["run_id"], user_id=user_id, db=db) or run

    return run


@router.get("/runs")
def list_agent_runs(
    status: Optional[str] = None,
    limit: int = 20,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List the current user's agent runs, newest first."""
    from db.models.agent_run import AgentRun

    user_id = str(current_user["sub"])
    query = db.query(AgentRun).filter(AgentRun.user_id == user_id)

    if status:
        query = query.filter(AgentRun.status == status)

    runs = query.order_by(AgentRun.created_at.desc()).limit(limit).all()
    return [_run_to_response(r) for r in runs]


@router.get("/runs/{run_id}")
def get_agent_run(
    run_id: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get a single agent run by ID."""
    user_id = str(current_user["sub"])
    run = _get_run_or_404(run_id, user_id, db)
    return _run_to_response(run)


@router.post("/runs/{run_id}/approve")
def approve_agent_run(
    run_id: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Approve a pending_approval run.
    Immediately executes the plan and returns the final run state.
    """
    from services.agent_runtime import approve_run

    user_id = str(current_user["sub"])
    run = approve_run(run_id=run_id, user_id=user_id, db=db)

    if not run:
        raise HTTPException(status_code=404, detail="Run not found or not approvable")

    return run


@router.post("/runs/{run_id}/reject")
def reject_agent_run(
    run_id: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Reject a pending_approval run without executing it."""
    from services.agent_runtime import reject_run

    user_id = str(current_user["sub"])
    run = reject_run(run_id=run_id, user_id=user_id, db=db)

    if not run:
        raise HTTPException(status_code=404, detail="Run not found or not rejectable")

    return run


@router.get("/runs/{run_id}/steps")
def get_run_steps(
    run_id: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return execution steps for a completed run."""
    from db.models.agent_run import AgentStep

    user_id = str(current_user["sub"])
    _get_run_or_404(run_id, user_id, db)  # auth check

    steps = (
        db.query(AgentStep)
        .filter(AgentStep.run_id == run_id)
        .order_by(AgentStep.step_index.asc())
        .all()
    )

    return [
        {
            "step_index": s.step_index,
            "tool_name": s.tool_name,
            "description": s.description,
            "risk_level": s.risk_level,
            "status": s.status,
            "result": s.result,
            "error_message": s.error_message,
            "execution_ms": s.execution_ms,
            "executed_at": s.executed_at.isoformat() if s.executed_at else None,
        }
        for s in steps
    ]


@router.get("/tools")
def list_tools(current_user=Depends(get_current_user)):
    """List all registered tools with risk levels and descriptions."""
    from services.agent_tools import TOOL_REGISTRY

    return [
        {
            "name": name,
            "risk": entry["risk"],
            "description": entry["description"],
        }
        for name, entry in TOOL_REGISTRY.items()
    ]


@router.get("/trust")
def get_trust_settings(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get the current user's agent trust settings."""
    from db.models.agent_run import AgentTrustSettings

    user_id = str(current_user["sub"])
    trust = db.query(AgentTrustSettings).filter(
        AgentTrustSettings.user_id == user_id
    ).first()

    return {
        "user_id": user_id,
        "auto_execute_low": trust.auto_execute_low if trust else False,
        "auto_execute_medium": trust.auto_execute_medium if trust else False,
        "note": "High-risk plans always require approval regardless of trust settings.",
    }


@router.get("/suggestions")
def get_tool_suggestions(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Return up to 3 KPI-driven tool suggestions for the current user.

    Reads the user's latest Infinity score snapshot and maps low KPIs to
    recommended tools + pre-filled goal strings.

    Returns [] when the user has no score history yet.
    """
    from services.agent_tools import suggest_tools
    from services.infinity_service import get_user_kpi_snapshot

    user_id = str(current_user["sub"])
    snapshot = get_user_kpi_snapshot(user_id=user_id, db=db)
    return suggest_tools(kpi_snapshot=snapshot)


@router.put("/trust")
def update_trust_settings(
    body: TrustSettingsUpdate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update the current user's agent trust settings."""
    from datetime import datetime, timezone

    from db.models.agent_run import AgentTrustSettings

    user_id = str(current_user["sub"])
    trust = db.query(AgentTrustSettings).filter(
        AgentTrustSettings.user_id == user_id
    ).first()

    if not trust:
        trust = AgentTrustSettings(user_id=user_id)
        db.add(trust)

    if body.auto_execute_low is not None:
        trust.auto_execute_low = body.auto_execute_low
    if body.auto_execute_medium is not None:
        trust.auto_execute_medium = body.auto_execute_medium

    trust.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(trust)

    return {
        "user_id": user_id,
        "auto_execute_low": trust.auto_execute_low,
        "auto_execute_medium": trust.auto_execute_medium,
        "note": "High-risk plans always require approval regardless of trust settings.",
    }
