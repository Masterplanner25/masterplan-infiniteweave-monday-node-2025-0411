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

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from AINDY.core.execution_helper import execute_with_pipeline_sync
from AINDY.db.database import get_db
from AINDY.platform_layer.rate_limiter import limiter
from AINDY.services.auth_service import get_current_user
from AINDY.utils.uuid_utils import normalize_uuid

logger = logging.getLogger(__name__)


def _run_to_response(run) -> dict:
    from AINDY.agents.agent_runtime import run_to_dict

    return run_to_dict(run)


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
    from AINDY.runtime.flow_engine import run_flow
    result = run_flow(flow_name, payload, db=db, user_id=str(user_id))
    data = result.get("data")
    if data is None:
        data = {}

    if isinstance(data, dict):
        if data.get("_http_status") == 202:
            return {
                "_http_status": 202,
                "_http_response": _with_legacy_log_alias(data.get("_http_response", {})),
            }
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


def _execute_agent(request: Request, route_name: str, handler, *, db: Session, user_id: str, input_payload=None):
    result = execute_with_pipeline_sync(
        request=request,
        route_name=route_name,
        handler=handler,
        user_id=str(user_id),
        input_payload=input_payload or {},
        metadata={"db": db, "source": "agent"},
        return_result=True,
    )
    if not result.success:
        detail = result.metadata.get("detail") or result.error or "Execution failed"
        raise HTTPException(
            status_code=int(result.metadata.get("status_code", 500)),
            detail=detail,
        )
    data = result.data
    if isinstance(data, dict) and data.get("_http_status"):
        payload = data.get("_http_response", {})
        if isinstance(payload, dict) and data.get("execution_envelope") is not None:
            payload = dict(payload)
            payload.setdefault("execution_envelope", data["execution_envelope"])
        return JSONResponse(
            status_code=int(data["_http_status"]),
            content=payload,
        )
    if isinstance(data, list):
        return {"data": data}
    return _with_legacy_log_alias(data)


def _with_legacy_log_alias(response):
    if not isinstance(response, dict):
        return response
    data = response.get("data")
    candidates = []
    if isinstance(data, dict):
        candidates.append(data)
        result = data.get("result")
        if isinstance(result, dict):
            candidates.append(result)
    candidates.append(response)
    log_id = None
    for item in candidates:
        log_id = log_id or item.get("job_log_id") or item.get("automation_log_id")
    if log_id:
        for item in candidates:
            item.setdefault("automation_log_id", log_id)
    return response


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
@limiter.limit("5/minute")
def create_agent_run(
    request: Request,
    body: RunRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Submit a plain-English goal. Returns generated plan + execution status."""
    if not body.goal or not body.goal.strip():
        raise HTTPException(status_code=400, detail="goal is required")
    user_id = _current_user_id(current_user)
    # Removed: if async_heavy_execution_enabled(): submit_autonomous_async_job(...)
    # Execution mode is decided exclusively by ExecutionDispatcher.
    # Autonomy logic (evaluate_live_trigger, defer, ignore) is preserved inside
    # agent_run_create_node — the flow node owns the autonomy decision.
    def handler(_ctx):
        return _run_flow_agent("agent_run_create", {"goal": body.goal.strip()}, db, user_id)

    return _execute_agent(
        request,
        "agent.run.create",
        handler,
        db=db,
        user_id=str(user_id),
        input_payload={"goal": body.goal.strip()},
    )


@router.get("/runs")
@limiter.limit("60/minute")
def list_agent_runs(
    request: Request,
    status: Optional[str] = None,
    limit: int = 20,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List the current user's agent runs, newest first."""
    user_id = _current_user_id(current_user)
    return _execute_agent(
        request,
        "agent.runs.list",
        lambda _ctx: _run_flow_agent("agent_runs_list", {"status": status, "limit": limit}, db, user_id),
        db=db,
        user_id=str(user_id),
        input_payload={"status": status, "limit": limit},
    )


@router.get("/runs/{run_id}")
@limiter.limit("60/minute")
def get_agent_run(
    request: Request,
    run_id: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get a single agent run by ID."""
    user_id = _current_user_id(current_user)
    return _execute_agent(request, "agent.run.get", lambda _ctx: _run_flow_agent("agent_run_get", {"run_id": run_id}, db, user_id), db=db, user_id=str(user_id), input_payload={"run_id": run_id})


@router.post("/runs/{run_id}/approve")
@limiter.limit("5/minute")
def approve_agent_run(
    request: Request,
    run_id: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Approve a pending_approval run. Immediately executes the plan."""
    user_id = _current_user_id(current_user)
    return _execute_agent(request, "agent.run.approve", lambda _ctx: _run_flow_agent("agent_run_approve", {"run_id": run_id}, db, user_id), db=db, user_id=str(user_id), input_payload={"run_id": run_id})


@router.post("/runs/{run_id}/reject")
@limiter.limit("5/minute")
def reject_agent_run(
    request: Request,
    run_id: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Reject a pending_approval run without executing it."""
    user_id = _current_user_id(current_user)
    return _execute_agent(request, "agent.run.reject", lambda _ctx: _run_flow_agent("agent_run_reject", {"run_id": run_id}, db, user_id), db=db, user_id=str(user_id), input_payload={"run_id": run_id})


@router.post("/runs/{run_id}/recover")
@limiter.limit("5/minute")
def recover_agent_run(
    request: Request,
    run_id: str,
    force: bool = False,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Manually recover a stuck AgentRun."""
    user_id = _current_user_id(current_user)
    return _execute_agent(request, "agent.run.recover", lambda _ctx: _run_flow_agent("agent_run_recover", {"run_id": run_id, "force": force}, db, user_id), db=db, user_id=str(user_id), input_payload={"run_id": run_id, "force": force})


@router.post("/runs/{run_id}/replay")
@limiter.limit("5/minute")
def replay_agent_run(
    request: Request,
    run_id: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Replay an existing run using the same plan."""
    user_id = _current_user_id(current_user)
    return _execute_agent(request, "agent.run.replay", lambda _ctx: _run_flow_agent("agent_run_replay", {"run_id": run_id}, db, user_id), db=db, user_id=str(user_id), input_payload={"run_id": run_id})


@router.get("/runs/{run_id}/steps")
@limiter.limit("60/minute")
def get_run_steps(
    request: Request,
    run_id: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return execution steps for a completed run."""
    user_id = _current_user_id(current_user)
    return _execute_agent(request, "agent.run.steps", lambda _ctx: _run_flow_agent("agent_run_steps", {"run_id": run_id}, db, user_id), db=db, user_id=str(user_id), input_payload={"run_id": run_id})


@router.get("/runs/{run_id}/events")
@limiter.limit("60/minute")
def get_run_events(
    request: Request,
    run_id: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return the unified event timeline for a run."""
    user_id = _current_user_id(current_user)
    return _execute_agent(request, "agent.run.events", lambda _ctx: _run_flow_agent("agent_run_events", {"run_id": run_id}, db, user_id), db=db, user_id=str(user_id), input_payload={"run_id": run_id})


@router.get("/tools")
@limiter.limit("60/minute")
def list_tools(
    request: Request,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all registered tools with risk levels and descriptions."""
    user_id = _current_user_id(current_user)
    return _execute_agent(request, "agent.tools.list", lambda _ctx: _run_flow_agent("agent_tools_list", {}, db, user_id), db=db, user_id=str(user_id))


@router.get("/trust")
@limiter.limit("60/minute")
def get_trust_settings(
    request: Request,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get the current user's agent trust settings."""
    user_id = _current_user_id(current_user)
    return _execute_agent(request, "agent.trust.get", lambda _ctx: _run_flow_agent("agent_trust_get", {}, db, user_id), db=db, user_id=str(user_id))


@router.get("/suggestions")
@limiter.limit("60/minute")
def get_tool_suggestions(
    request: Request,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return up to 3 KPI-driven tool suggestions for the current user."""
    user_id = _current_user_id(current_user)
    return _execute_agent(request, "agent.suggestions.get", lambda _ctx: _run_flow_agent("agent_suggestions_get", {}, db, user_id), db=db, user_id=str(user_id))


@router.put("/trust")
@limiter.limit("30/minute")
def update_trust_settings(
    request: Request,
    body: TrustSettingsUpdate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update the current user's agent trust settings."""
    user_id = _current_user_id(current_user)
    payload = {
        "auto_execute_low": body.auto_execute_low,
        "auto_execute_medium": body.auto_execute_medium,
        "allowed_auto_grant_tools": body.allowed_auto_grant_tools,
    }
    return _execute_agent(request, "agent.trust.update", lambda _ctx: _run_flow_agent("agent_trust_update", payload, db, user_id), db=db, user_id=str(user_id), input_payload=payload)

