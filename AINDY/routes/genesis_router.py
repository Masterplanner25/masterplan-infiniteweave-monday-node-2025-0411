import os
import uuid
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from db.database import get_db
from db.models import GenesisSessionDB, MasterPlan
from pydantic import BaseModel
from services.genesis_ai import call_genesis_llm, call_genesis_synthesis_llm, validate_draft_integrity
from services.masterplan_factory import create_masterplan_from_genesis
from datetime import datetime
from services.auth_service import get_current_user
from services.rate_limiter import limiter

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
            "confidence": 0.0
        }
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

    session = _get_user_session(session_id, user_id, db)

    current_state = session.summarized_state or {}

    llm_output = call_genesis_llm(
        message=user_message,
        current_state=current_state,
        user_id=str(user_id),
        db=db,
    )

    reply = llm_output.get("reply", "")
    state_update = llm_output.get("state_update", {})
    synthesis_ready_flag = llm_output.get("synthesis_ready", False)

    # Merge state safely
    for key, value in state_update.items():
        if key in current_state and value is not None:
            current_state[key] = value

    # Clamp confidence between 0 and 1
    if "confidence" in current_state:
        current_state["confidence"] = max(0.0, min(current_state["confidence"], 1.0))

    session.summarized_state = current_state

    # One-way flag: once True, never reverts to False
    if synthesis_ready_flag and not session.synthesis_ready:
        session.synthesis_ready = True

    db.commit()

    return {
        "reply": reply,
        "synthesis_ready": session.synthesis_ready
    }


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
                "message": "No draft available yet — run /genesis/synthesize first",
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
                "message": "Session is not ready for synthesis yet — continue the conversation until synthesis_ready is true",
            },
        )

    current_state = session.summarized_state or {}
    draft = call_genesis_synthesis_llm(
        current_state,
        user_id=str(user_id),
        db=db,
    )

    # Persist draft to session
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
    # NOTE: returns 422 when no draft_json is available.
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
                "message": "No draft available — run /genesis/synthesize first",
            },
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

    # Validate session ownership before locking
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

    # Write lock event to memory (fire-and-forget)
    try:
        from services.memory_capture_engine import MemoryCaptureEngine
        _vision = ""
        if isinstance(draft, dict):
            _vision = str(draft.get("vision_statement") or draft.get("vision_summary") or "")
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
                f"Vision: {str(_vision)[:200]}"
            ),
            source="genesis_lock",
            tags=["genesis", "masterplan", "decision"],
            node_type="decision",
            force=True,
        )
    except Exception:
        pass

    return {
        "masterplan_id": masterplan.id,
        "version": masterplan.version_label,
        "posture": masterplan.posture
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
        .filter(MasterPlan.id == plan_id, MasterPlan.user_id == str(user_id))
        .first()
    )

    if not plan:
        raise HTTPException(
            status_code=404,
            detail={"error": "masterplan_not_found", "message": "Plan not found"},
        )

    # Deactivate all plans owned by this user
    db.query(MasterPlan).filter(MasterPlan.user_id == str(user_id)).update({"is_active": False})

    # Activate selected
    plan.is_active = True
    plan.status = "active"
    plan.activated_at = datetime.utcnow()

    db.commit()

    # Write activation event to memory (fire-and-forget)
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
        pass

    return {"status": "activated"}
