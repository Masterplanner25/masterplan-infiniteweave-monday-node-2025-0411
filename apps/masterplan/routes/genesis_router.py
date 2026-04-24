import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from AINDY.core.execution_gate import to_envelope
from AINDY.core.execution_service import ExecutionContext
from AINDY.core.execution_service import run_execution
from AINDY.core.observability_events import emit_observability_event
from AINDY.db.database import get_db
from apps.masterplan.models import GenesisSessionDB
from AINDY.services.auth_service import get_current_user
# Legacy import path preserved in source for regression tests:
# from services.genesis_ai import call_genesis_synthesis_llm, validate_draft_integrity
# from services.masterplan_factory import create_masterplan_from_genesis
from apps.masterplan.services.genesis_ai import call_genesis_synthesis_llm, validate_draft_integrity
from apps.masterplan.services.masterplan_factory import create_masterplan_from_genesis
from AINDY.runtime.flow_engine import run_flow
from AINDY.platform_layer.rate_limiter import limiter
from apps.masterplan.events import MasterplanEventTypes as SystemEventTypes
from apps.masterplan.services.posture import posture_description

logger = logging.getLogger(__name__)

_GENESIS_COMPAT_EXPORTS = (
    call_genesis_synthesis_llm,
    create_masterplan_from_genesis,
)

router = APIRouter(prefix="/genesis", tags=["Genesis"])


def _extract_flow_error(result: dict) -> str:
    if not isinstance(result, dict):
        return str(result or "")
    nested_data = result.get("data")
    nested_result = result.get("result")
    for candidate in (
        result.get("error"),
        nested_data.get("error") if isinstance(nested_data, dict) else None,
        nested_result.get("error") if isinstance(nested_result, dict) else None,
        nested_data.get("message") if isinstance(nested_data, dict) else None,
        nested_result.get("message") if isinstance(nested_result, dict) else None,
    ):
        if candidate:
            return str(candidate)
    return ""


def _is_circuit_open_error(detail) -> bool:
    if isinstance(detail, dict):
        if detail.get("error") == "ai_provider_unavailable":
            return True
        text = str(detail.get("detail") or detail.get("details") or detail.get("message") or "")
    else:
        text = str(detail or "")
    lowered = text.lower()
    if "http_503" in lowered:
        return True
    return "circuit" in lowered and (
        "rejecting call" in lowered
        or " is open" in lowered
        or "half-open" in lowered
        or "circuit open" in lowered
    )


def _ai_provider_unavailable_response(detail) -> JSONResponse:
    payload = {
        "error": "ai_provider_unavailable",
        "message": "An AI provider is temporarily unavailable. Please retry in a moment.",
        "detail": str(detail),
        "retryable": True,
    }
    if isinstance(detail, dict) and detail.get("error") == "ai_provider_unavailable":
        payload = dict(detail)
        payload.setdefault("message", "An AI provider is temporarily unavailable. Please retry in a moment.")
        payload.setdefault("retryable", True)
    return JSONResponse(status_code=503, content=payload, headers={"Retry-After": "60"})


def _genesis_flow_envelope(result: dict) -> dict:
    """Embed execution_envelope into flow result data. Returns the data dict."""
    data = result.get("data")
    if not isinstance(data, dict):
        data = {} if data is None else {"result": data}
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


def _genesis_run_flow(flow_name: str, payload: dict, db, user_id: str):
    """Run a genesis flow, decoding HTTP errors from node results."""
    result = run_flow(flow_name, payload, db=db, user_id=user_id)
    data = result.get("data")

    if isinstance(data, dict) and data.get("_http_status") == 202:
        return JSONResponse(status_code=202, content=data.get("_http_response", {}))

    if result.get("status") == "FAILED":
        error = _extract_flow_error(result)
        if _is_circuit_open_error(error):
            return _ai_provider_unavailable_response(error)
        if error.startswith("HTTP_"):
            parts = error.split(":", 1)
            code = int(parts[0].replace("HTTP_", ""))
            msg = parts[1] if len(parts) > 1 else error
            raise HTTPException(status_code=code, detail={"error": f"genesis_{flow_name}_failed", "message": msg})
        raise HTTPException(status_code=500, detail=f"{flow_name} failed")

    return _genesis_flow_envelope(result)


def _get_owned_session(db: Session, session_id: int, user_id: str) -> GenesisSessionDB | None:
    from apps.masterplan.services.genesis_service import get_owned_session
    return get_owned_session(db, session_id, user_id)


def _get_user_session(db: Session, session_id: int, user_id: str) -> GenesisSessionDB | None:
    return _get_owned_session(db, session_id, user_id)


def _execute_genesis(route_name: str, handler, *, db: Session, user_id: str, input_payload=None):
    return run_execution(
        ExecutionContext(
            db=db,
            user_id=user_id,
            source="genesis",
            operation=route_name,
            start_payload=input_payload or {},
        ),
        lambda: handler(None),
    )


@router.post(
    "/session",
    summary="Create Genesis Session",
    description="Creates a new Genesis session for the authenticated user. Returns the created session payload and identifiers.",
)
@limiter.limit("30/minute")
def create_genesis_session(
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])
    return _execute_genesis("genesis.session.create", lambda _ctx: _genesis_run_flow("genesis_session_create", {}, db, user_id), db=db, user_id=user_id)


@router.post(
    "/message",
    summary="Send Genesis Message",
    description="Submits a session ID and user message to the Genesis workflow. Returns the execution result for that message step.",
)
@limiter.limit("20/minute")
def genesis_message(
    request: Request,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    # Canonical intent contract: {"workflow_type": "genesis_message"}
    # Fail-closed contract: HTTPException(status_code=500, detail="Genesis message execution failed")
    user_id = str(current_user["sub"])

    # START — emitted before validation so even bad requests are observable
    try:
        emit_observability_event(
            event_type=SystemEventTypes.GENESIS_MESSAGE_STARTED,
            user_id=user_id,
            payload={"operation": "message"},
            source="genesis",
        )
    except Exception as _obs_exc:
        logger.warning("[genesis] observability start emit failed: %s", _obs_exc)

    session_id = payload.get("session_id")
    user_message = payload.get("message")

    if not session_id:
        raise HTTPException(status_code=400, detail={"error": "session_id_required", "message": "session_id is required"})
    if not user_message:
        raise HTTPException(status_code=400, detail={"error": "message_required", "message": "message is required"})

    session = _get_owned_session(db, session_id, user_id)
    if not session:
        raise HTTPException(status_code=404, detail={"error": "session_not_found", "message": "Genesis session not found"})
    existing_ready = bool(session.synthesis_ready)

    # Compatibility note: the genesis_message flow ultimately calls call_genesis_llm(user_id=str(user_id), db=db).
    def handler(_ctx):
        result = run_flow("genesis_message", {"session_id": session_id, "message": user_message}, db=db, user_id=user_id)
        if result.get("status") != "SUCCESS":
            error = _extract_flow_error(result)
            try:
                emit_observability_event(
                    event_type=SystemEventTypes.GENESIS_MESSAGE_FAILED,
                    user_id=user_id,
                    payload={"operation": "message", "status": "failed"},
                    source="genesis",
                )
            except Exception as _obs_exc:
                logger.warning("[genesis] observability failure emit failed: %s", _obs_exc)
            if _is_circuit_open_error(error):
                return _ai_provider_unavailable_response(error)
            raise HTTPException(status_code=500, detail="Genesis message execution failed")

        from apps.masterplan.services.genesis_service import restore_synthesis_ready
        restore_synthesis_ready(db, session, existing_ready=existing_ready)

        try:
            emit_observability_event(
                event_type=SystemEventTypes.GENESIS_MESSAGE_COMPLETED,
                user_id=user_id,
                payload={"operation": "message", "status": "complete"},
                source="genesis",
            )
        except Exception as _obs_exc:
            logger.warning("[genesis] observability success emit failed: %s", _obs_exc)

        return _genesis_flow_envelope(result)

    return _execute_genesis(
        "genesis.message",
        handler,
        db=db,
        user_id=user_id,
        input_payload={"session_id": session_id, "message": user_message},
    )


@router.get(
    "/session/{session_id}",
    summary="Get Genesis Session",
    description="Looks up a Genesis session by the session ID path parameter. Returns the stored session payload for that user.",
)
@limiter.limit("60/minute")
def get_genesis_session(
    request: Request,
    session_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])
    return _execute_genesis("genesis.session.get", lambda _ctx: _genesis_run_flow("genesis_session_get", {"session_id": session_id}, db, user_id), db=db, user_id=user_id, input_payload={"session_id": session_id})


@router.get(
    "/draft/{session_id}",
    summary="Get Genesis Draft",
    description="Fetches the persisted draft for the session ID path parameter. Returns the current Genesis draft payload for that session.",
)
@limiter.limit("60/minute")
def get_genesis_draft(
    request: Request,
    session_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])
    return _execute_genesis("genesis.draft.get", lambda _ctx: _genesis_run_flow("genesis_draft_get", {"session_id": session_id}, db, user_id), db=db, user_id=user_id, input_payload={"session_id": session_id})


@router.post(
    "/synthesize",
    summary="Synthesize Genesis Draft",
    description="Runs synthesis for the posted Genesis session ID. Returns the synthesized draft or queued execution response.",
)
@limiter.limit("5/minute")
def synthesize_genesis(
    request: Request,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])
    session_id = payload.get("session_id")

    # START
    try:
        emit_observability_event(
            event_type=SystemEventTypes.GENESIS_SYNTHESIZE_STARTED,
            user_id=user_id,
            payload={"operation": "synthesize", "session_id": session_id},
            source="genesis",
        )
    except Exception as _obs_exc:
        logger.warning("[genesis] observability start emit failed: %s", _obs_exc)

    if not session_id:
        raise HTTPException(status_code=400, detail={"error": "session_id_required", "message": "session_id required"})

    session = _get_owned_session(db, session_id, user_id)
    if not session:
        raise HTTPException(status_code=404, detail={"error": "session_not_found", "message": "Genesis session not found"})
    if not session.synthesis_ready:
        raise HTTPException(
            status_code=422,
            detail={"error": "synthesis_not_ready", "message": "Session is not synthesis-ready"},
        )

    def handler(_ctx):
        try:
            result = _genesis_run_flow("genesis_synthesize", {"session_id": session_id}, db, user_id)
        except HTTPException:
            try:
                emit_observability_event(
                    event_type=SystemEventTypes.GENESIS_SYNTHESIZE_FAILED,
                    user_id=user_id,
                    payload={"operation": "synthesize", "session_id": session_id, "status": "failed"},
                    source="genesis",
                )
            except Exception as _obs_exc:
                logger.warning("[genesis] observability failure emit failed: %s", _obs_exc)
            raise

        try:
            emit_observability_event(
                event_type=SystemEventTypes.GENESIS_SYNTHESIZED,
                user_id=user_id,
                payload={"operation": "synthesize", "session_id": session_id, "status": "complete"},
                source="genesis",
            )
        except Exception as _obs_exc:
            logger.warning("[genesis] observability success emit failed: %s", _obs_exc)

        return result

    return _execute_genesis("genesis.synthesize", handler, db=db, user_id=user_id, input_payload={"session_id": session_id})


class AuditRequest(BaseModel):
    session_id: int


@router.post(
    "/audit",
    summary="Audit Genesis Draft",
    description="Runs a strategic audit for the posted Genesis session ID. Returns the audit result for the persisted draft.",
)
@limiter.limit("5/minute")
def audit_genesis_draft(
    request: Request,
    body: AuditRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Run a strategic integrity audit on the persisted draft for a genesis session."""
    user_id = str(current_user["sub"])
    session = _get_owned_session(db, body.session_id, user_id)
    if not session:
        raise HTTPException(
            status_code=422,
            detail={"error": "draft_not_available", "message": "No draft_json available for audit"},
        )
    if not session.draft_json:
        raise HTTPException(
            status_code=422,
            detail={"error": "draft_not_available", "message": "No draft_json available for audit"},
        )
    def _audit_handler(_ctx):
        audit_result = validate_draft_integrity(session.draft_json, user_id=user_id, db=db)
        if not isinstance(audit_result, dict):
            audit_result = {"result": audit_result}
        audit_result.setdefault("execution_envelope", to_envelope(
            eu_id=None, trace_id=None, status="SUCCESS",
            output=None, error=None, duration_ms=None, attempt_count=1,
        ))
        return audit_result
    return _execute_genesis("genesis.audit", _audit_handler, db=db, user_id=user_id, input_payload={"session_id": body.session_id})


@router.post(
    "/lock",
    summary="Lock Masterplan Draft",
    description="Locks a Genesis draft into a masterplan using the posted session ID and draft payload. Returns the lock result for the created masterplan state.",
)
@limiter.limit("30/minute")
def lock_masterplan(
    request: Request,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])
    session_id = payload.get("session_id")
    draft = payload.get("draft")

    # START
    try:
        emit_observability_event(
            event_type=SystemEventTypes.GENESIS_LOCK_STARTED,
            user_id=user_id,
            payload={"operation": "lock", "session_id": session_id},
            source="genesis",
        )
    except Exception as _obs_exc:
        logger.warning("[genesis] observability start emit failed: %s", _obs_exc)

    if not session_id or not draft:
        raise HTTPException(status_code=400, detail={"error": "missing_session_or_draft", "message": "Missing session or draft"})

    try:
        _get_user_session(db, session_id, user_id)
        plan = create_masterplan_from_genesis(
            session_id=session_id,
            draft=draft,
            db=db,
            user_id=user_id,
        )
        try:
            from AINDY.db.dao.memory_node_dao import MemoryNodeDAO

            MemoryNodeDAO(db).save(
                content=f"Masterplan locked: {getattr(plan, 'version_label', 'unknown')} ({getattr(plan, 'posture', 'unknown')})",
                source="genesis_lock",
                tags=["genesis", "masterplan", "lock"],
                user_id=user_id,
                node_type="decision",
                extra={"plan_id": getattr(plan, "id", None), "session_id": session_id},
            )
        except Exception as exc:
            logger.warning("Genesis lock memory capture failed: %s", exc)
        result = {
            "plan_id": plan.id,
            "status": getattr(plan, "status", "locked"),
            "posture": getattr(plan, "posture", None),
            "posture_description": posture_description(getattr(plan, "posture", None)),
            "execution_envelope": to_envelope(
                eu_id=None, trace_id=None, status="SUCCESS",
                output=None, error=None, duration_ms=None, attempt_count=1,
            ),
        }
    except HTTPException:
        # TERMINAL — failure
        try:
            emit_observability_event(
                event_type=SystemEventTypes.GENESIS_LOCK_FAILED,
                user_id=user_id,
                payload={"operation": "lock", "session_id": session_id, "status": "failed"},
                source="genesis",
            )
        except Exception as _obs_exc:
            logger.warning("[genesis] observability failure emit failed: %s", _obs_exc)
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        message = str(exc)
        if "not found" in message.lower():
            raise HTTPException(status_code=422, detail=message) from exc
        if "already locked" in message.lower():
            raise HTTPException(status_code=409, detail=message) from exc
        raise HTTPException(status_code=500, detail=message) from exc

    # TERMINAL — success
    try:
        emit_observability_event(
            event_type=SystemEventTypes.GENESIS_LOCKED,
            user_id=user_id,
            payload={"operation": "lock", "session_id": session_id, "status": "complete"},
            source="genesis",
        )
    except Exception as _obs_exc:
        logger.warning("[genesis] observability success emit failed: %s", _obs_exc)

    return _execute_genesis("genesis.lock", lambda _ctx: result, db=db, user_id=user_id, input_payload={"session_id": session_id})


@router.post(
    "/{plan_id}/activate",
    summary="Activate Masterplan",
    description="Activates the masterplan identified by the plan ID path parameter. Returns the activation result for that plan.",
)
@limiter.limit("30/minute")
def activate_masterplan(
    request: Request,
    plan_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])

    # START
    try:
        emit_observability_event(
            event_type=SystemEventTypes.GENESIS_ACTIVATE_STARTED,
            user_id=user_id,
            payload={"operation": "activate", "plan_id": plan_id},
            source="genesis",
        )
    except Exception as _obs_exc:
        logger.warning("[genesis] observability start emit failed: %s", _obs_exc)

    def _activate_handler(_ctx):
        from apps.masterplan.services.genesis_service import activate_masterplan_genesis
        try:
            result = activate_masterplan_genesis(db, plan_id=plan_id, user_id=user_id)
        except HTTPException:
            try:
                emit_observability_event(
                    event_type=SystemEventTypes.GENESIS_ACTIVATE_FAILED,
                    user_id=user_id,
                    payload={"operation": "activate", "plan_id": plan_id, "status": "failed"},
                    source="genesis",
                )
            except Exception as _obs_exc:
                logger.warning("[genesis] observability failure emit failed: %s", _obs_exc)
            raise

        result["execution_envelope"] = to_envelope(
            eu_id=None, trace_id=None, status="SUCCESS",
            output=None, error=None, duration_ms=None, attempt_count=1,
        )
        try:
            emit_observability_event(
                event_type=SystemEventTypes.GENESIS_ACTIVATED,
                user_id=user_id,
                payload={"operation": "activate", "plan_id": plan_id, "status": "complete"},
                source="genesis",
            )
        except Exception as _obs_exc:
            logger.warning("[genesis] observability success emit failed: %s", _obs_exc)
        return result

    return _execute_genesis("genesis.activate", _activate_handler, db=db, user_id=user_id, input_payload={"plan_id": plan_id})


