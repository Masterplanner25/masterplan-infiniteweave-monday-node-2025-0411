from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional

from core.execution_helper import execute_with_pipeline
from db.database import get_db
from db.models import MasterPlan
from services.auth_service import get_current_user
from services.masterplan_factory import create_masterplan_from_genesis
from services.masterplan_execution_service import (
    get_masterplan_execution_status,
    sync_masterplan_tasks,
)
from services.posture import posture_description

router = APIRouter(prefix="/masterplans", tags=["MasterPlans"])


# ------------------------------
# LOCK FROM GENESIS
# ------------------------------
@router.post("/lock")
def lock_from_genesis(
    request: Request,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    def handler(ctx):
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
                detail={
                    "error": "masterplan_validation_failed",
                    "message": "Masterplan validation failed",
                    "details": str(e),
                },
            )
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "masterplan_create_failed",
                    "message": "Failed to create masterplan",
                    "details": str(e),
                },
            )

        task_sync = sync_masterplan_tasks(db=db, masterplan=masterplan, user_id=user_id_str)

        return {
            "masterplan_id": masterplan.id,
            "version": masterplan.version_label,
            "posture_description": posture_description(masterplan.posture),
            "posture": masterplan.posture,
            "status": masterplan.status,
            "task_sync": task_sync,
        }

    return execute_with_pipeline(request, "masterplan_lock_from_genesis", handler)


# ------------------------------
# LOCK PLAN
# ------------------------------
@router.post("/{plan_id}/lock")
def lock_plan(
    request: Request,
    plan_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    def handler(ctx):
        user_id_str = str(current_user["sub"])

        plan = (
            db.query(MasterPlan)
            .filter(MasterPlan.id == plan_id, MasterPlan.user_id == user_id_str)
            .first()
        )

        if not plan:
            raise HTTPException(404, detail={"error": "masterplan_not_found", "message": "Plan not found"})

        if plan.status == "locked":
            raise HTTPException(400, detail={"error": "masterplan_already_locked", "message": "Plan is already locked"})

        plan.status = "locked"
        plan.locked_at = datetime.utcnow()
        db.commit()

        task_sync = sync_masterplan_tasks(db=db, masterplan=plan, user_id=user_id_str)

        return {"plan_id": plan.id, "status": plan.status, "task_sync": task_sync}

    return execute_with_pipeline(request, "masterplan_lock", handler)


# ------------------------------
# LIST
# ------------------------------
@router.get("/")
def list_masterplans(
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    def handler(ctx):
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

    return execute_with_pipeline(request, "masterplan_list", handler)


# ------------------------------
# GET SINGLE
# ------------------------------
@router.get("/{plan_id}")
def get_masterplan(
    request: Request,
    plan_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    def handler(ctx):
        user_id_str = str(current_user["sub"])

        plan = (
            db.query(MasterPlan)
            .filter(MasterPlan.id == plan_id, MasterPlan.user_id == user_id_str)
            .first()
        )

        if not plan:
            raise HTTPException(404, detail={"error": "masterplan_not_found", "message": "Plan not found"})

        execution_status = get_masterplan_execution_status(
            db=db, masterplan_id=plan.id, user_id=user_id_str
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
            "execution_status": execution_status,
        }

    return execute_with_pipeline(request, "masterplan_get", handler)


# ------------------------------
# ANCHOR
# ------------------------------
class AnchorRequest(BaseModel):
    anchor_date: Optional[str] = None
    goal_value: Optional[float] = None
    goal_unit: Optional[str] = None
    goal_description: Optional[str] = None


@router.put("/{plan_id}/anchor")
def set_masterplan_anchor(
    request: Request,
    plan_id: int,
    body: AnchorRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    def handler(ctx):
        user_id_str = str(current_user["sub"])

        plan = (
            db.query(MasterPlan)
            .filter(MasterPlan.id == plan_id, MasterPlan.user_id == user_id_str)
            .first()
        )

        if not plan:
            raise HTTPException(404, detail={"error": "masterplan_not_found", "message": "Plan not found"})

        if body.anchor_date is not None:
            try:
                plan.anchor_date = datetime.fromisoformat(body.anchor_date)
            except ValueError:
                raise HTTPException(422, detail={"error": "invalid_anchor_date", "message": "anchor_date must be ISO format"})

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

    return execute_with_pipeline(request, "masterplan_anchor", handler)


# ------------------------------
# PROJECTION
# ------------------------------
@router.get("/{plan_id}/projection")
def get_masterplan_projection(
    request: Request,
    plan_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    def handler(ctx):
        user_id_str = str(current_user["sub"])

        plan = (
            db.query(MasterPlan)
            .filter(MasterPlan.id == plan_id, MasterPlan.user_id == user_id_str)
            .first()
        )

        if not plan:
            raise HTTPException(404, detail={"error": "masterplan_not_found", "message": "Plan not found"})

        from services.eta_service import calculate_eta

        try:
            return calculate_eta(db=db, masterplan_id=plan_id, user_id=user_id_str)
        except Exception as exc:
            raise HTTPException(500, detail={"error": "eta_calculation_failed", "message": str(exc)})

    return execute_with_pipeline(request, "masterplan_projection", handler)


# ------------------------------
# ACTIVATE
# ------------------------------
@router.post("/{plan_id}/activate")
def activate_masterplan(
    request: Request,
    plan_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    def handler(ctx):
        user_id_str = str(current_user["sub"])

        plan = (
            db.query(MasterPlan)
            .filter(MasterPlan.id == plan_id, MasterPlan.user_id == user_id_str)
            .first()
        )

        if not plan:
            raise HTTPException(404, detail={"error": "masterplan_not_found", "message": "Plan not found"})

        db.query(MasterPlan).filter(MasterPlan.user_id == user_id_str).update({"is_active": False})

        plan.is_active = True
        plan.status = "active"
        plan.activated_at = datetime.utcnow()
        db.commit()

        task_sync = sync_masterplan_tasks(db=db, masterplan=plan, user_id=user_id_str)
        execution_status = get_masterplan_execution_status(
            db=db, masterplan_id=plan.id, user_id=user_id_str
        )

        return {
            "status": "activated",
            "plan_id": plan.id,
            "task_sync": task_sync,
            "execution_status": execution_status,
        }

    return execute_with_pipeline(request, "masterplan_activate", handler)