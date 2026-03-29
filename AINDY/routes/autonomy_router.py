from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from db.database import get_db
from services.auth_service import get_current_user
from services.autonomous_controller import list_recent_decisions
from services.execution_envelope import success
from utils.trace_context import ensure_trace_id


router = APIRouter(prefix="/autonomy", tags=["Autonomy"])


@router.get("/decisions")
def get_recent_autonomy_decisions(
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return success(
        list_recent_decisions(db, user_id=current_user["sub"], limit=limit),
        [],
        ensure_trace_id(),
    )
