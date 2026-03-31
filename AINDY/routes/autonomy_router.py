from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from core.execution_helper import execute_with_pipeline_sync
from db.database import get_db
from services.auth_service import get_current_user
from services.autonomous_controller import list_recent_decisions


router = APIRouter(prefix="/autonomy", tags=["Autonomy"])


@router.get("/decisions")
def get_recent_autonomy_decisions(
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return execute_with_pipeline_sync(
        request=None,
        route_name="autonomy.decisions.list",
        handler=lambda ctx: list_recent_decisions(db, user_id=current_user["sub"], limit=limit),
        user_id=str(current_user["sub"]),
        metadata={"db": db},
    )
