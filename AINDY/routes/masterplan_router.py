from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db.database import get_db
from db.models import MasterPlan
from services.auth_service import get_current_user
from domain.masterplan_factory import create_masterplan_from_genesis
from analytics.posture import posture_description

router = APIRouter(prefix="/masterplans", tags=["MasterPlans"])


def _flow_failure(result: dict) -> str:
    direct_error = result.get("error")
    if isinstance(direct_error, str) and direct_error:
        return direct_error
    for key in ("data", "result"):
        payload = result.get(key)
        if isinstance(payload, dict):
            nested_error = payload.get("error") or payload.get("message")
            if isinstance(nested_error, str) and nested_error:
                return nested_error
    return ""


def _masterplan_http_detail(code: int, message: str):
    normalized = str(message or "").strip()
    lowered = normalized.lower()
    if code == 404 and "plan not found" in lowered:
        return {"error": "masterplan_not_found", "message": "Masterplan not found"}
    if code == 422 and "anchor_date must be iso format" in lowered:
        return {"error": "invalid_anchor_date", "message": "anchor_date must be ISO format"}
    return normalized or f"HTTP_{code}"


def _run_flow_masterplan(flow_name: str, payload: dict, db: Session, user_id: str):
    from runtime.flow_engine import run_flow
    result = run_flow(flow_name, payload, db=db, user_id=user_id)
    if result.get("status") == "FAILED":
        error = _flow_failure(result)
        if error.startswith("HTTP_"):
            parts = error.split(":", 1)
            code = int(parts[0].replace("HTTP_", ""))
            msg = parts[1] if len(parts) > 1 else error
            raise HTTPException(status_code=code, detail=_masterplan_http_detail(code, msg))
        raise HTTPException(status_code=500, detail=error or f"{flow_name} failed")
    return result.get("data")


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
    session_id = payload.get("session_id")
    draft = payload.get("draft", {})
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id is required")
    try:
        plan = create_masterplan_from_genesis(
            session_id=session_id,
            draft=draft,
            db=db,
            user_id=str(current_user["sub"]),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        message = str(exc)
        if "not found" in message.lower():
            raise HTTPException(status_code=422, detail=message) from exc
        if "already locked" in message.lower():
            raise HTTPException(status_code=409, detail=message) from exc
        raise HTTPException(status_code=500, detail=message) from exc

    return {
        "plan_id": plan.id,
        "status": plan.status,
        "posture": plan.posture,
        "posture_description": posture_description(plan.posture),
    }


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
    return _run_flow_masterplan("masterplan_lock", {"plan_id": plan_id}, db, str(current_user["sub"]))


# ------------------------------
# LIST
# ------------------------------
@router.get("/")
def list_masterplans(
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    plans = (
        db.query(MasterPlan)
        .filter(MasterPlan.user_id == current_user["sub"])
        .order_by(MasterPlan.id.desc())
        .all()
    )
    return {
        "plans": [
            {
                "id": plan.id,
                "status": plan.status,
                "posture": plan.posture,
                "is_active": plan.is_active,
                "locked_at": plan.locked_at.isoformat() if plan.locked_at else None,
                "created_at": plan.created_at.isoformat() if plan.created_at else None,
            }
            for plan in plans
        ]
    }


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
    return _run_flow_masterplan("masterplan_get", {"plan_id": plan_id}, db, str(current_user["sub"]))


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
    from datetime import datetime

    plan = (
        db.query(MasterPlan)
        .filter(MasterPlan.id == plan_id, MasterPlan.user_id == current_user["sub"])
        .first()
    )
    if not plan:
        raise HTTPException(
            status_code=404,
            detail={"error": "masterplan_not_found", "message": "Masterplan not found"},
        )

    if body.anchor_date is not None:
        try:
            plan.anchor_date = datetime.fromisoformat(body.anchor_date)
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail={"error": "invalid_anchor_date", "message": "anchor_date must be ISO format"},
            ) from exc
    if body.goal_value is not None:
        plan.goal_value = body.goal_value
    if body.goal_unit is not None:
        plan.goal_unit = body.goal_unit
    if body.goal_description is not None:
        plan.goal_description = body.goal_description

    db.commit()
    db.refresh(plan)
    return {
        "plan_id": plan.id,
        "anchor_date": plan.anchor_date.isoformat() if plan.anchor_date else None,
        "goal_value": plan.goal_value,
        "goal_unit": plan.goal_unit,
        "goal_description": plan.goal_description,
    }


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
    plan = (
        db.query(MasterPlan)
        .filter(MasterPlan.id == plan_id, MasterPlan.user_id == current_user["sub"])
        .first()
    )
    if not plan:
        raise HTTPException(
            status_code=404,
            detail={"error": "masterplan_not_found", "message": "Masterplan not found"},
        )
    try:
        from analytics import eta_service

        return eta_service.calculate_eta(db=db, masterplan_id=plan_id, user_id=current_user["sub"])
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={"error": "eta_calculation_failed", "message": str(exc)},
        ) from exc


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
    return _run_flow_masterplan("masterplan_activate", {"plan_id": plan_id}, db, str(current_user["sub"]))

