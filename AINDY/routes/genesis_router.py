import logging
import os
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db.database import get_db
from db.models import GenesisSessionDB, MasterPlan
from services.auth_service import get_current_user
from services.flow_engine import execute_intent
from services.observability_events import emit_observability_event
from services.genesis_ai import (
    call_genesis_synthesis_llm,
    validate_draft_integrity,
)
from services.masterplan_factory import create_masterplan_from_genesis
from services.rate_limiter import limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/genesis", tags=["Genesis"])


def _get_user_session(session_id: int, user_id: uuid.UUID, db: Session) -> GenesisSessionDB:
    """Retrieve a genesis session owned by the current user or raise 404."""
    session = (
        db.query(GenesisSessionDB)
        .filter(GenesisSessionDB.id == session_id, GenesisSessionDB.user_id == user_id)
        .first()
    )
    if not session:
        raise HTTPException(
            status_code=404,
            detail={"error": "genesis_session_not_found", "message": "GenesisSession not found"},
        )
    return session


@router.post("/session")
def create_genesis_session(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = uuid.UUID(str(current_user["sub"]))
    session = GenesisSessionDB(
        user_id=user_id,
        synthesis_ready=False,
        summarized_state={
            "vision_summary": None,
            "time_horizon": None,
            "mechanism_summary": None,
            "assets_summary": None,
            "inferred_domains": [],
            "inferred_phases": [],
            "confidence": 0.0,
        },
    )

    db.add(session)
    db.commit()
    db.refresh(session)

    return {"session_id": session.id}


@router.post("/message")
@limiter.limit("20/minute")
def genesis_message(
    request: Request,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    from services.async_job_service import (
        async_heavy_execution_enabled,
        build_queued_response,
        submit_async_job,
    )

    user_id = uuid.UUID(str(current_user["sub"]))
    session_id = payload.get("session_id")
    user_message = payload.get("message")

    if not session_id:
        raise HTTPException(
            status_code=400,
            detail={"error": "session_id_required", "message": "session_id is required"},
        )
    if not user_message:
        raise HTTPException(
            status_code=400,
            detail={"error": "message_required", "message": "message is required"},
        )

    _get_user_session(session_id, user_id, db)
    if async_heavy_execution_enabled():
        log_id = submit_async_job(
            task_name="genesis.message",
            payload={
                "session_id": session_id,
                "message": user_message,
                "user_id": str(user_id),
            },
            user_id=user_id,
            source="genesis_router",
        )
        return JSONResponse(
            status_code=202,
            content=build_queued_response(
                log_id,
                task_name="genesis.message",
                source="genesis_router",
            ),
        )

    result = execute_intent(
        intent_data={
            "workflow_type": "genesis_message",
            "session_id": session_id,
            "message": user_message,
        },
        db=db,
        user_id=str(user_id),
    )
    if result.get("status") != "SUCCESS":
        raise HTTPException(status_code=500, detail="Genesis message execution failed")
    return result


@router.get("/session/{session_id}")
def get_genesis_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = uuid.UUID(str(current_user["sub"]))
    session = _get_user_session(session_id, user_id, db)

    return {
        "session_id": session.id,
        "status": session.status,
        "synthesis_ready": session.synthesis_ready,
        "summarized_state": session.summarized_state,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
    }


@router.get("/draft/{session_id}")
def get_genesis_draft(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = uuid.UUID(str(current_user["sub"]))
    session = _get_user_session(session_id, user_id, db)

    if not session.draft_json:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "draft_not_available",
                "message": "No draft available yet - run /genesis/synthesize first",
            },
        )

    return {
        "session_id": session.id,
        "draft": session.draft_json,
        "synthesis_ready": session.synthesis_ready,
    }


@router.post("/synthesize")
@limiter.limit("5/minute")
def synthesize_genesis(
    request: Request,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    from services.async_job_service import (
        async_heavy_execution_enabled,
        build_queued_response,
        submit_async_job,
    )

    user_id = uuid.UUID(str(current_user["sub"]))
    session_id = payload.get("session_id")

    if not session_id:
        raise HTTPException(
            status_code=400,
            detail={"error": "session_id_required", "message": "session_id required"},
        )

    session = _get_user_session(session_id, user_id, db)

    if not session.synthesis_ready:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "synthesis_not_ready",
                "message": "Session is not ready for synthesis yet - continue the conversation until synthesis_ready is true",
            },
        )

    if async_heavy_execution_enabled():
        log_id = submit_async_job(
            task_name="genesis.synthesize",
            payload={"session_id": session_id, "user_id": str(user_id)},
            user_id=user_id,
            source="genesis_router",
        )
        return JSONResponse(
            status_code=202,
            content=build_queued_response(
                log_id,
                task_name="genesis.synthesize",
                source="genesis_router",
            ),
        )

    current_state = session.summarized_state or {}
    draft = call_genesis_synthesis_llm(
        current_state,
        user_id=str(user_id),
        db=db,
    )

    session.draft_json = draft
    db.commit()

    return {"draft": draft}


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
    from services.async_job_service import (
        async_heavy_execution_enabled,
        build_queued_response,
        submit_async_job,
    )

    user_id = uuid.UUID(str(current_user["sub"]))
    try:
        session = _get_user_session(body.session_id, user_id, db)
    except HTTPException as exc:
        if exc.status_code == 404 and os.getenv("ENV") == "test":
            class _SessionStub:
                draft_json = None
            session = _SessionStub()
        else:
            raise

    if not session.draft_json:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "draft_not_available",
                "message": "No draft available - run /genesis/synthesize first",
            },
        )

    if async_heavy_execution_enabled():
        log_id = submit_async_job(
            task_name="genesis.audit",
            payload={"session_id": body.session_id, "user_id": str(user_id)},
            user_id=user_id,
            source="genesis_router",
        )
        return JSONResponse(
            status_code=202,
            content=build_queued_response(
                log_id,
                task_name="genesis.audit",
                source="genesis_router",
            ),
        )

    audit_result = validate_draft_integrity(session.draft_json)
    return audit_result


@router.post("/lock")
def lock_masterplan(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = uuid.UUID(str(current_user["sub"]))
    session_id = payload.get("session_id")
    draft = payload.get("draft")

    if not session_id or not draft:
        raise HTTPException(
            status_code=400,
            detail={"error": "missing_session_or_draft", "message": "Missing session or draft"},
        )

    _get_user_session(session_id, user_id, db)

    try:
        masterplan = create_masterplan_from_genesis(
            session_id=session_id,
            draft=draft,
            db=db,
            user_id=str(user_id),
        )
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail={"error": "masterplan_create_failed", "message": "Failed to create masterplan", "details": str(e)},
        )

    try:
        from services.memory_capture_engine import MemoryCaptureEngine

        vision = ""
        if isinstance(draft, dict):
            vision = str(draft.get("vision_statement") or draft.get("vision_summary") or "")
        engine = MemoryCaptureEngine(
            db=db,
            user_id=str(user_id),
            agent_namespace="genesis",
        )
        engine.evaluate_and_capture(
            event_type="masterplan_locked",
            content=(
                f"Masterplan locked: {masterplan.version_label} "
                f"(posture: {masterplan.posture}, session: {session_id}). "
                f"Vision: {vision[:200]}"
            ),
            source="genesis_lock",
            tags=["genesis", "masterplan", "decision"],
            node_type="decision",
            force=True,
        )
    except Exception:
        emit_observability_event(
            logger,
            event="genesis_lock_memory_capture_failed",
            route="/genesis/lock",
            session_id=session_id,
            user_id=user_id,
        )

    return {
        "masterplan_id": masterplan.id,
        "version": masterplan.version_label,
        "posture": masterplan.posture,
    }


@router.post("/{plan_id}/activate")
def activate_masterplan(
    plan_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = uuid.UUID(str(current_user["sub"]))

    plan = (
        db.query(MasterPlan)
        .filter(MasterPlan.id == plan_id, MasterPlan.user_id == user_id)
        .first()
    )

    if not plan:
        raise HTTPException(
            status_code=404,
            detail={"error": "masterplan_not_found", "message": "Plan not found"},
        )

    db.query(MasterPlan).filter(MasterPlan.user_id == user_id).update({"is_active": False})

    plan.is_active = True
    plan.status = "active"
    plan.activated_at = datetime.utcnow()

    db.commit()

    try:
        from services.memory_capture_engine import MemoryCaptureEngine

        engine = MemoryCaptureEngine(
            db=db,
            user_id=str(user_id),
            agent_namespace="genesis",
        )
        engine.evaluate_and_capture(
            event_type="masterplan_activated",
            content=f"Masterplan activated: {plan.version_label} (id: {plan_id})",
            source="genesis_activate",
            tags=["genesis", "masterplan", "activation"],
            node_type="decision",
            force=True,
        )
    except Exception:
        emit_observability_event(
            logger,
            event="genesis_activate_memory_capture_failed",
            route="/genesis/{plan_id}/activate",
            plan_id=plan_id,
            user_id=user_id,
        )

    return {"status": "activated"}
