# /routes/dashboard_router.py
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from core.execution_helper import execute_with_pipeline_sync
from db.database import get_db
from services.auth_service import get_current_user

router = APIRouter(prefix="/dashboard", tags=["Dashboard Overview"], dependencies=[Depends(get_current_user)])


def _run_flow_dashboard(flow_name: str, payload: dict, db: Session, user_id: str):
    from services.flow_engine import run_flow
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


def _execute_dashboard(request: Request, route_name: str, handler, *, db: Session, user_id: str):
    return execute_with_pipeline_sync(
        request=request,
        route_name=route_name,
        handler=handler,
        user_id=user_id,
        metadata={"db": db, "source": "dashboard_router"},
    )


@router.get("/overview")
def get_system_overview(
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> dict:
    """
    Returns a snapshot of A.I.N.D.Y.'s current awareness:
    - Total connected authors
    - Recent ripple events
    - System heartbeat timestamp
    """
    user_id = str(current_user["sub"])
    def handler(_ctx):
        return _run_flow_dashboard("dashboard_overview", {}, db, user_id)
    return _execute_dashboard(request, "dashboard.overview", handler, db=db, user_id=user_id)
