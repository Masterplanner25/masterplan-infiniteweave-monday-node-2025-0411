from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from AINDY.core.execution_gate import to_envelope
from AINDY.core.execution_helper import execute_with_pipeline_sync
from AINDY.db.database import get_db
from AINDY.platform_layer.rate_limiter import limiter
from AINDY.services.auth_service import get_current_user


router = APIRouter(prefix="/goals", tags=["Goals"])


def _execute_goals(request: Request, route_name: str, handler, *, db: Session, user_id: str, input_payload=None, success_status_code: int = 200):
    result = execute_with_pipeline_sync(
        request=request,
        route_name=route_name,
        handler=handler,
        user_id=user_id,
        input_payload=input_payload or {},
        metadata={"db": db, "source": "goals_router"},
        success_status_code=success_status_code,
        return_result=True,
    )
    if not result.success:
        detail = result.metadata.get("detail") or result.error or "Execution failed"
        raise HTTPException(
            status_code=int(result.metadata.get("status_code", 500)),
            detail=detail,
        )
    eu_id = result.metadata.get("eu_id")
    if eu_id is None:
        raise HTTPException(status_code=500, detail="Execution pipeline did not attach eu_id")
    data = result.data
    if isinstance(data, dict):
        data = dict(data)
        _envelope_status = "SUCCESS"
        if hasattr(result, "data") and isinstance(result.data, dict):
            _raw_status = str(result.data.get("status") or "").upper()
            if _raw_status in {"SUCCESS", "FAILURE", "FAILED", "WAITING", "QUEUED", "ERROR", "UNKNOWN"}:
                _envelope_status = _raw_status
        data.setdefault(
            "execution_envelope",
            to_envelope(
                eu_id=eu_id,
                trace_id=result.metadata.get("trace_id"),
                status=_envelope_status,
                output=None,
                error=result.metadata.get("error") or (
                    result.data.get("error") if isinstance(
                        getattr(result, "data", None), dict
                    ) else None
                ),
                duration_ms=None,
                attempt_count=None,
            ),
        )
    return data


class GoalCreateRequest(BaseModel):
    name: str
    description: str | None = None
    goal_type: str = "strategic"
    priority: float = 0.5
    status: str = "active"
    success_metric: dict = Field(default_factory=dict)


def _do_create_goal(db: Session, body: GoalCreateRequest, user_id: str):
    from AINDY.runtime.flow_engine import run_flow

    result = run_flow(
        "goal_create",
        {
            "name": body.name,
            "description": body.description,
            "goal_type": body.goal_type,
            "priority": body.priority,
            "status": body.status,
            "success_metric": body.success_metric,
        },
        db=db,
        user_id=user_id,
    )
    if result.get("status") == "error":
        raise RuntimeError(
            (result.get("data") or {}).get("message", "Goal create flow failed")
        )
    return result.get("data")


@router.get("")
@limiter.limit("60/minute")
def list_goals(
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])
    def handler(_ctx):
        from AINDY.runtime.flow_engine import run_flow
        result = run_flow("goals_list", {}, db=db, user_id=user_id)
        if result.get("status") == "error":
            raise RuntimeError((result.get("data") or {}).get("message", "Goals list flow failed"))
        return result.get("data")
    return _execute_goals(request, "goals.list", handler, db=db, user_id=user_id)


@router.post("", status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
def create_goal_route(
    request: Request,
    body: GoalCreateRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])
    def handler(_ctx):
        return _do_create_goal(db, body, user_id)
    return _execute_goals(
        request,
        "goals.create",
        handler,
        db=db,
        user_id=user_id,
        input_payload=body.model_dump(),
        success_status_code=status.HTTP_201_CREATED,
    )


@router.get("/state")
@limiter.limit("60/minute")
def list_goal_state(
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])
    def handler(_ctx):
        from AINDY.runtime.flow_engine import run_flow
        result = run_flow("goals_state", {}, db=db, user_id=user_id)
        if result.get("status") == "error":
            raise RuntimeError((result.get("data") or {}).get("message", "Goals state flow failed"))
        return result.get("data")
    return _execute_goals(request, "goals.state", handler, db=db, user_id=user_id)

