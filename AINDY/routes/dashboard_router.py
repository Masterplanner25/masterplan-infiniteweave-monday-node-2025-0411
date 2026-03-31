# /routes/dashboard_router.py
import uuid
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from datetime import datetime

from core.execution_helper import execute_with_pipeline_sync
from db.database import get_db
from db.models.author_model import AuthorDB
from db.models import PingDB  # from your existing rippletrace models
from services.auth_service import get_current_user

router = APIRouter(prefix="/dashboard", tags=["Dashboard Overview"], dependencies=[Depends(get_current_user)])


def _execute_dashboard(request: Request, route_name: str, handler, *, db: Session, user_id: str):
    return execute_with_pipeline_sync(
        request=request,
        route_name=route_name,
        handler=handler,
        user_id=user_id,
        metadata={"db": db, "source": "dashboard_router"},
    )


@router.get("/overview")
async def get_system_overview(
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
    # 🧠 1. Authors summary
    authors = db.query(AuthorDB).filter(
        AuthorDB.user_id == uuid.UUID(str(current_user["sub"]))
    ).order_by(AuthorDB.joined_at.desc()).limit(10).all()
    author_list = [
        {
            "id": a.id,
            "name": a.name,
            "platform": a.platform,
            "last_seen": a.last_seen.isoformat() if a.last_seen else None,
            "notes": a.notes,
        }
        for a in authors
    ]

    # 🌊 2. RippleTrace summary
    ripples = db.query(PingDB).filter(
        PingDB.user_id == uuid.UUID(str(current_user["sub"]))
    ).order_by(PingDB.date_detected.desc()).limit(10).all()
    ripple_list = [
        {
            "ping_type": r.ping_type,
            "source_platform": r.source_platform,
            "summary": r.connection_summary,
            "date_detected": r.date_detected.isoformat() if r.date_detected else None,
        }
        for r in ripples
    ]

    # 🕒 3. Combine snapshot
    overview = {
        "system_timestamp": datetime.utcnow().isoformat(),
        "author_count": len(author_list),
        "recent_authors": author_list,
        "recent_ripples": ripple_list,
    }

    def handler(_ctx):
        return {"status": "ok", "overview": overview}
    return _execute_dashboard(request, "dashboard.overview", handler, db=db, user_id=str(current_user["sub"]))
