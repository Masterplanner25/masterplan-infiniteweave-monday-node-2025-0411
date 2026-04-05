"""
Automation Router - task execution log + replay.

Exposes the AutomationLog for visibility into background task execution.
Replaces the silent daemon thread model with observable, replayable
task execution.
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

router = APIRouter(prefix="/automation", tags=["Automation"])


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


def _run_flow_automation(flow_name: str, payload: dict, db: Session, user_id: str):
    from runtime.flow_engine import run_flow
    result = run_flow(flow_name, payload, db=db, user_id=user_id)
    if result.get("status") == "FAILED":
        error = _flow_failure(result)
        if error.startswith("HTTP_"):
            parts = error.split(":", 1)
            code = int(parts[0].replace("HTTP_", ""))
            msg = parts[1] if len(parts) > 1 else error
            raise HTTPException(status_code=code, detail=msg)
        raise HTTPException(status_code=500, detail=error or f"{flow_name} failed")
    return result.get("data")


async def _execute_automation(request: Request, route_name: str, handler, *, db: Session, user_id: str, input_payload=None):
    return await execute_with_pipeline(
        request=request,
        route_name=route_name,
        handler=handler,
        user_id=user_id,
        input_payload=input_payload,
        metadata={"db": db, "source": "automation_router"},
    )


class AutomationTriggerRequest(BaseModel):
    automation_type: Optional[str] = None
    automation_config: Optional[dict] = None


@router.get("/logs")
async def get_automation_logs(
    request: Request,
    status: Optional[str] = None,
    source: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])
    def handler(_ctx):
        return _run_flow_automation(
            "automation_logs_list",
            {"status": status, "source_filter": source, "limit": limit},
            db, user_id,
        )
    return await _execute_automation(request, "automation.logs.list", handler, db=db, user_id=user_id,
                                     input_payload={"status": status, "source_filter": source})


@router.get("/logs/{log_id}")
async def get_automation_log(
    request: Request,
    log_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])
    def handler(_ctx):
        return _run_flow_automation("automation_log_get", {"log_id": log_id}, db, user_id)
    return await _execute_automation(request, "automation.logs.get", handler, db=db, user_id=user_id,
                                     input_payload={"automation_log_id": log_id})


@router.post("/logs/{log_id}/replay")
async def replay_automation_log(
    request: Request,
    log_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])
    from db.models.automation_log import AutomationLog
    from agents.capability_service import validate_token

    log = db.query(AutomationLog).filter(AutomationLog.id == log_id).first()
    if log and getattr(log, "payload", None):
        payload = log.payload if isinstance(log.payload, dict) else {}
        if payload.get("execution_token"):
            validation = validate_token(
                token=payload.get("execution_token"),
                run_id=payload.get("run_id"),
                user_id=user_id,
            )
            if not validation.get("ok"):
                raise HTTPException(
                    status_code=403,
                    detail={"error": validation.get("error", "invalid_execution_token")},
                )

    def handler(_ctx):
        return _run_flow_automation("automation_log_replay", {"log_id": log_id}, db, user_id)
    return await _execute_automation(request, "automation.logs.replay", handler, db=db, user_id=user_id,
                                     input_payload={"automation_log_id": log_id})


@router.get("/scheduler/status")
async def get_scheduler_status(
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])
    def handler(_ctx):
        return _run_flow_automation("automation_scheduler_status", {}, db, user_id)
    return await _execute_automation(request, "automation.scheduler.status", handler, db=db, user_id=user_id)


@router.post("/tasks/{task_id}/trigger")
async def trigger_task_automation(
    request: Request,
    task_id: int,
    body: AutomationTriggerRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])
    def handler(_ctx):
        return _run_flow_automation(
            "automation_task_trigger",
            {"task_id": task_id, "automation_type": body.automation_type, "automation_config": body.automation_config},
            db, user_id,
        )
    return await _execute_automation(request, "automation.tasks.trigger", handler, db=db, user_id=user_id,
                                     input_payload={"task_id": task_id, "automation_type": body.automation_type})

