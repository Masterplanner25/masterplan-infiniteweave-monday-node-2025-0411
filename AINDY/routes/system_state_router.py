from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from AINDY.core.execution_service import ExecutionContext
from AINDY.core.execution_service import run_execution
from AINDY.db.database import get_db
from AINDY.platform_layer.rate_limiter import limiter
from AINDY.services.auth_service import get_current_user
from AINDY.platform_layer.system_state_service import compute_current_state
from AINDY.platform_layer.system_state_service import get_latest_snapshot


router = APIRouter(prefix="/system", tags=["System State"])


@router.get("/state")
@limiter.limit("60/minute")
def get_system_state(
    request: Request,
    force_refresh: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return run_execution(
        ExecutionContext(
            db=db,
            user_id=str(current_user["sub"]),
            source="system_state",
            operation="system.state.get",
            start_payload={"force_refresh": force_refresh},
        ),
        lambda: {
            "current": compute_current_state(db, force_refresh=force_refresh, persist_snapshot=True),
            "latest_persisted": get_latest_snapshot(db),
        },
    )

