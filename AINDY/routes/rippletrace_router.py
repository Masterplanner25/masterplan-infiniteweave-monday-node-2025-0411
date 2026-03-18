# /routers/rippletrace_router.py
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from db.database import get_db
from services import rippletrace_services
from services.auth_service import get_current_user

router = APIRouter(prefix="/rippletrace", tags=["RippleTrace"], dependencies=[Depends(get_current_user)])

# === Pydantic Schemas ===
class DropPoint(BaseModel):
    id: str
    title: str
    platform: str
    url: Optional[str] = None
    date_dropped: Optional[datetime] = None
    core_themes: List[str]
    tagged_entities: List[str]
    intent: str

class Ping(BaseModel):
    id: str
    drop_point_id: str
    ping_type: str
    source_platform: str
    date_detected: Optional[datetime] = None
    connection_summary: Optional[str] = None
    external_url: Optional[str] = None
    reaction_notes: Optional[str] = None

class RippleEvent(BaseModel):
    ping_type: str
    source_platform: Optional[str] = "AINDY"
    summary: Optional[str] = None
    url: Optional[str] = None
    notes: Optional[str] = None
    drop_point_id: Optional[str] = "bridge"


# === ROUTES ===
@router.post("/drop_point")
def create_drop_point(
    dp: DropPoint,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return rippletrace_services.add_drop_point(db, dp, user_id=str(current_user["sub"]))

@router.post("/ping")
def create_ping(
    pg: Ping,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return rippletrace_services.add_ping(db, pg, user_id=str(current_user["sub"]))

@router.get("/ripples/{drop_point_id}")
def get_ripples(
    drop_point_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return rippletrace_services.get_ripples(
        db, drop_point_id, user_id=str(current_user["sub"])
    )

@router.get("/drop_points")
def all_drop_points(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return rippletrace_services.get_all_drop_points(db, user_id=str(current_user["sub"]))

@router.get("/pings")
def all_pings(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return rippletrace_services.get_all_pings(db, user_id=str(current_user["sub"]))

@router.get("/recent")
def recent_ripples(
    limit: int = 10,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Fetch the most recent ripple or ping events for visualization.
    """
    return rippletrace_services.get_recent_ripples(
        db, limit, user_id=str(current_user["sub"])
    )

@router.post("/event")
async def log_ripple_event(
    event: RippleEvent,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Log a symbolic ripple event triggered by the Bridge or other ecosystem nodes."""
    rippletrace_services.log_ripple_event(
        db, event.model_dump(), user_id=str(current_user["sub"])
    )
    return {"status": "logged", "event": event.model_dump()}
