# /routers/rippletrace_router.py
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from db.config import get_db
from services import rippletrace_services

router = APIRouter(prefix="/rippletrace", tags=["RippleTrace"])

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


# === ROUTES ===
@router.post("/drop_point")
def create_drop_point(dp: DropPoint, db: Session = Depends(get_db)):
    return rippletrace_services.add_drop_point(db, dp)

@router.post("/ping")
def create_ping(pg: Ping, db: Session = Depends(get_db)):
    return rippletrace_services.add_ping(db, pg)

@router.get("/ripples/{drop_point_id}")
def get_ripples(drop_point_id: str, db: Session = Depends(get_db)):
    return rippletrace_services.get_ripples(db, drop_point_id)

@router.get("/drop_points")
def all_drop_points(db: Session = Depends(get_db)):
    return rippletrace_services.get_all_drop_points(db)

@router.get("/pings")
def all_pings(db: Session = Depends(get_db)):
    return rippletrace_services.get_all_pings(db)
