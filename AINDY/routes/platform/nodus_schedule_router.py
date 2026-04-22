from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from AINDY.db.database import get_db
from AINDY.platform_layer.rate_limiter import limiter
from AINDY.routes.platform.nodus_shared import (
    _NODUS_SCRIPT_REGISTRY,
    _SCRIPTS_DIR,
    _script_lock,
    _validate_nodus_source,
)
from AINDY.routes.platform.schemas import NodusScheduleRequest
from AINDY.services.auth_service import get_current_user

router = APIRouter()


@router.post("/nodus/schedule", status_code=201, response_model=None)
@limiter.limit("30/minute")
def create_nodus_schedule(request: Request, body: NodusScheduleRequest, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    user_id = str(current_user["sub"])
    if body.script:
        _validate_nodus_source(body.script, field="script")
        script_source = body.script
    else:
        with _script_lock:
            record = _NODUS_SCRIPT_REGISTRY.get(body.script_name)
        if not record:
            disk_path = _SCRIPTS_DIR / f"{body.script_name}.nodus"
            if disk_path.exists():
                script_source = disk_path.read_text(encoding="utf-8")
            else:
                raise HTTPException(status_code=404, detail={"error": "script_not_found", "message": f"Script {body.script_name!r} not found. Upload it first via POST /platform/nodus/upload."})
        else:
            script_source = record["content"]
        _validate_nodus_source(script_source, field="script_name")

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


@router.get("/nodus/schedule", response_model=None)
@limiter.limit("60/minute")
def list_nodus_schedules(request: Request, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    from AINDY.runtime.nodus_schedule_service import list_nodus_scheduled_jobs

    jobs = list_nodus_scheduled_jobs(db=db, user_id=str(current_user["sub"]))
    return {"count": len(jobs), "jobs": jobs}


@router.delete("/nodus/schedule/{job_id}", status_code=204, response_model=None)
@limiter.limit("30/minute")
def delete_nodus_schedule(request: Request, job_id: str, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    from AINDY.runtime.nodus_schedule_service import delete_nodus_scheduled_job

    removed = delete_nodus_scheduled_job(db=db, job_id=job_id, user_id=str(current_user["sub"]))
    if not removed:
        raise HTTPException(status_code=404, detail=f"Scheduled job {job_id!r} not found")
    return None
