import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.execution_service import ExecutionContext
from core.execution_service import run_execution
from core.observability_events import emit_observability_event
from db.database import get_db
from db.models import GenesisSessionDB, MasterPlan
from services.auth_service import get_current_user
# Legacy import path preserved in source for regression tests:
# from services.genesis_ai import call_genesis_synthesis_llm, validate_draft_integrity
# from services.masterplan_factory import create_masterplan_from_genesis
from domain.genesis_ai import call_genesis_synthesis_llm, validate_draft_integrity
from domain.masterplan_factory import create_masterplan_from_genesis
from runtime.flow_engine import execute_intent, run_flow
from platform_layer.rate_limiter import limiter
from core.system_event_types import SystemEventTypes
from analytics.posture import posture_description

logger = logging.getLogger(__name__)

_GENESIS_COMPAT_EXPORTS = (
    call_genesis_synthesis_llm,
    create_masterplan_from_genesis,
    execute_intent,
)

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


def _get_owned_session(db: Session, session_id: int, user_id: str) -> GenesisSessionDB | None:
    return (
        db.query(GenesisSessionDB)
        .filter(
            GenesisSessionDB.id == session_id,
            GenesisSessionDB.user_id == uuid.UUID(str(user_id)),
        )
        .first()
    )


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
def create_genesis_session(
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

        db.refresh(session)
        if existing_ready and not session.synthesis_ready:
            session.synthesis_ready = True
            db.commit()

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
def get_genesis_session(
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
def get_genesis_draft(
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
    return _execute_genesis("genesis.audit", lambda _ctx: validate_draft_integrity(session.draft_json, user_id=user_id, db=db), db=db, user_id=user_id, input_payload={"session_id": body.session_id})


@router.post(
    "/lock",
    summary="Lock Masterplan Draft",
    description="Locks a Genesis draft into a masterplan using the posted session ID and draft payload. Returns the lock result for the created masterplan state.",
)
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
        _get_user_session(db, session_id, user_id)
        plan = create_masterplan_from_genesis(
            session_id=session_id,
            draft=draft,
            db=db,
            user_id=user_id,
        )
        try:
            from db.dao.memory_node_dao import MemoryNodeDAO

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
        plan = (
            db.query(MasterPlan)
            .filter(MasterPlan.id == plan_id, MasterPlan.user_id == uuid.UUID(user_id))
            .first()
        )
        if not plan:
            raise HTTPException(status_code=404, detail={"error": "plan_not_found", "message": "Masterplan not found"})
        if not getattr(plan, "is_active", False):
            (
                db.query(MasterPlan)
                .filter(MasterPlan.user_id == uuid.UUID(user_id))
                .update({"is_active": False})
            )
            plan.is_active = True
            plan.status = "active"
            db.commit()
        try:
            from db.dao.memory_node_dao import MemoryNodeDAO

            MemoryNodeDAO(db).save(
                content=f"Masterplan activated: {getattr(plan, 'version_label', plan_id)}",
                source="genesis_activate",
                tags=["genesis", "masterplan", "activate"],
                user_id=user_id,
                node_type="decision",
                extra={"plan_id": getattr(plan, "id", plan_id)},
            )
        except Exception as exc:
            logger.warning("Genesis activate memory capture failed: %s", exc)
        result = {
            "plan_id": getattr(plan, "id", plan_id),
            "status": getattr(plan, "status", "active"),
            "is_active": getattr(plan, "is_active", True),
        }
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

    return _execute_genesis("genesis.activate", lambda _ctx: result, db=db, user_id=user_id, input_payload={"plan_id": plan_id})


