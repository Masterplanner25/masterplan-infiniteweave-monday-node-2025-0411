from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from db.database import get_db
from services.auth_service import get_current_user
from services.system_state_service import compute_current_state
from services.system_state_service import get_latest_snapshot


router = APIRouter(prefix="/system", tags=["System State"])


@router.get("/state")
def get_system_state(
    force_refresh: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    snapshot = compute_current_state(db, force_refresh=force_refresh, persist_snapshot=True)
    return {
        "current": snapshot,
        "latest_persisted": get_latest_snapshot(db),
    }
