from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from db.models import MasterPlan, GenesisSessionDB
from services.posture import determine_posture  # adjust import if needed


def create_masterplan_from_genesis(session_id: int, draft: dict, db: Session):

    session = db.query(GenesisSessionDB).filter_by(id=session_id).first()

    if not session:
        raise Exception("Genesis session not found")

    if session.status == "locked":
        raise Exception("Session already locked")

    existing_plans = db.query(MasterPlan).order_by(MasterPlan.id).all()

    if not existing_plans:
        version_label = "V1"
        is_origin = True
        parent_id = None
    else:
        version_label = f"V{len(existing_plans) + 1}"
        is_origin = False
        parent_id = existing_plans[-1].id

    # Timeline
    horizon = draft.get("time_horizon_years", 5)
    start_date = datetime.utcnow()
    target_date = start_date + timedelta(days=int(horizon * 365))

    # Posture
    posture = determine_posture(draft)

    masterplan = MasterPlan(
        version_label=version_label,
        is_origin=is_origin,
        is_active=False,
        structure_json=draft,
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

    db.commit()
    db.refresh(masterplan)

    return masterplan

