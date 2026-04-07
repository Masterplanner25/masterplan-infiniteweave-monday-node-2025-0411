from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.execution_helper import execute_with_pipeline
from db.database import get_db
from services.auth_service import get_current_user

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
async def lock_from_genesis(
    request: Request,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])

    def handler(ctx):
        from domain.masterplan_service import lock_from_genesis as svc_lock
        return svc_lock(
            db,
            user_id=user_id,
            session_id=payload.get("session_id"),
            draft=payload.get("draft", {}),
        )

    return await execute_with_pipeline(
        request=request,
        route_name="masterplan.lock_from_genesis",
        handler=handler,
        user_id=user_id,
        input_payload=payload,
        metadata={"db": db},
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
async def list_masterplans(
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])

    def handler(ctx):
        from domain.masterplan_service import list_masterplans as svc_list
        return svc_list(db, user_id=user_id)

    return await execute_with_pipeline(
        request=request,
        route_name="masterplan.list",
        handler=handler,
        user_id=user_id,
        metadata={"db": db},
    )


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
async def set_masterplan_anchor(
    request: Request,
    plan_id: int,
    body: AnchorRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])

    def handler(ctx):
        from domain.masterplan_service import set_masterplan_anchor as svc_anchor
        return svc_anchor(
            db,
            user_id=user_id,
            plan_id=plan_id,
            anchor_date=body.anchor_date,
            goal_value=body.goal_value,
            goal_unit=body.goal_unit,
            goal_description=body.goal_description,
        )

    return await execute_with_pipeline(
        request=request,
        route_name="masterplan.set_anchor",
        handler=handler,
        user_id=user_id,
        input_payload=body.model_dump(),
        metadata={"db": db},
    )


# ------------------------------
# PROJECTION
# ------------------------------
@router.get("/{plan_id}/projection")
async def get_masterplan_projection(
    request: Request,
    plan_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])

    def handler(ctx):
        from domain.masterplan_service import get_masterplan_projection as svc_projection
        return svc_projection(db, user_id=user_id, plan_id=plan_id)

    return await execute_with_pipeline(
        request=request,
        route_name="masterplan.projection",
        handler=handler,
        user_id=user_id,
        input_payload={"plan_id": plan_id},
        metadata={"db": db},
    )


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
