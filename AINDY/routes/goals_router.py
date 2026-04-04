from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from core.execution_helper import execute_with_pipeline_sync
from db.database import get_db
from services.auth_service import get_current_user


router = APIRouter(prefix="/goals", tags=["Goals"])


def _execute_goals(request: Request, route_name: str, handler, *, db: Session, user_id: str, input_payload=None, success_status_code: int = 200):
    return execute_with_pipeline_sync(
        request=request,
        route_name=route_name,
        handler=handler,
        user_id=user_id,
        input_payload=input_payload,
        metadata={"db": db, "source": "goals_router"},
        success_status_code=success_status_code,
    )


class GoalCreateRequest(BaseModel):
    name: str
    description: str | None = None
    goal_type: str = "strategic"
    priority: float = 0.5
    status: str = "active"
    success_metric: dict = Field(default_factory=dict)


@router.get("")
def list_goals(
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])
    def handler(_ctx):
        from runtime.flow_engine import run_flow
        result = run_flow("goals_list", {}, db=db, user_id=user_id)
        if result.get("status") == "error":
            raise RuntimeError((result.get("data") or {}).get("message", "Goals list flow failed"))
        return result.get("data")
    return _execute_goals(request, "goals.list", handler, db=db, user_id=user_id)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_goal_route(
    request: Request,
    body: GoalCreateRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])

    def handler(_ctx):
        from runtime.flow_engine import run_flow
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

    return _execute_goals(
        request,
        "goals.create",
        handler,
        db=db,
        user_id=user_id,
        input_payload={"goal_name": body.name},
        success_status_code=status.HTTP_201_CREATED,
    )


@router.get("/state")
def list_goal_state(
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])
    def handler(_ctx):
        from runtime.flow_engine import run_flow
        result = run_flow("goals_state", {}, db=db, user_id=user_id)
        if result.get("status") == "error":
            raise RuntimeError((result.get("data") or {}).get("message", "Goals state flow failed"))
        return result.get("data")
    return _execute_goals(request, "goals.state", handler, db=db, user_id=user_id)

