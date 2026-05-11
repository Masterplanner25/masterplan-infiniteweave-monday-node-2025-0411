from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from AINDY.core.execution_helper import execute_with_pipeline_sync
from AINDY.db.database import get_db
from AINDY.platform_layer.rate_limiter import limiter
from AINDY.routes.platform.nodus_shared import (
    _NODUS_SCRIPT_REGISTRY,
    load_named_nodus_script_or_404,
    _validate_nodus_source,
)
from AINDY.routes.platform.schemas import NodusScheduleRequest
from AINDY.services.auth_service import get_current_user

router = APIRouter()


def _execute_nodus_schedule(request: Request, route_name: str, handler, *, db: Session, user_id: str, input_payload=None, success_status_code: int = 200):
    result = execute_with_pipeline_sync(
        request=request,
        route_name=route_name,
        handler=handler,
        user_id=user_id,
        input_payload=input_payload or {},
        metadata={"db": db, "source": "platform.nodus_schedule"},
        success_status_code=success_status_code,
        return_result=True,
    )
    if not result.success:
        detail = result.metadata.get("detail") or result.error or "Execution failed"
        raise HTTPException(
            status_code=int(result.metadata.get("status_code", 500)),
            detail=detail,
        )
    data = result.data
    if isinstance(data, dict):
        data = dict(data)
        data.pop("execution_envelope", None)
    return data


@router.post("/nodus/schedule", status_code=201, response_model=None)
@limiter.limit("30/minute")
def create_nodus_schedule(request: Request, body: NodusScheduleRequest, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    user_id = str(current_user["sub"])
    if body.script:
        _validate_nodus_source(body.script, field="script")
        script_source = body.script
    else:
        script_source = load_named_nodus_script_or_404(body.script_name)
        _validate_nodus_source(script_source, field="script_name")

    def handler(ctx):
        from AINDY.runtime.nodus_schedule_service import create_nodus_scheduled_job

        try:
            return create_nodus_scheduled_job(
                db=db,
                script=script_source,
                cron_expression=body.cron,
                user_id=user_id,
                job_name=body.job_name,
                script_name=body.script_name,
                input_payload=body.input,
                error_policy=body.error_policy,
                max_retries=body.max_retries,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail={"error": str(exc)})

    return _execute_nodus_schedule(request, "platform.nodus_schedule.create", handler, db=db, user_id=user_id, input_payload=body.model_dump(), success_status_code=201)


@router.get("/nodus/schedule", response_model=None)
@limiter.limit("60/minute")
def list_nodus_schedules(request: Request, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    def handler(ctx):
        from AINDY.runtime.nodus_schedule_service import list_nodus_scheduled_jobs

        jobs = list_nodus_scheduled_jobs(db=db, user_id=str(current_user["sub"]))
        return {"count": len(jobs), "jobs": jobs}

    return _execute_nodus_schedule(request, "platform.nodus_schedule.list", handler, db=db, user_id=str(current_user["sub"]))


@router.delete("/nodus/schedule/{job_id}", status_code=204, response_model=None)
@limiter.limit("30/minute")
def delete_nodus_schedule(request: Request, job_id: str, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    def handler(ctx):
        from AINDY.runtime.nodus_schedule_service import delete_nodus_scheduled_job

        removed = delete_nodus_scheduled_job(db=db, job_id=job_id, user_id=str(current_user["sub"]))
        if not removed:
            raise HTTPException(status_code=404, detail=f"Scheduled job {job_id!r} not found")
        return None

    return _execute_nodus_schedule(request, "platform.nodus_schedule.delete", handler, db=db, user_id=str(current_user["sub"]), input_payload={"job_id": job_id}, success_status_code=204)
