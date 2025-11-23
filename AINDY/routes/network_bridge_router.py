# /routes/network_bridge_router.py
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from db.database import get_db
from datetime import datetime
import uuid
from services.calculation_services import save_calculation

# Internal service imports
from services import rippletrace_services, network_bridge_services

router = APIRouter(prefix="/network_bridge", tags=["Network Bridge"])


# ---------------------------------------------------------------------------
# MODELS
# ---------------------------------------------------------------------------
class NetworkHandshake(BaseModel):
    author_name: str = Field(..., description="Name of the external node or author")
    platform: str = Field(..., description="Source platform (e.g., InfiniteNetwork, SYLVA)")
    connection_type: str = Field(default="BridgeHandshake")
    notes: str | None = Field(default=None, description="Optional notes or context")

class NetworkUser(BaseModel):
    name: str
    tagline: str
    platform: str = "InfiniteNetwork"
    action: str = "create_profile"


# ---------------------------------------------------------------------------
# ROUTES
# ---------------------------------------------------------------------------
@router.post("/connect")
async def connect_external_author(
    handshake: NetworkHandshake,
    db: Session = Depends(get_db),
) -> dict:
    """
    Registers an external connection or author handshake and logs it to calculation_results.
    """

    author = network_bridge_services.register_author(
        db=db,
        name=handshake.author_name,
        platform=handshake.platform,
        notes=handshake.notes,
    )

    ripple_event = {
        "ping_type": handshake.connection_type,
        "source_platform": handshake.platform,
        "summary": f"{handshake.author_name} connected via {handshake.platform}",
        "notes": handshake.notes or "",
        "drop_point_id": "bridge",
    }
    rippletrace_services.log_ripple_event(db, ripple_event)

    # Save metric — now safely committed once at the end
    metric_name = f"UserEvent::{handshake.platform}"
    save_calculation(db, metric_name, 1)

    print(f"🔗 {handshake.author_name} connected via {handshake.platform} at {datetime.utcnow()}")
    print(f"🧩 Logged metric from router: {metric_name}")
    db.commit()  # Final commit after all other services

    return {
        "status": "connected",
        "author_id": author.id,
        "platform": handshake.platform,
        "timestamp": datetime.utcnow().isoformat(),
    }

@router.post("/user_event")
def log_user_event(event: NetworkUser, db: Session = Depends(get_db)):
    """
    Called from the Node server whenever a new user joins or updates their profile.
    Logs the event into A.I.N.D.Y.'s metrics system (calculation_results table).
    """
    metric_name = f"UserEvent::{event.platform}"
    value = 1.0

    result = save_calculation(db, metric_name, value)

    print(f"🔗 {event.name} joined from {event.platform} at {datetime.utcnow()}")

    return {
        "status": "logged",
        "user": event.name,
        "tagline": event.tagline,
        "record_id": result.id if result else str(uuid.uuid4())
    }
