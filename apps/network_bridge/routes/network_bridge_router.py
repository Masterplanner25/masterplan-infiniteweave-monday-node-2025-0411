# /routes/network_bridge_router.py
from fastapi import APIRouter, Depends, Request
import logging
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from AINDY.core.execution_gate import to_envelope
from AINDY.core.execution_helper import execute_with_pipeline_sync
from AINDY.db.database import get_db
from AINDY.platform_layer.rate_limiter import limiter
from datetime import datetime
import uuid
from AINDY.services.auth_service import verify_api_key

from apps.network_bridge.services import network_bridge_services
router = APIRouter(prefix="/network_bridge", tags=["Network Bridge"], dependencies=[Depends(verify_api_key)])
logger = logging.getLogger(__name__)


def _execute_network_bridge(request: Request, route_name: str, handler, *, db: Session):
    return execute_with_pipeline_sync(
        request=request,
        route_name=route_name,
        handler=handler,
        metadata={"db": db, "source": "network_bridge_router"},
    )


def _with_execution_envelope(payload):
    envelope = to_envelope(
        eu_id=None,
        trace_id=None,
        status="SUCCESS",
        output=None,
        error=None,
        duration_ms=None,
        attempt_count=1,
    )
    if hasattr(payload, "status_code") and hasattr(payload, "body"):
        return payload
    if isinstance(payload, dict):
        data = payload.get("data")
        result = dict(data) if isinstance(data, dict) else dict(payload)
        result.setdefault("execution_envelope", envelope)
        return result
    return {"data": payload, "execution_envelope": envelope}


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
@limiter.limit("30/minute")
async def connect_external_author(
    request: Request,
    handshake: NetworkHandshake,
    db: Session = Depends(get_db),
) -> dict:
    """
    Registers an external connection or author handshake and logs it to calculation_results.
    """
    def handler(_ctx):
        result = network_bridge_services.connect_external_author(
            db,
            author_name=handshake.author_name,
            platform=handshake.platform,
            connection_type=handshake.connection_type,
            notes=handshake.notes,
        )
        logger.info("Bridge connect: %s via %s", handshake.author_name, handshake.platform)
        return result

    return _with_execution_envelope(
        _execute_network_bridge(request, "network_bridge.connect", handler, db=db)
    )

@router.post("/user_event")
@limiter.limit("30/minute")
def log_user_event(request: Request, event: NetworkUser, db: Session = Depends(get_db)):
    """
    Called from the Node server whenever a new user joins or updates their profile.
    Logs the event into A.I.N.D.Y.'s metrics system (calculation_results table).
    """
    def handler(_ctx):
        from apps.analytics.public import save_calculation

        metric_name = f"UserEvent::{event.platform}"
        result = save_calculation(db, metric_name, 1.0)
        logger.info("Bridge user event: %s via %s", event.name, event.platform)
        return {
            "status": "logged",
            "user": event.name,
            "tagline": event.tagline,
            "record_id": result.id if result else str(uuid.uuid4()),
        }

    return _with_execution_envelope(
        _execute_network_bridge(request, "network_bridge.user_event", handler, db=db)
    )


@router.get("/authors")
@limiter.limit("60/minute")
def list_authors(
    request: Request,
    platform: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    """
    Return persisted external authors for gateway state reads.
    """
    authors = network_bridge_services.list_authors(db=db, platform=platform, limit=limit)
    def handler(_ctx):
        return {"authors": authors, "count": len(authors), "platform": platform}
    return _execute_network_bridge(request, "network_bridge.authors.list", handler, db=db)

