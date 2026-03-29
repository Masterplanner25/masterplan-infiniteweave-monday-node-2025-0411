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
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db.database import get_db
from services.auth_service import get_current_user
from services.autonomous_controller import build_decision_response
from services.autonomous_controller import evaluate_live_trigger
from services.autonomous_controller import record_decision
from services.execution_envelope import success
from services.async_job_service import defer_async_job
from utils.trace_context import ensure_trace_id
from utils.uuid_utils import normalize_uuid

logger = logging.getLogger(__name__)


def _current_user_id(current_user) -> UUID:
    try:
        return normalize_uuid(current_user["sub"])
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid authenticated user id") from exc


def _parse_run_id(run_id: str) -> UUID:
    try:
        return normalize_uuid(run_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid run_id") from exc

router = APIRouter(prefix="/agent", tags=["Agent"])


# ── Request / Response Models ─────────────────────────────────────────────────

class RunRequest(BaseModel):
    goal: str


class TrustSettingsUpdate(BaseModel):
    auto_execute_low: Optional[bool] = None
    auto_execute_medium: Optional[bool] = None
    allowed_auto_grant_tools: Optional[list[str]] = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_run_or_404(run_id: str, user_id: str, db: Session):
    from db.models.agent_run import AgentRun
    run_uuid = _parse_run_id(run_id)
    run = db.query(AgentRun).filter(AgentRun.id == run_uuid).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.user_id != normalize_uuid(user_id):
        raise HTTPException(status_code=403, detail="Not authorized")
    return run


def _run_to_response(run) -> dict:
    """Unified serializer — delegates to the service layer (Sprint N+7)."""
    from services.agent_runtime import _run_to_dict
    return _run_to_dict(run)


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
    from services.agent_runtime import create_run, execute_run, to_execution_response
    from services.async_job_service import (
        async_heavy_execution_enabled,
        submit_autonomous_async_job,
    )

    if not body.goal or not body.goal.strip():
        raise HTTPException(status_code=400, detail="goal is required")

    user_id = _current_user_id(current_user)
    if async_heavy_execution_enabled():
        response = submit_autonomous_async_job(
            task_name="agent.create_run",
            payload={"goal": body.goal.strip(), "user_id": str(user_id)},
            user_id=user_id,
            source="agent_router",
            trigger_type="user",
            trigger_context={"goal": body.goal.strip(), "importance": 0.95},
        )
        return JSONResponse(status_code=202, content=response)

    trace_id = ensure_trace_id()
    trigger_context = {"goal": body.goal.strip(), "importance": 0.95}
    evaluation = evaluate_live_trigger(
        db=db,
        trigger={"trigger_type": "user", "source": "agent_router", "goal": body.goal.strip()},
        user_id=user_id,
        context=trigger_context,
    )
    record_decision(
        db=db,
        trigger={"trigger_type": "user", "source": "agent_router", "goal": body.goal.strip()},
        evaluation=evaluation,
        user_id=user_id,
        trace_id=trace_id,
        context=trigger_context,
    )
    if evaluation["decision"] == "ignore":
        return build_decision_response(evaluation, trace_id=trace_id)
    if evaluation["decision"] == "defer":
        log_id = defer_async_job(
            task_name="agent.create_run",
            payload={"goal": body.goal.strip(), "user_id": str(user_id), "__autonomy": {"trigger_type": "user", "source": "agent_router", "context": trigger_context}},
            user_id=user_id,
            source="agent_router",
            decision=evaluation,
        )
        return JSONResponse(
            status_code=202,
            content=build_decision_response(
                evaluation,
                trace_id=log_id,
                result={"automation_log_id": log_id, "decision": "defer", "reason": evaluation["reason"]},
                next_action={"type": "poll_automation_log", "automation_log_id": log_id},
            ),
        )

    run = create_run(goal=body.goal.strip(), user_id=user_id, db=db)

    if not run:
        raise HTTPException(status_code=500, detail="Failed to generate plan")

    # Auto-execute if trust gate approved it
    if run["status"] == "approved":
        run = execute_run(run_id=run["run_id"], user_id=user_id, db=db) or run

    return to_execution_response(run, db)


@router.get("/runs")
def list_agent_runs(
    status: Optional[str] = None,
    limit: int = 20,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List the current user's agent runs, newest first."""
    from db.models.agent_run import AgentRun

    user_id = _current_user_id(current_user)
    query = db.query(AgentRun).filter(AgentRun.user_id == user_id)

    if status:
        query = query.filter(AgentRun.status == status)

    runs = query.order_by(AgentRun.created_at.desc()).limit(limit).all()
    return success([_run_to_response(r) for r in runs], [], ensure_trace_id())


@router.get("/runs/{run_id}")
def get_agent_run(
    run_id: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get a single agent run by ID."""
    user_id = _current_user_id(current_user)
    run = _get_run_or_404(run_id, user_id, db)
    serialized = _run_to_response(run)
    return success(serialized, [], serialized.get("trace_id") or ensure_trace_id())


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
    from services.agent_runtime import approve_run, to_execution_response
    from services.async_job_service import (
        async_heavy_execution_enabled,
        submit_autonomous_async_job,
    )

    user_id = _current_user_id(current_user)
    if async_heavy_execution_enabled():
        response = submit_autonomous_async_job(
            task_name="agent.approve_run",
            payload={"run_id": run_id, "user_id": str(user_id)},
            user_id=user_id,
            source="agent_router",
            trigger_type="user",
            trigger_context={"goal": f"approve_run:{run_id}", "importance": 0.9},
        )
        return JSONResponse(status_code=202, content=response)

    trace_id = ensure_trace_id()
    trigger_context = {"goal": f"approve_run:{run_id}", "importance": 0.9}
    evaluation = evaluate_live_trigger(
        db=db,
        trigger={"trigger_type": "user", "source": "agent_router.approve", "goal": f"approve_run:{run_id}"},
        user_id=user_id,
        context=trigger_context,
    )
    record_decision(
        db=db,
        trigger={"trigger_type": "user", "source": "agent_router.approve", "goal": f"approve_run:{run_id}"},
        evaluation=evaluation,
        user_id=user_id,
        trace_id=trace_id,
        context=trigger_context,
    )
    if evaluation["decision"] == "ignore":
        return build_decision_response(evaluation, trace_id=trace_id)
    if evaluation["decision"] == "defer":
        log_id = defer_async_job(
            task_name="agent.approve_run",
            payload={"run_id": run_id, "user_id": str(user_id), "__autonomy": {"trigger_type": "user", "source": "agent_router.approve", "context": trigger_context}},
            user_id=user_id,
            source="agent_router",
            decision=evaluation,
        )
        return JSONResponse(
            status_code=202,
            content=build_decision_response(
                evaluation,
                trace_id=log_id,
                result={"automation_log_id": log_id, "decision": "defer", "reason": evaluation["reason"]},
                next_action={"type": "poll_automation_log", "automation_log_id": log_id},
            ),
        )

    run = approve_run(run_id=run_id, user_id=user_id, db=db)

    if not run:
        raise HTTPException(status_code=404, detail="Run not found or not approvable")

    return to_execution_response(run, db)


@router.post("/runs/{run_id}/reject")
def reject_agent_run(
    run_id: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Reject a pending_approval run without executing it."""
    from services.agent_runtime import reject_run

    user_id = _current_user_id(current_user)
    run = reject_run(run_id=run_id, user_id=user_id, db=db)

    if not run:
        raise HTTPException(status_code=404, detail="Run not found or not rejectable")

    from services.agent_runtime import to_execution_response

    return to_execution_response(run, db)


@router.post("/runs/{run_id}/recover")
def recover_agent_run(
    run_id: str,
    force: bool = False,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Manually recover a stuck AgentRun (Sprint N+7).

    The run must be in status="executing".  By default, the run must also
    have been started at least AINDY_STUCK_RUN_THRESHOLD_MINUTES ago.
    Pass ?force=true to bypass the age guard.

    Returns 409 with a distinct message for each blocking condition:
      - "Run is not in executing state"
      - "Run started less than N minutes ago (use ?force=true to override)"
    """
    from services.stuck_run_service import recover_stuck_agent_run

    user_id = _current_user_id(current_user)
    result = recover_stuck_agent_run(run_id=run_id, user_id=user_id, db=db, force=force)

    if result["ok"]:
        from services.agent_runtime import to_execution_response

        return to_execution_response(result["run"], db)

    error_code = result.get("error_code", "internal_error")
    if error_code == "not_found":
        raise HTTPException(status_code=404, detail="Run not found")
    if error_code == "forbidden":
        raise HTTPException(status_code=403, detail="Not authorized")
    if error_code in ("wrong_status", "too_recent"):
        raise HTTPException(status_code=409, detail=result.get("detail", error_code))
    raise HTTPException(status_code=500, detail="Recovery failed")


@router.post("/runs/{run_id}/replay")
def replay_agent_run(
    run_id: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Replay an existing run using the same plan (Sprint N+7).

    Creates a new AgentRun with the original plan.  Trust gate is
    re-applied — prior approval does not carry forward.

    Returns the new run dict (status pending_approval or approved).
    """
    from services.agent_runtime import replay_run

    user_id = _current_user_id(current_user)
    new_run = replay_run(run_id=run_id, user_id=user_id, db=db)

    if not new_run:
        raise HTTPException(status_code=404, detail="Run not found or not replayable")

    from services.agent_runtime import to_execution_response

    return to_execution_response(new_run, db)


@router.get("/runs/{run_id}/steps")
def get_run_steps(
    run_id: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return execution steps for a completed run."""
    from db.models.agent_run import AgentStep

    user_id = _current_user_id(current_user)
    _get_run_or_404(run_id, user_id, db)  # auth check

    steps = (
        db.query(AgentStep)
        .filter(AgentStep.run_id == _parse_run_id(run_id))
        .order_by(AgentStep.step_index.asc())
        .all()
    )

    return success([
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
    ], [], ensure_trace_id())


@router.get("/runs/{run_id}/events")
def get_run_events(
    run_id: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Return the unified event timeline for a run (Sprint N+8).

    Merges lifecycle events (PLAN_CREATED, APPROVED, EXECUTION_STARTED,
    COMPLETED, etc.) with synthesised step events (STEP_EXECUTED, STEP_FAILED)
    from AgentStep, sorted chronologically.

    Returns the complete execution story from plan creation to final outcome.
    Pre-N+8 runs (no correlation_id) return correlation_id: null and an
    empty events list gracefully.
    """
    from services.agent_runtime import get_run_events

    user_id = _current_user_id(current_user)
    result = get_run_events(run_id=run_id, user_id=user_id, db=db)

    if result is None:
        # Distinguish not-found from auth error by re-querying just for existence
        from db.models.agent_run import AgentRun
        run = db.query(AgentRun).filter(AgentRun.id == _parse_run_id(run_id)).first()
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")
        raise HTTPException(status_code=403, detail="Not authorized")

    return success(result, [], ensure_trace_id())


@router.get("/tools")
def list_tools(current_user=Depends(get_current_user)):
    """List all registered tools with risk levels and descriptions."""
    from services.agent_tools import TOOL_REGISTRY

    return success([
        {
            "name": name,
            "risk": entry["risk"],
            "description": entry["description"],
            "capability": entry.get("capability"),
            "required_capability": entry.get("required_capability"),
            "category": entry.get("category"),
            "egress_scope": entry.get("egress_scope"),
        }
        for name, entry in TOOL_REGISTRY.items()
    ], [], ensure_trace_id())


@router.get("/trust")
def get_trust_settings(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get the current user's agent trust settings."""
    from db.models.agent_run import AgentTrustSettings
    from services.capability_service import get_auto_grantable_tools

    user_id = _current_user_id(current_user)
    trust = db.query(AgentTrustSettings).filter(
        AgentTrustSettings.user_id == user_id
    ).first()

    return success(
        {
            "user_id": str(user_id),
            "auto_execute_low": trust.auto_execute_low if trust else False,
            "auto_execute_medium": trust.auto_execute_medium if trust else False,
            "allowed_auto_grant_tools": (
                trust.allowed_auto_grant_tools
                if trust and trust.allowed_auto_grant_tools is not None
                else get_auto_grantable_tools(user_id=user_id, db=db)
            ),
            "note": "High-risk plans always require approval regardless of trust settings.",
        },
        [],
        ensure_trace_id(),
    )


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

    user_id = _current_user_id(current_user)
    snapshot = get_user_kpi_snapshot(user_id=user_id, db=db)
    return success(
        suggest_tools(kpi_snapshot=snapshot, user_id=user_id, db=db),
        [],
        ensure_trace_id(),
    )


@router.put("/trust")
def update_trust_settings(
    body: TrustSettingsUpdate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update the current user's agent trust settings."""
    from datetime import datetime, timezone

    from db.models.agent_run import AgentTrustSettings
    from services.agent_tools import TOOL_REGISTRY

    user_id = _current_user_id(current_user)
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
    if body.allowed_auto_grant_tools is not None:
        trust.allowed_auto_grant_tools = sorted(
            {
                tool_name
                for tool_name in body.allowed_auto_grant_tools
                if tool_name in TOOL_REGISTRY
                and TOOL_REGISTRY[tool_name]["risk"] in {"low", "medium"}
                and tool_name != "genesis.message"
            }
        )

    trust.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(trust)

    return success(
        {
            "user_id": str(user_id),
            "auto_execute_low": trust.auto_execute_low,
            "auto_execute_medium": trust.auto_execute_medium,
            "allowed_auto_grant_tools": trust.allowed_auto_grant_tools or [],
            "note": "High-risk plans always require approval regardless of trust settings.",
        },
        [],
        ensure_trace_id(),
    )
