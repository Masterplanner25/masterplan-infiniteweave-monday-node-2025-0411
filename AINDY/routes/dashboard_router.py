# /routes/dashboard_router.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import datetime

from db.database import get_db
from db.models.author_model import AuthorDB
from db.models import PingDB  # from your existing rippletrace models

router = APIRouter(prefix="/dashboard", tags=["Dashboard Overview"])


@router.get("/overview")
async def get_system_overview(db: Session = Depends(get_db)) -> dict:
    """
    Returns a snapshot of A.I.N.D.Y.'s current awareness:
    - Total connected authors
    - Recent ripple events
    - System heartbeat timestamp
    """
    # 🧠 1. Authors summary
    authors = db.query(AuthorDB).order_by(AuthorDB.joined_at.desc()).limit(10).all()
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
    ripples = db.query(PingDB).order_by(PingDB.date_detected.desc()).limit(10).all()
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

    return {"status": "ok", "overview": overview}
