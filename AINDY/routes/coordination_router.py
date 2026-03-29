from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from db.database import get_db
from services.agent_coordinator import coordination_graph
from services.agent_coordinator import get_agent_status
from services.agent_coordinator import list_agents
from services.auth_service import get_current_user
from services.execution_envelope import success
from utils.trace_context import ensure_trace_id


router = APIRouter(tags=["Coordination"])


@router.get("/agents")
def get_agents(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return success(list_agents(db), [], ensure_trace_id())


@router.get("/agents/status")
def get_agents_status(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return success(get_agent_status(db), [], ensure_trace_id())


@router.get("/coordination/graph")
def get_coordination_graph(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return success(
        coordination_graph(db, user_id=current_user["sub"]),
        [],
        ensure_trace_id(),
    )
