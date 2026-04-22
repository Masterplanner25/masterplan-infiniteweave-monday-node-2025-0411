from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from AINDY.routes.platform.schemas import _NODUS_SCRIPT_REGISTRY, _SCRIPTS_DIR, _script_lock


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
