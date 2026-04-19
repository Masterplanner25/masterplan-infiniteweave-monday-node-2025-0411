from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from AINDY.core.execution_helper import execute_with_pipeline_sync
from AINDY.db.database import get_db
from AINDY.platform_layer.rate_limiter import limiter
from AINDY.services.auth_service import get_current_user

router = APIRouter(prefix="/autonomy", tags=["Autonomy"])


def _run_flow_autonomy(flow_name: str, payload: dict, db: Session, user_id: str):
    from AINDY.runtime.flow_engine import run_flow
    result = run_flow(flow_name, payload, db=db, user_id=user_id)
    if result.get("status") == "FAILED":
        error = result.get("error", "")
        if error.startswith("HTTP_"):
            parts = error.split(":", 1)
            code = int(parts[0].replace("HTTP_", ""))
            msg = parts[1] if len(parts) > 1 else error
            raise HTTPException(status_code=code, detail=msg)
        raise HTTPException(status_code=500, detail=error or f"{flow_name} failed")
    return result.get("data")


@router.get("/decisions")
@limiter.limit("60/minute")
def get_recent_autonomy_decisions(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])
    return execute_with_pipeline_sync(
        request=None,
        route_name="autonomy.decisions.list",
        handler=lambda ctx: _run_flow_autonomy("autonomy_decisions_list", {"limit": limit}, db, user_id),
        user_id=user_id,
        metadata={"db": db},
    )

