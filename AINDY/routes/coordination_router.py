from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from core.execution_helper import execute_with_pipeline_sync
from db.database import get_db
from services.agent_coordinator import coordination_graph
from services.agent_coordinator import get_agent_status
from services.agent_coordinator import list_agents
from services.auth_service import get_current_user


router = APIRouter(prefix="/coordination", tags=["Coordination"])


@router.get("/agents")
def get_agents(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return execute_with_pipeline_sync(
        request=None,
        route_name="coordination.agents.list",
        handler=lambda ctx: list_agents(db),
        user_id=str(current_user["sub"]),
        metadata={"db": db},
    )


@router.get("/agents/status")
def get_agents_status(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return execute_with_pipeline_sync(
        request=None,
        route_name="coordination.agents.status",
        handler=lambda ctx: get_agent_status(db),
        user_id=str(current_user["sub"]),
        metadata={"db": db},
    )


@router.get("/graph")
def get_coordination_graph(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return execute_with_pipeline_sync(
        request=None,
        route_name="coordination.graph.get",
        handler=lambda ctx: coordination_graph(db, user_id=current_user["sub"]),
        user_id=str(current_user["sub"]),
        metadata={"db": db},
    )
