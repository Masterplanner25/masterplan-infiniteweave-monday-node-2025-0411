import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.observability_events import emit_observability_event
from db.database import get_db
from services.auth_service import get_current_user
from services.flow_engine import run_flow
from services.rate_limiter import limiter
from services.system_event_types import SystemEventTypes

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/genesis", tags=["Genesis"])


def _genesis_run_flow(flow_name: str, payload: dict, db, user_id: str):
    """Run a genesis flow, decoding HTTP errors from node results."""
    result = run_flow(flow_name, payload, db=db, user_id=user_id)
    data = result.get("data")

    if isinstance(data, dict) and data.get("_http_status") == 202:
        return JSONResponse(status_code=202, content=data.get("_http_response", {}))

    if result.get("status") == "FAILED":
        error = result.get("error", "")
        if error.startswith("HTTP_"):
            parts = error.split(":", 1)
            code = int(parts[0].replace("HTTP_", ""))
            msg = parts[1] if len(parts) > 1 else error
            raise HTTPException(status_code=code, detail={"error": f"genesis_{flow_name}_failed", "message": msg})
        raise HTTPException(status_code=500, detail=f"{flow_name} failed")

    return data


@router.post("/session")
def create_genesis_session(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])
    return _genesis_run_flow("genesis_session_create", {}, db, user_id)


@router.post("/message")
@limiter.limit("20/minute")
def genesis_message(
    request: Request,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
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

    result = run_flow("genesis_message", {"session_id": session_id, "message": user_message}, db=db, user_id=user_id)
    if result.get("status") != "SUCCESS":
        # TERMINAL — failure
        try:
            emit_observability_event(
                event_type=SystemEventTypes.GENESIS_MESSAGE_FAILED,
                user_id=user_id,
                payload={"operation": "message", "status": "failed"},
                source="genesis",
            )
        except Exception as _obs_exc:
            logger.warning("[genesis] observability failure emit failed: %s", _obs_exc)
        raise HTTPException(status_code=500, detail="Genesis message execution failed")

    # TERMINAL — success
    try:
        emit_observability_event(
            event_type=SystemEventTypes.GENESIS_MESSAGE_COMPLETED,
            user_id=user_id,
            payload={"operation": "message", "status": "complete"},
            source="genesis",
        )
    except Exception as _obs_exc:
        logger.warning("[genesis] observability success emit failed: %s", _obs_exc)

    return result


@router.get("/session/{session_id}")
def get_genesis_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return _genesis_run_flow("genesis_session_get", {"session_id": session_id}, db, str(current_user["sub"]))


@router.get("/draft/{session_id}")
def get_genesis_draft(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return _genesis_run_flow("genesis_draft_get", {"session_id": session_id}, db, str(current_user["sub"]))


@router.post("/synthesize")
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

    try:
        result = _genesis_run_flow("genesis_synthesize", {"session_id": session_id}, db, user_id)
    except HTTPException:
        # TERMINAL — failure
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

    # TERMINAL — success
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


class AuditRequest(BaseModel):
    session_id: int


@router.post("/audit")
@limiter.limit("5/minute")
def audit_genesis_draft(
    request: Request,
    body: AuditRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Run a strategic integrity audit on the persisted draft for a genesis session."""
    return _genesis_run_flow("genesis_audit", {"session_id": body.session_id}, db, str(current_user["sub"]))


@router.post("/lock")
def lock_masterplan(
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
        result = _genesis_run_flow("genesis_lock", {"session_id": session_id, "draft": draft}, db, user_id)
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

    return result


@router.post("/{plan_id}/activate")
def activate_masterplan(
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

    try:
        result = _genesis_run_flow("genesis_activate", {"plan_id": plan_id}, db, user_id)
    except HTTPException:
        # TERMINAL — failure
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

    # TERMINAL — success
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
