from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from db.database import get_db
from db.models import GenesisSessionDB, MasterPlan
from services.genesis_ai import call_genesis_llm, call_genesis_synthesis_llm
from services.masterplan_factory import create_masterplan_from_genesis
from datetime import datetime
from services.auth_service import get_current_user
from services.rate_limiter import limiter

router = APIRouter(prefix="/genesis", tags=["Genesis"])


def _get_user_session(session_id: int, user_id_str: str, db: Session) -> GenesisSessionDB:
    """Retrieve a genesis session owned by the current user or raise 404."""
    session = (
        db.query(GenesisSessionDB)
        .filter(GenesisSessionDB.id == session_id, GenesisSessionDB.user_id_str == user_id_str)
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="GenesisSession not found")
    return session


@router.post("/session")
def create_genesis_session(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id_str = str(current_user["sub"])
    session = GenesisSessionDB(
        user_id_str=user_id_str,
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
    user_id_str = str(current_user["sub"])
    session_id = payload.get("session_id")
    user_message = payload.get("message")

    if not session_id:
        raise HTTPException(status_code=400, detail="session_id is required")
    if not user_message:
        raise HTTPException(status_code=400, detail="message is required")

    session = _get_user_session(session_id, user_id_str, db)

    current_state = session.summarized_state or {}

    llm_output = call_genesis_llm(
        user_message=user_message,
        current_state=current_state
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
    user_id_str = str(current_user["sub"])
    session = _get_user_session(session_id, user_id_str, db)

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
    user_id_str = str(current_user["sub"])
    session = _get_user_session(session_id, user_id_str, db)

    if not session.draft_json:
        raise HTTPException(status_code=404, detail="No draft available yet — run /genesis/synthesize first")

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
    user_id_str = str(current_user["sub"])
    session_id = payload.get("session_id")

    if not session_id:
        raise HTTPException(status_code=400, detail="session_id required")

    session = _get_user_session(session_id, user_id_str, db)

    if not session.synthesis_ready:
        raise HTTPException(
            status_code=422,
            detail="Session is not ready for synthesis yet — continue the conversation until synthesis_ready is true"
        )

    current_state = session.summarized_state or {}
    draft = call_genesis_synthesis_llm(current_state)

    # Persist draft to session
    session.draft_json = draft
    db.commit()

    return {"draft": draft}


@router.post("/lock")
def lock_masterplan(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id_str = str(current_user["sub"])
    session_id = payload.get("session_id")
    draft = payload.get("draft")

    if not session_id or not draft:
        raise HTTPException(status_code=400, detail="Missing session or draft")

    # Validate session ownership before locking
    _get_user_session(session_id, user_id_str, db)

    try:
        masterplan = create_masterplan_from_genesis(
            session_id=session_id,
            draft=draft,
            db=db,
            user_id=user_id_str,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

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
    user_id_str = str(current_user["sub"])

    plan = (
        db.query(MasterPlan)
        .filter(MasterPlan.id == plan_id, MasterPlan.user_id == user_id_str)
        .first()
    )

    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    # Deactivate all plans owned by this user
    db.query(MasterPlan).filter(MasterPlan.user_id == user_id_str).update({"is_active": False})

    # Activate selected
    plan.is_active = True
    plan.status = "active"
    plan.activated_at = datetime.utcnow()

    db.commit()

    return {"status": "activated"}
