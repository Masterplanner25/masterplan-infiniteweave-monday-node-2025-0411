from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from db.database import get_db
from db.models import MasterPlan
from services.auth_service import get_current_user
from datetime import datetime

router = APIRouter(prefix="/masterplans", tags=["MasterPlans"])


@router.post("/{plan_id}/lock")
def lock_plan(
    plan_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Transition a draft plan to locked status."""
    user_id_str = str(current_user["sub"])
    plan = (
        db.query(MasterPlan)
        .filter(MasterPlan.id == plan_id, MasterPlan.user_id == user_id_str)
        .first()
    )
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    if plan.status == "locked":
        raise HTTPException(status_code=400, detail="Plan is already locked")

    plan.status = "locked"
    plan.locked_at = datetime.utcnow()
    db.commit()

    return {"plan_id": plan.id, "status": plan.status}


@router.get("/")
def list_masterplans(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """List all master plans owned by the current user."""
    user_id_str = str(current_user["sub"])
    plans = (
        db.query(MasterPlan)
        .filter(MasterPlan.user_id == user_id_str)
        .order_by(MasterPlan.id.desc())
        .all()
    )
    return [
        {
            "id": p.id,
            "version_label": p.version_label,
            "posture": p.posture,
            "status": p.status,
            "is_active": p.is_active,
            "created_at": p.created_at,
            "locked_at": p.locked_at,
            "activated_at": p.activated_at,
        }
        for p in plans
    ]


@router.get("/{plan_id}")
def get_masterplan(
    plan_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get a single master plan owned by the current user."""
    user_id_str = str(current_user["sub"])
    plan = (
        db.query(MasterPlan)
        .filter(MasterPlan.id == plan_id, MasterPlan.user_id == user_id_str)
        .first()
    )
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    return {
        "id": plan.id,
        "version_label": plan.version_label,
        "posture": plan.posture,
        "status": plan.status,
        "is_active": plan.is_active,
        "structure_json": plan.structure_json,
        "created_at": plan.created_at,
        "locked_at": plan.locked_at,
        "activated_at": plan.activated_at,
        "linked_genesis_session_id": plan.linked_genesis_session_id,
    }


@router.post("/{plan_id}/activate")
def activate_masterplan(
    plan_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Activate a locked plan, deactivating all other plans for this user."""
    user_id_str = str(current_user["sub"])
    plan = (
        db.query(MasterPlan)
        .filter(MasterPlan.id == plan_id, MasterPlan.user_id == user_id_str)
        .first()
    )
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    # Single active masterplan invariant — deactivate all user plans first
    db.query(MasterPlan).filter(MasterPlan.user_id == user_id_str).update({"is_active": False})

    plan.is_active = True
    plan.status = "active"
    plan.activated_at = datetime.utcnow()
    db.commit()

    return {"status": "activated", "plan_id": plan.id}
