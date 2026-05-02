"""
Runtime-owned agent HTTP surface.

These routes stay mounted under `/apps/agent/*` for URL stability, but the
ownership boundary is the runtime layer under `AINDY/`, not `apps/agent/`.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from AINDY.agents.runtime_api import (
    approve_agent_run_runtime,
    create_agent_run_runtime,
    get_agent_run_runtime,
    get_agent_tool_suggestions_runtime,
    get_agent_trust_runtime,
    list_agent_run_events_runtime,
    list_agent_run_steps_runtime,
    list_agent_runs_runtime,
    list_agent_tools_runtime,
    recover_agent_run_runtime,
    reject_agent_run_runtime,
    replay_agent_run_runtime,
    update_agent_trust_runtime,
)
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


class RunRequest(BaseModel):
    goal: str


class TrustSettingsUpdate(BaseModel):
    auto_execute_low: Optional[bool] = None
    auto_execute_medium: Optional[bool] = None
    allowed_auto_grant_tools: Optional[list[str]] = None


@router.post("/run")
@limiter.limit("5/minute")
def create_agent_run(
    request: Request,
    body: RunRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not body.goal or not body.goal.strip():
        raise HTTPException(status_code=400, detail="goal is required")
    user_id = _current_user_id(current_user)
    return _execute_agent(
        request,
        "agent.run.create",
        lambda _ctx: create_agent_run_runtime(goal=body.goal, db=db, user_id=user_id),
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
    user_id = _current_user_id(current_user)
    return _execute_agent(
        request,
        "agent.runs.list",
        lambda _ctx: list_agent_runs_runtime(db=db, user_id=user_id, status=status, limit=limit),
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
    user_id = _current_user_id(current_user)
    return _execute_agent(
        request,
        "agent.run.get",
        lambda _ctx: get_agent_run_runtime(db=db, user_id=user_id, run_id=run_id),
        db=db,
        user_id=str(user_id),
        input_payload={"run_id": run_id},
    )


@router.post("/runs/{run_id}/approve")
@limiter.limit("5/minute")
def approve_agent_run(
    request: Request,
    run_id: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id = _current_user_id(current_user)
    return _execute_agent(
        request,
        "agent.run.approve",
        lambda _ctx: approve_agent_run_runtime(db=db, user_id=user_id, run_id=run_id),
        db=db,
        user_id=str(user_id),
        input_payload={"run_id": run_id},
    )


@router.post("/runs/{run_id}/reject")
@limiter.limit("5/minute")
def reject_agent_run(
    request: Request,
    run_id: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id = _current_user_id(current_user)
    return _execute_agent(
        request,
        "agent.run.reject",
        lambda _ctx: reject_agent_run_runtime(db=db, user_id=user_id, run_id=run_id),
        db=db,
        user_id=str(user_id),
        input_payload={"run_id": run_id},
    )


@router.post("/runs/{run_id}/recover")
@limiter.limit("5/minute")
def recover_agent_run(
    request: Request,
    run_id: str,
    force: bool = False,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id = _current_user_id(current_user)
    return _execute_agent(
        request,
        "agent.run.recover",
        lambda _ctx: recover_agent_run_runtime(db=db, user_id=user_id, run_id=run_id, force=force),
        db=db,
        user_id=str(user_id),
        input_payload={"run_id": run_id, "force": force},
    )


@router.post("/runs/{run_id}/replay")
@limiter.limit("5/minute")
def replay_agent_run(
    request: Request,
    run_id: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id = _current_user_id(current_user)
    return _execute_agent(
        request,
        "agent.run.replay",
        lambda _ctx: replay_agent_run_runtime(db=db, user_id=user_id, run_id=run_id),
        db=db,
        user_id=str(user_id),
        input_payload={"run_id": run_id},
    )


@router.get("/runs/{run_id}/steps")
@limiter.limit("60/minute")
def get_run_steps(
    request: Request,
    run_id: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id = _current_user_id(current_user)
    return _execute_agent(
        request,
        "agent.run.steps",
        lambda _ctx: list_agent_run_steps_runtime(db=db, user_id=user_id, run_id=run_id),
        db=db,
        user_id=str(user_id),
        input_payload={"run_id": run_id},
    )


@router.get("/runs/{run_id}/events")
@limiter.limit("60/minute")
def get_run_events(
    request: Request,
    run_id: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id = _current_user_id(current_user)
    return _execute_agent(
        request,
        "agent.run.events",
        lambda _ctx: list_agent_run_events_runtime(db=db, user_id=user_id, run_id=run_id),
        db=db,
        user_id=str(user_id),
        input_payload={"run_id": run_id},
    )


@router.get("/tools")
@limiter.limit("60/minute")
def list_tools(
    request: Request,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id = _current_user_id(current_user)
    return _execute_agent(
        request,
        "agent.tools.list",
        lambda _ctx: list_agent_tools_runtime(),
        db=db,
        user_id=str(user_id),
    )


@router.get("/trust")
@limiter.limit("60/minute")
def get_trust_settings(
    request: Request,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id = _current_user_id(current_user)
    return _execute_agent(
        request,
        "agent.trust.get",
        lambda _ctx: get_agent_trust_runtime(db=db, user_id=user_id),
        db=db,
        user_id=str(user_id),
    )


@router.get("/suggestions")
@limiter.limit("60/minute")
def get_tool_suggestions(
    request: Request,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id = _current_user_id(current_user)
    return _execute_agent(
        request,
        "agent.suggestions.get",
        lambda _ctx: get_agent_tool_suggestions_runtime(db=db, user_id=user_id),
        db=db,
        user_id=str(user_id),
    )


@router.put("/trust")
@limiter.limit("30/minute")
def update_trust_settings(
    request: Request,
    body: TrustSettingsUpdate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id = _current_user_id(current_user)
    payload = {
        "auto_execute_low": body.auto_execute_low,
        "auto_execute_medium": body.auto_execute_medium,
        "allowed_auto_grant_tools": body.allowed_auto_grant_tools,
    }
    return _execute_agent(
        request,
        "agent.trust.update",
        lambda _ctx: update_agent_trust_runtime(db=db, user_id=user_id, **payload),
        db=db,
        user_id=str(user_id),
        input_payload=payload,
    )
