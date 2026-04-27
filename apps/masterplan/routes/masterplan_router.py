from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from AINDY.core.execution_gate import to_envelope
from AINDY.core.execution_helper import execute_with_pipeline
from AINDY.db.database import get_db
from AINDY.platform_layer.rate_limiter import limiter
from AINDY.services.auth_service import get_current_user

router = APIRouter(prefix="/masterplans", tags=["MasterPlans"])


def _with_execution_envelope(payload):
    envelope = to_envelope(
        eu_id=None,
        trace_id=None,
        status="SUCCESS",
        output=None,
        error=None,
        duration_ms=None,
        attempt_count=1,
    )
    if hasattr(payload, "status_code") and hasattr(payload, "body"):
        return payload
    if isinstance(payload, dict):
        data = payload.get("data")
        result = dict(data) if isinstance(data, dict) else dict(payload)
        result.setdefault("execution_envelope", envelope)
        return result
    return {"data": payload, "execution_envelope": envelope}


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
    from AINDY.runtime.flow_engine import run_flow
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
@limiter.limit("30/minute")
async def lock_from_genesis(
    request: Request,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])

    def handler(ctx):
        from apps.masterplan.services.masterplan_service import lock_from_genesis as svc_lock
        return svc_lock(
            db,
            user_id=user_id,
            session_id=payload.get("session_id"),
            draft=payload.get("draft", {}),
        )

    result = await execute_with_pipeline(
        request=request,
        route_name="masterplan.lock_from_genesis",
        handler=handler,
        user_id=user_id,
        input_payload=payload,
        metadata={"db": db},
    )
    return _with_execution_envelope(result)


# ------------------------------
# LOCK PLAN
# ------------------------------
@router.post("/{plan_id}/lock")
@limiter.limit("30/minute")
def lock_plan(
    request: Request,
    plan_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return _with_execution_envelope(_run_flow_masterplan("masterplan_lock", {"plan_id": plan_id}, db, str(current_user["sub"])))


# ------------------------------
# LIST
# ------------------------------
@router.get("/")
@limiter.limit("60/minute")
async def list_masterplans(
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])

    def handler(ctx):
        from apps.masterplan.services.masterplan_service import list_masterplans as svc_list
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
@limiter.limit("60/minute")
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
@limiter.limit("30/minute")
async def set_masterplan_anchor(
    request: Request,
    plan_id: int,
    body: AnchorRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])

    def handler(ctx):
        from apps.masterplan.services.masterplan_service import set_masterplan_anchor as svc_anchor
        return svc_anchor(
            db,
            user_id=user_id,
            plan_id=plan_id,
            anchor_date=body.anchor_date,
            goal_value=body.goal_value,
            goal_unit=body.goal_unit,
            goal_description=body.goal_description,
        )

    result = await execute_with_pipeline(
        request=request,
        route_name="masterplan.set_anchor",
        handler=handler,
        user_id=user_id,
        input_payload=body.model_dump(),
        metadata={"db": db},
    )
    return _with_execution_envelope(result)


# ------------------------------
# PROJECTION
# ------------------------------
@router.get("/{plan_id}/projection")
@limiter.limit("60/minute")
async def get_masterplan_projection(
    request: Request,
    plan_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])

    def handler(ctx):
        from apps.masterplan.services.masterplan_service import get_masterplan_projection as svc_projection
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
@limiter.limit("30/minute")
def activate_masterplan(
    request: Request,
    plan_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return _with_execution_envelope(_run_flow_masterplan("masterplan_activate", {"plan_id": plan_id}, db, str(current_user["sub"])))


@router.post("/{plan_id}/activate-cascade")
@limiter.limit("30/minute")
async def activate_masterplan_cascade(
    request: Request,
    plan_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])

    def handler(ctx):
        import uuid
        from AINDY.kernel.syscall_dispatcher import SyscallContext, get_dispatcher

        syscall_ctx = SyscallContext(
            execution_unit_id=str(uuid.uuid4()),
            user_id=user_id,
            capabilities=["masterplan.cascade_activate"],
            trace_id="",
            metadata={"_db": db},
        )
        result = get_dispatcher().dispatch(
            "sys.v1.masterplan.cascade_activate",
            {"masterplan_id": str(plan_id), "user_id": user_id},
            syscall_ctx,
        )
        if result["status"] != "success":
            raise HTTPException(status_code=500, detail=result.get("error") or "cascade activation failed")
        data = result.get("data") or {}
        return {
            "activated": data.get("activated_task_ids", []),
            "count": int(data.get("count") or 0),
            "masterplan_id": str(plan_id),
        }

    result = await execute_with_pipeline(
        request=request,
        route_name="masterplan.activate_cascade",
        handler=handler,
        user_id=user_id,
        input_payload={"plan_id": plan_id},
        metadata={"db": db},
    )
    return _with_execution_envelope(result)
