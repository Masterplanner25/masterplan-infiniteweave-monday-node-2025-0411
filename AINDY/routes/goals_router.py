from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from db.database import get_db
from services.auth_service import get_current_user
from services.goal_service import create_goal
from services.goal_service import detect_goal_drift
from services.goal_service import get_active_goals
from services.goal_service import get_goal_states
from services.execution_service import ExecutionContext, run_execution


router = APIRouter(prefix="/goals", tags=["Goals"])


class GoalCreateRequest(BaseModel):
    name: str
    description: str | None = None
    goal_type: str = "strategic"
    priority: float = 0.5
    status: str = "active"
    success_metric: dict = Field(default_factory=dict)


@router.get("")
def list_goals(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return run_execution(
        ExecutionContext(
            db=db,
            user_id=str(current_user["sub"]),
            source="goals_router",
            operation="goals.list",
        ),
        lambda: get_active_goals(db, current_user["sub"]),
    )


@router.post("", status_code=status.HTTP_201_CREATED)
def create_goal_route(
    body: GoalCreateRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return run_execution(
        ExecutionContext(
            db=db,
            user_id=str(current_user["sub"]),
            source="goals_router",
            operation="goals.create",
            start_payload={"goal_name": body.name},
        ),
        lambda: create_goal(
            db,
            user_id=current_user["sub"],
            name=body.name,
            description=body.description,
            goal_type=body.goal_type,
            priority=body.priority,
            status=body.status,
            success_metric=body.success_metric,
        ),
        success_status_code=status.HTTP_201_CREATED,
    )


@router.get("/state")
def list_goal_state(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return run_execution(
        ExecutionContext(
            db=db,
            user_id=str(current_user["sub"]),
            source="goals_router",
            operation="goals.state",
        ),
        lambda: {
            "goals": get_goal_states(db, current_user["sub"]),
            "drift": detect_goal_drift(db, current_user["sub"]),
        },
    )
