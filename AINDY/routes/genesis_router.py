from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from db.database import get_db
from db.models import GenesisSessionDB
from services.genesis_ai import call_genesis_llm
from datetime import datetime, timedelta

router = APIRouter(prefix="/genesis", tags=["Genesis"])


@router.post("/session")
def create_genesis_session(db: Session = Depends(get_db)):
    session = GenesisSessionDB(
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
def genesis_message(payload: dict, db: Session = Depends(get_db)):

    session_id = payload.get("session_id")
    user_message = payload.get("message")

    if not session_id:
        raise HTTPException(status_code=400, detail="session_id is required")

    if not user_message:
        raise HTTPException(status_code=400, detail="message is required")

    session = db.query(GenesisSessionDB).filter_by(id=session_id).first()

    if not session:
        raise HTTPException(status_code=404, detail="GenesisSession not found")

    current_state = session.summarized_state or {}

    # 🧠 CALL AI SERVICE
    llm_output = call_genesis_llm(
        user_message=user_message,
        current_state=current_state
    )

    reply = llm_output.get("reply", "")
    state_update = llm_output.get("state_update", {})
    synthesis_ready = llm_output.get("synthesis_ready", False)

    # 🧠 MERGE STATE SAFELY
    for key, value in state_update.items():
        if key in current_state and value is not None:
            current_state[key] = value

    # Clamp confidence between 0 and 1
    if "confidence" in current_state:
        current_state["confidence"] = max(
            0.0,
            min(current_state["confidence"], 1.0)
        )

    session.summarized_state = current_state
    db.commit()

    return {
        "reply": reply,
        "synthesis_ready": synthesis_ready
    }

@router.post("/synthesize")
def synthesize_genesis(payload: dict, db: Session = Depends(get_db)):

    session_id = payload.get("session_id")

    if not session_id:
        raise HTTPException(status_code=400, detail="session_id required")

    session = db.query(GenesisSessionDB).filter_by(id=session_id).first()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    current_state = session.summarized_state or {}

    draft = call_genesis_synthesis_llm(current_state)

    return {
        "draft": draft
    }

@router.post("/lock")
def lock_masterplan(payload: dict, db: Session = Depends(get_db)):

    session_id = payload.get("session_id")
    draft = payload.get("draft")

    if not session_id or not draft:
        raise HTTPException(status_code=400, detail="Missing session or draft")

    try:
        masterplan = create_masterplan_from_genesis(
            session_id=session_id,
            draft=draft,
            db=db
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "masterplan_id": masterplan.id,
        "version": masterplan.version_label,
        "posture": masterplan.posture
    }

@router.post("/{plan_id}/activate")
def activate_masterplan(plan_id: int, db: Session = Depends(get_db)):

    plan = db.query(MasterPlan).filter_by(id=plan_id).first()

    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    # Deactivate all
    db.query(MasterPlan).update({"is_active": False})

    # Activate selected
    plan.is_active = True
    plan.activated_at = datetime.utcnow()

    db.commit()

    return {"status": "activated"}


