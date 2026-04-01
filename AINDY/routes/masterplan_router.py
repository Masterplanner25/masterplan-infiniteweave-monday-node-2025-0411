from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db.database import get_db
from services.auth_service import get_current_user

router = APIRouter(prefix="/masterplans", tags=["MasterPlans"])


def _run_flow_masterplan(flow_name: str, payload: dict, db: Session, user_id: str):
    from services.flow_engine import run_flow
    result = run_flow(flow_name, payload, db=db, user_id=user_id)
    if result.get("status") == "FAILED":
        error = result.get("error", "")
        if error.startswith("HTTP_"):
            parts = error.split(":", 1)
            code = int(parts[0].replace("HTTP_", ""))
            msg = parts[1] if len(parts) > 1 else error
            raise HTTPException(status_code=code, detail=msg)
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
    return _run_flow_masterplan(
        "masterplan_lock_from_genesis",
        {"session_id": payload.get("session_id"), "draft": payload.get("draft", {})},
        db, str(current_user["sub"]),
    )


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
    return _run_flow_masterplan("masterplan_list", {}, db, str(current_user["sub"]))


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
    return _run_flow_masterplan(
        "masterplan_anchor",
        {
            "plan_id": plan_id,
            "anchor_date": body.anchor_date,
            "goal_value": body.goal_value,
            "goal_unit": body.goal_unit,
            "goal_description": body.goal_description,
        },
        db, str(current_user["sub"]),
    )


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
    return _run_flow_masterplan("masterplan_projection", {"plan_id": plan_id}, db, str(current_user["sub"]))


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
