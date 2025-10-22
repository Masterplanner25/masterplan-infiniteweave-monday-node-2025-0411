# /routers/network_bridge_router.py
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from db.config import get_db
from services.calculation_services import save_calculation
from datetime import datetime
import uuid

router = APIRouter(prefix="/bridge", tags=["Network Bridge"])

class NetworkUser(BaseModel):
    name: str
    tagline: str
    platform: str = "InfiniteNetwork"
    action: str = "create_profile"

@router.post("/user_event")
def log_user_event(event: NetworkUser, db: Session = Depends(get_db)):
    """
    Called from the Node server whenever a new user joins or updates their profile.
    Logs the event into A.I.N.D.Y.'s metrics system.
    """
    metric_name = f"UserEvent::{event.platform}"
    value = 1  # base unit — one user creation
    result = save_calculation(db, metric_name, value)

    # Optionally record in memory bridge
    print(f"🔗 {event.name} joined from {event.platform} at {datetime.utcnow()}")
    return {
        "status": "logged",
        "user": event.name,
        "tagline": event.tagline,
        "record_id": result.id if result else str(uuid.uuid4()),
    }
