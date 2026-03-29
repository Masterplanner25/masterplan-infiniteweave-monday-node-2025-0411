"""
Automation Router — task execution log + replay.

Exposes the AutomationLog for visibility into background task execution.
Replaces the silent daemon thread model with observable, replayable
task execution.
"""
import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db.database import get_db
from db.models.automation_log import AutomationLog
from services import task_services
from services.auth_service import get_current_user
from services.execution_envelope import error, success
from services.task_services import queue_task_automation
from utils.trace_context import ensure_trace_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/automation", tags=["Automation"])


class AutomationTriggerRequest(BaseModel):
    automation_type: Optional[str] = None
    automation_config: Optional[dict] = None


@router.get("/logs")
async def get_automation_logs(
    status: Optional[str] = None,
    source: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Get automation execution logs for the current user.

    Shows all background task executions — pending, running, success,
    failed, retrying.

    This replaces silent daemon thread execution with full observability.
    """
    query = db.query(AutomationLog).filter(
        AutomationLog.user_id == UUID(str(current_user["sub"]))
    )

    if status:
        query = query.filter(AutomationLog.status == status)

    if source:
        query = query.filter(AutomationLog.source == source)

    logs = query.order_by(AutomationLog.created_at.desc()).limit(limit).all()

    return success({
        "logs": [
            {
                "id": log.id,
                "source": log.source,
                "task_name": log.task_name,
                "status": log.status,
                "attempt_count": log.attempt_count,
                "max_attempts": log.max_attempts,
                "error_message": log.error_message,
                "result": log.result,
                "created_at": log.created_at.isoformat() if log.created_at else None,
                "started_at": log.started_at.isoformat() if log.started_at else None,
                "completed_at": log.completed_at.isoformat() if log.completed_at else None,
            }
            for log in logs
        ],
        "count": len(logs),
        "filters": {"status": status, "source": source},
    }, [], ensure_trace_id())


@router.get("/logs/{log_id}")
async def get_automation_log(
    log_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get a single automation log entry by ID."""
    log = (
        db.query(AutomationLog)
        .filter(
            AutomationLog.id == log_id,
            AutomationLog.user_id == UUID(str(current_user["sub"])),
        )
        .first()
    )

    if not log:
        raise HTTPException(status_code=404, detail="Automation log not found")

    return success({
        "id": log.id,
        "source": log.source,
        "task_name": log.task_name,
        "payload": log.payload,
        "status": log.status,
        "attempt_count": log.attempt_count,
        "max_attempts": log.max_attempts,
        "error_message": log.error_message,
        "result": log.result,
        "created_at": log.created_at.isoformat() if log.created_at else None,
        "started_at": log.started_at.isoformat() if log.started_at else None,
        "completed_at": log.completed_at.isoformat() if log.completed_at else None,
        "scheduled_for": log.scheduled_for.isoformat() if log.scheduled_for else None,
    }, [], ensure_trace_id())


@router.post("/logs/{log_id}/replay")
async def replay_automation_log(
    log_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Replay a failed task execution.

    Resets the log to pending and re-runs the original task with the
    original payload. Only failed or retrying logs can be replayed.
    """
    log = (
        db.query(AutomationLog)
        .filter(
            AutomationLog.id == log_id,
            AutomationLog.user_id == UUID(str(current_user["sub"])),
        )
        .first()
    )

    if not log:
        raise HTTPException(status_code=404, detail="Automation log not found")

    if log.status not in ("failed", "retrying"):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Cannot replay log with status '{log.status}'. "
                "Only failed or retrying logs can be replayed."
            ),
        )

    payload = log.payload or {}
    if isinstance(payload, dict) and payload.get("execution_token"):
        from services.capability_service import validate_token

        validation = validate_token(
            token=payload.get("execution_token"),
            run_id=str(payload.get("run_id", "")),
            user_id=UUID(str(current_user["sub"])),
        )
        if not validation["ok"]:
            raise HTTPException(
                status_code=403,
                detail=f"Execution token invalid for replay: {validation['error']}",
            )

    from services.scheduler_service import replay_task

    result = replay_task(log_id)

    if not result:
        raise HTTPException(
            status_code=500,
            detail=(
                "Replay failed — task function not registered. "
                "Check task registry."
            ),
        )

    return success({
        "log_id": log_id,
        "status": "replay_scheduled",
        "message": (
            "Task replay has been scheduled. "
            "Check GET /automation/logs/{id} for status updates."
        ),
    }, [], ensure_trace_id())


@router.get("/scheduler/status")
async def get_scheduler_status(
    current_user: dict = Depends(get_current_user),
):
    """
    Get APScheduler status and registered jobs.

    Shows what recurring jobs are scheduled and when they last ran
    or will next run.
    """
    try:
        from services.scheduler_service import get_scheduler

        scheduler = get_scheduler()
        jobs = scheduler.get_jobs()

        return success({
            "running": scheduler.running,
            "job_count": len(jobs),
            "jobs": [
                {
                    "id": job.id,
                    "name": job.name,
                    "next_run": (
                        job.next_run_time.isoformat() if job.next_run_time else None
                    ),
                    "trigger": str(job.trigger),
                }
                for job in jobs
            ],
        }, [], ensure_trace_id())
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@router.post("/tasks/{task_id}/trigger")
async def trigger_task_automation(
    task_id: int,
    body: AutomationTriggerRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    task = task_services.get_task_by_id(db, task_id, current_user["sub"])
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if body.automation_type is not None:
        task.automation_type = body.automation_type
    if body.automation_config is not None:
        task.automation_config = body.automation_config
    db.commit()
    db.refresh(task)

    if not task.automation_type:
        return error("task_automation_not_configured", [], ensure_trace_id())

    dispatch = queue_task_automation(
        db=db,
        task=task,
        user_id=current_user["sub"],
        reason="manual_trigger",
    )
    if not dispatch:
        return error("task_automation_dispatch_failed", [], ensure_trace_id())
    return dispatch
