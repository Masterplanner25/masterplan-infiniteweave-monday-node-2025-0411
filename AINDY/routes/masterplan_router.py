from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from db.database import get_db
from db.models import MasterPlan
from services.auth_service import get_current_user
from services.masterplan_factory import create_masterplan_from_genesis
from services.posture import posture_description
from datetime import datetime
from typing import Optional

router = APIRouter(prefix="/masterplans", tags=["MasterPlans"])


@router.post("/lock")
def lock_from_genesis(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Create and lock a MasterPlan from a completed Genesis session."""
    # Response includes posture_description for UI display.
    # ValueError from factory maps to 422.
    user_id_str = str(current_user["sub"])
    session_id = payload.get("session_id")
    draft = payload.get("draft", {})

    if not session_id:
        raise HTTPException(
            status_code=400,
            detail={"error": "session_id_required", "message": "session_id is required"},
        )

    try:
        masterplan = create_masterplan_from_genesis(
            session_id=session_id,
            draft=draft,
            db=db,
            user_id=user_id_str,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=422,
            detail={"error": "masterplan_validation_failed", "message": "Masterplan validation failed", "details": str(e)},
        )
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail={"error": "masterplan_create_failed", "message": "Failed to create masterplan", "details": str(e)},
        )

    return {
        "masterplan_id": masterplan.id,
        "version": masterplan.version_label,
        "posture_description": posture_description(masterplan.posture),
        "posture": masterplan.posture,
        "status": masterplan.status,
    }


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
        raise HTTPException(
            status_code=404,
            detail={"error": "masterplan_not_found", "message": "Plan not found"},
        )
    if plan.status == "locked":
        raise HTTPException(
            status_code=400,
            detail={"error": "masterplan_already_locked", "message": "Plan is already locked"},
        )

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
    return {
        "plans": [
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
    }


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
        raise HTTPException(
            status_code=404,
            detail={"error": "masterplan_not_found", "message": "Plan not found"},
        )
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


class AnchorRequest(BaseModel):
    anchor_date: Optional[str] = None      # ISO date string e.g. "2027-01-01"
    goal_value: Optional[float] = None
    goal_unit: Optional[str] = None
    goal_description: Optional[str] = None


@router.put("/{plan_id}/anchor")
def set_masterplan_anchor(
    plan_id: int,
    body: AnchorRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Set or update the anchor (user-declared milestone) on a masterplan."""
    user_id_str = str(current_user["sub"])
    plan = (
        db.query(MasterPlan)
        .filter(MasterPlan.id == plan_id, MasterPlan.user_id == user_id_str)
        .first()
    )
    if not plan:
        raise HTTPException(
            status_code=404,
            detail={"error": "masterplan_not_found", "message": "Plan not found"},
        )

    if body.anchor_date is not None:
        try:
            plan.anchor_date = datetime.fromisoformat(body.anchor_date)
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail={"error": "invalid_anchor_date", "message": "anchor_date must be ISO format (YYYY-MM-DD)"},
            )
    if body.goal_value is not None:
        plan.goal_value = body.goal_value
    if body.goal_unit is not None:
        plan.goal_unit = body.goal_unit
    if body.goal_description is not None:
        plan.goal_description = body.goal_description

    db.commit()

    return {
        "plan_id": plan.id,
        "anchor_date": plan.anchor_date.isoformat() if plan.anchor_date else None,
        "goal_value": plan.goal_value,
        "goal_unit": plan.goal_unit,
        "goal_description": plan.goal_description,
    }


@router.get("/{plan_id}/projection")
def get_masterplan_projection(
    plan_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Compute (or return cached) ETA projection for a masterplan."""
    user_id_str = str(current_user["sub"])
    plan = (
        db.query(MasterPlan)
        .filter(MasterPlan.id == plan_id, MasterPlan.user_id == user_id_str)
        .first()
    )
    if not plan:
        raise HTTPException(
            status_code=404,
            detail={"error": "masterplan_not_found", "message": "Plan not found"},
        )

    from services.eta_service import calculate_eta
    try:
        result = calculate_eta(db=db, masterplan_id=plan_id, user_id=user_id_str)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={"error": "eta_calculation_failed", "message": str(exc)},
        )
    return result


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
        raise HTTPException(
            status_code=404,
            detail={"error": "masterplan_not_found", "message": "Plan not found"},
        )

    # Single active masterplan invariant — deactivate all user plans first
    db.query(MasterPlan).filter(MasterPlan.user_id == user_id_str).update({"is_active": False})

    plan.is_active = True
    plan.status = "active"
    plan.activated_at = datetime.utcnow()
    db.commit()

    return {"status": "activated", "plan_id": plan.id}
