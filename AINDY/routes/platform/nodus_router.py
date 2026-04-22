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
    _run_nodus_script,
    _script_lock,
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
        with _script_lock:
            record = _NODUS_SCRIPT_REGISTRY.get(body.script_name)
        if not record:
            disk_path = _SCRIPTS_DIR / f"{body.script_name}.nodus"
            if disk_path.exists():
                script_source = disk_path.read_text(encoding="utf-8")
                with _script_lock:
                    _NODUS_SCRIPT_REGISTRY[body.script_name] = {
                        "name": body.script_name,
                        "content": script_source,
                        "restored_from_disk": True,
                        "uploaded_at": None,
                        "uploaded_by": None,
                    }
            else:
                raise HTTPException(status_code=404, detail={"error": "script_not_found", "message": f"Script {body.script_name!r} not found. Upload it first via POST /platform/nodus/upload."})
        else:
            script_source = record["content"]

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
    with _script_lock:
        if body.name in _NODUS_SCRIPT_REGISTRY and not body.overwrite:
            raise HTTPException(status_code=409, detail={"error": "script_already_exists", "message": f"Script {body.name!r} already exists. Set overwrite=true to replace it."})
        try:
            _SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
            (_SCRIPTS_DIR / f"{body.name}.nodus").write_text(body.content, encoding="utf-8")
        except OSError:
            pass
        now = datetime.now(timezone.utc).isoformat()
        meta: Dict[str, Any] = {
            "name": body.name,
            "content": body.content,
            "description": body.description,
            "size_bytes": len(body.content.encode("utf-8")),
            "uploaded_at": now,
            "uploaded_by": user_id,
        }
        _NODUS_SCRIPT_REGISTRY[body.name] = meta
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
    if _SCRIPTS_DIR.exists():
        with _script_lock:
            for script_path in _SCRIPTS_DIR.glob("*.nodus"):
                name = script_path.stem
                if name not in _NODUS_SCRIPT_REGISTRY:
                    try:
                        content = script_path.read_text(encoding="utf-8")
                        _NODUS_SCRIPT_REGISTRY[name] = {"name": name, "content": content, "description": None, "size_bytes": len(content.encode("utf-8")), "uploaded_at": None, "uploaded_by": None}
                    except OSError:
                        pass
    with _script_lock:
        scripts = [
            {
                "name": meta["name"],
                "description": meta.get("description"),
                "size_bytes": meta.get("size_bytes", 0),
                "uploaded_at": meta.get("uploaded_at"),
                "uploaded_by": meta.get("uploaded_by"),
            }
            for meta in reversed(list(_NODUS_SCRIPT_REGISTRY.values()))
        ]
    return {"count": len(scripts), "scripts": scripts}
