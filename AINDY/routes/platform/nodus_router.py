from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from AINDY.core.execution_helper import execute_with_pipeline_sync
from AINDY.db.database import get_db
from AINDY.platform_layer.rate_limiter import limiter
from AINDY.routes.platform.nodus_shared import (
    _NODUS_SCRIPT_REGISTRY,
    _SCRIPTS_DIR,
    _format_nodus_response,
    list_nodus_script_summaries,
    load_named_nodus_script_or_404,
    nodus_script_exists,
    _run_nodus_script,
    save_nodus_script,
    _validate_nodus_source,
)
from AINDY.routes.platform.schemas import NodusRunRequest, NodusScriptUpload
from AINDY.services.auth_service import get_current_user

router = APIRouter()


@router.post("/nodus/run", response_model=None)
@limiter.limit("30/minute")
def run_nodus_script(request: Request, body: NodusRunRequest, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    user_id = str(current_user["sub"])
    if body.script:
        script_source = body.script
        _validate_nodus_source(script_source, field="script")
    else:
        script_source = load_named_nodus_script_or_404(body.script_name)

    def handler(_ctx):
        from AINDY.core.execution_gate import flow_result_to_envelope

        flow_result = _run_nodus_script(
            script=script_source,
            input_payload=body.input,
            error_policy=body.error_policy,
            db=db,
            user_id=user_id,
        )
        formatted = _format_nodus_response(flow_result)
        formatted.setdefault("execution_envelope", flow_result_to_envelope(flow_result))
        return formatted

    return execute_with_pipeline_sync(
        request=request,
        route_name="platform.nodus.run",
        handler=handler,
        user_id=user_id,
        input_payload={"script_name": body.script_name, "has_inline_script": bool(body.script), "error_policy": body.error_policy, **body.input},
        metadata={"db": db},
    )


@router.post("/nodus/upload", status_code=201, response_model=None)
@limiter.limit("30/minute")
def upload_nodus_script(request: Request, body: NodusScriptUpload, current_user: dict = Depends(get_current_user)):
    user_id = str(current_user["sub"])
    _validate_nodus_source(body.content, field="content")
    if nodus_script_exists(body.name) and not body.overwrite:
        raise HTTPException(status_code=409, detail={"error": "script_already_exists", "message": f"Script {body.name!r} already exists. Set overwrite=true to replace it."})

    try:
        _SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
        (_SCRIPTS_DIR / f"{body.name}.nodus").write_text(body.content, encoding="utf-8")
    except OSError:
        pass
    now = datetime.now(timezone.utc).isoformat()
    meta = save_nodus_script(
        name=body.name,
        content=body.content,
        description=body.description,
        uploaded_at=now,
        uploaded_by=user_id,
    )
    return {
        "name": meta["name"],
        "description": meta["description"],
        "size_bytes": meta["size_bytes"],
        "uploaded_at": meta["uploaded_at"],
        "uploaded_by": meta["uploaded_by"],
    }


@router.get("/nodus/scripts", response_model=None)
@limiter.limit("60/minute")
def list_nodus_scripts(request: Request, current_user: dict = Depends(get_current_user)):
    scripts = list_nodus_script_summaries()
    return {"count": len(scripts), "scripts": scripts}
