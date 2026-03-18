from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from db.models import MasterPlan, GenesisSessionDB
from services.posture import determine_posture  # adjust import if needed


def create_masterplan_from_genesis(session_id: int, draft: dict, db: Session, user_id: str = None):

    session = db.query(GenesisSessionDB).filter_by(id=session_id).first()

    if not session:
        raise Exception("Genesis session not found")

    if session.status == "locked":
        raise Exception("Session already locked")

    if not session.synthesis_ready:
        raise ValueError("Session is not synthesis-ready — run /genesis/synthesize first")

    # Load draft from session if available; fall back to caller-supplied draft
    draft_to_use = session.draft_json or draft

    # Version label scoped per-user to avoid global numbering pollution
    if user_id:
        user_plans = db.query(MasterPlan).filter(MasterPlan.user_id == user_id).order_by(MasterPlan.id).all()
    else:
        user_plans = db.query(MasterPlan).order_by(MasterPlan.id).all()

    if not user_plans:
        version_label = "V1"
        is_origin = True
        parent_id = None
    else:
        version_label = f"V{len(user_plans) + 1}"
        is_origin = False
        parent_id = user_plans[-1].id

    # Timeline
    horizon = draft_to_use.get("time_horizon_years", 5)
    start_date = datetime.utcnow()
    target_date = start_date + timedelta(days=int(horizon * 365))

    # Posture
    posture = determine_posture(draft_to_use)

    try:
        masterplan = MasterPlan(
            version_label=version_label,
            is_origin=is_origin,
            is_active=False,
            user_id=user_id,
            status="locked",
            structure_json=draft_to_use,
            posture=posture,
            locked_at=start_date,
            start_date=start_date,
            duration_years=horizon,
            target_date=target_date,
            parent_id=parent_id,
            linked_genesis_session_id=session.id
        )

        db.add(masterplan)

        # Freeze Genesis
        session.status = "locked"
        session.locked_at = start_date

        db.commit()
        db.refresh(masterplan)
    except Exception:
        db.rollback()
        raise

    return masterplan

