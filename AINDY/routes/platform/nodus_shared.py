import inspect
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from AINDY.db.database import get_db
from AINDY.platform_layer.nodus_script_store import (
    _NODUS_SCRIPT_REGISTRY,
    _SCRIPTS_DIR,
    _script_lock,
    list_script_metadata,
    load_script_source,
    script_exists,
    store_script,
)


def _run_flow_platform(flow_name: str, state: dict, db: Session, user_id: str | None) -> dict:
    from AINDY.core.execution_gate import flow_result_to_envelope
    from AINDY.runtime.flow_engine import run_flow

    result = run_flow(flow_name, state, db=db, user_id=user_id)
    if result.get("status") == "FAILED":
        error = result.get("error", "")
        if error.startswith("HTTP_"):
            parts = error.split(":", 1)
            code = int(parts[0].replace("HTTP_", ""))
            msg = parts[1] if len(parts) > 1 else error
            raise HTTPException(status_code=code, detail=msg)
        raise HTTPException(status_code=500, detail=error or f"{flow_name} failed")
    result.setdefault("execution_envelope", flow_result_to_envelope(result))
    return result


def _ensure_nodus_flow_registered() -> None:
    from AINDY.runtime.nodus_execution_service import ensure_nodus_script_flow_registered

    ensure_nodus_script_flow_registered()


def _run_nodus_script(
    *,
    script: str,
    input_payload: dict,
    error_policy: str,
    db: Session,
    user_id: str,
) -> dict:
    from AINDY.runtime.nodus_execution_service import run_nodus_script_via_flow

    return run_nodus_script_via_flow(
        script=script,
        input_payload=input_payload,
        error_policy=error_policy,
        db=db,
        user_id=user_id,
    )


def _format_nodus_response(flow_result: dict) -> dict:
    from AINDY.runtime.nodus_execution_service import format_nodus_flow_result

    return format_nodus_flow_result(flow_result)


def _validate_nodus_source(source: str, field: str = "script") -> None:
    from AINDY.runtime.nodus_security import NodusSecurityError, validate_nodus_source

    try:
        validate_nodus_source(source)
    except NodusSecurityError as exc:
        raise HTTPException(
            status_code=422,
            detail={"error": "nodus_security_violation", "message": str(exc), "field": field},
        )


def load_named_nodus_script_or_404(name: str) -> str:
    script_source = load_script_source(name)
    if script_source is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "script_not_found",
                "message": f"Script {name!r} not found. Upload it first via POST /platform/nodus/upload.",
            },
        )
    return script_source


def save_nodus_script(
    *,
    name: str,
    content: str,
    description: str | None,
    uploaded_at: str | None,
    uploaded_by: str | None,
) -> dict[str, Any]:
    return store_script(
        name=name,
        content=content,
        description=description,
        uploaded_at=uploaded_at,
        uploaded_by=uploaded_by,
    )


def list_nodus_script_summaries() -> list[dict[str, Any]]:
    return list_script_metadata(include_disk=True)


def nodus_script_exists(name: str) -> bool:
    return script_exists(name)


def resolve_request_db_override(request, db: Session):
    """
    Prefer an app-level get_db override when it returns a direct value.

    Some endpoint tests install a simple ``lambda: sentinel`` override instead of
    a generator dependency. FastAPI can still resolve the real Session object in
    those import-order cases, so the route normalizes to the explicit override
    here before invoking downstream helpers. Generator-based overrides are left
    untouched because the dependency system already manages their lifecycle.
    """
    app = getattr(request, "app", None)
    overrides = getattr(app, "dependency_overrides", None)
    if not overrides:
        return db

    override = overrides.get(get_db)
    if override is None:
        return db

    try:
        candidate = override()
    except Exception:
        return db

    if candidate is None or inspect.isgenerator(candidate):
        return db
    return candidate
