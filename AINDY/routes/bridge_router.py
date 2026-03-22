# /routes/bridge_router.py
from __future__ import annotations
import os
import time
import logging
import time
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from services.memory_capture_engine import MemoryCaptureEngine
from services.memory_persistence import MemoryNodeDAO
from config import settings
from services import rippletrace_services
from services.auth_service import get_current_user, verify_api_key
from db.models.bridge_user_event import BridgeUserEvent

logger = logging.getLogger(__name__)
# --- Environment / Config -------------------------------------------------
if not settings.DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not configured in .env or Settings.")

# ✅ Use centralized configuration
from db.database import get_db


# --- Permission Models ----------------------------------------------------
class TracePermission(BaseModel):
    nonce: str
    ts: int
    ttl: int
    scopes: List[str] = Field(default_factory=list)
    signature: str


# --- Node + Link Models ---------------------------------------------------
class NodeCreateRequest(BaseModel):
    content: str
    source: Optional[str] = None
    tags: Optional[List[str]] = Field(default_factory=list)
    node_type: Optional[str] = None
    extra: Optional[dict] = Field(default_factory=dict)
    user_id: Optional[str] = None
    source_agent: Optional[str] = None
    permission: Optional[TracePermission] = None


class NodeResponse(BaseModel):
    id: str
    content: str
    tags: List[str]
    node_type: Optional[str]
    extra: dict


class NodeSearchResponse(BaseModel):
    nodes: List[NodeResponse]


class LinkCreateRequest(BaseModel):
    source_id: str
    target_id: str
    link_type: Optional[str] = "related"
    permission: Optional[TracePermission] = None


class LinkResponse(BaseModel):
    id: str
    source_node_id: str
    target_node_id: str
    link_type: str
    strength: str
    created_at: Optional[str]


# --- Router Setup ---------------------------------------------------------
router = APIRouter(prefix="/bridge", tags=["Bridge"])

@router.post("/nodes", response_model=NodeResponse, status_code=status.HTTP_201_CREATED)
def create_node(payload: NodeCreateRequest, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    start = time.perf_counter()
    engine = MemoryCaptureEngine(
        db=db,
        user_id=str(current_user["sub"]),
        agent_namespace=payload.source_agent or "user",
    )
    saved = engine.evaluate_and_capture(
        event_type="task_completed",
        content=payload.content,
        source=payload.source or "bridge",
        tags=payload.tags,
        node_type=payload.node_type,
        context=payload.extra,
        extra=payload.extra,
        force=True,
    )
    if not saved:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "bridge_node_create_failed", "message": "Failed to create memory node"},
        )

    # 🔁 Emit RippleTrace event
    rippletrace_services.log_ripple_event(db, {
        "drop_point_id": "bridge",
        "ping_type": "node_creation",
        "source_platform": "AINDY",
        "summary": f"Node created: {(saved.get('content') or '')[:50]}",
    })
    duration_ms = (time.perf_counter() - start) * 1000
    logger.info("Bridge node created in %.2fms", duration_ms)

    return NodeResponse(
        id=str(saved.get("id")),
        content=saved.get("content"),
        tags=saved.get("tags", []),
        node_type=saved.get("node_type"),
        extra=saved.get("extra") or {},
    )


@router.get("/nodes", response_model=NodeSearchResponse)
def search_nodes(tag: Optional[List[str]] = None, mode: Optional[str] = "OR", limit: int = 100, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    dao = MemoryNodeDAO(db)
    nodes = dao.find_by_tags(tag or [], limit=limit, mode=mode, user_id=str(current_user["sub"]))
    result = [NodeResponse(**{
        "id": str(getattr(n, "id", n.get("id"))),
        "content": getattr(n, "content", n.get("content", "")),
        "tags": getattr(n, "tags", n.get("tags", [])),
        "node_type": getattr(n, "node_type", n.get("node_type")),
        "extra": getattr(n, "extra", n.get("extra", {})) or {},
    }) for n in nodes]
    return NodeSearchResponse(nodes=result)


@router.post("/link", response_model=LinkResponse, status_code=status.HTTP_201_CREATED)
def create_link(payload: LinkCreateRequest, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    start = time.perf_counter()
    dao = MemoryNodeDAO(db)
    source = dao.load_memory_node(payload.source_id)
    target = dao.load_memory_node(payload.target_id)
    if not source or not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "bridge_link_nodes_not_found", "message": "Source or target node not found"},
        )
    if source.get("user_id") != str(current_user["sub"]) or target.get("user_id") != str(current_user["sub"]):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "bridge_link_forbidden", "message": "Cannot link nodes you do not own"},
        )
    link = dao.create_link(payload.source_id, payload.target_id, link_type=payload.link_type)
    duration_ms = (time.perf_counter() - start) * 1000
    logger.info("Bridge link created in %.2fms", duration_ms)
    return LinkResponse(
        id=link["id"],
        source_node_id=link["source_node_id"],
        target_node_id=link["target_node_id"],
        link_type=link["link_type"],
        strength=link["strength"],
        created_at=str(link["created_at"]) if link.get("created_at") else None,
    )


# --- NEW: /bridge/user_event Endpoint ------------------------------------
class UserEvent(BaseModel):
    user: str
    origin: str
    timestamp: Optional[str] = None


def _parse_event_timestamp(raw_timestamp: Optional[str]) -> Optional[datetime]:
    if not raw_timestamp:
        return None
    try:
        cleaned = raw_timestamp.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(cleaned)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        return None


@router.post("/user_event")
def bridge_user_event(event: UserEvent, _key: str = Depends(verify_api_key), db: Session = Depends(get_db)):
    """Accept symbolic user join or runtime events."""
    start = time.perf_counter()
    timestamp = event.timestamp or time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
    occurred_at = _parse_event_timestamp(event.timestamp) or datetime.now(timezone.utc)
    try:
        db.add(BridgeUserEvent(
            user_name=event.user,
            origin=event.origin,
            raw_timestamp=event.timestamp,
            occurred_at=occurred_at,
        ))
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.warning("Failed to persist bridge user event: %s", exc)
    duration_ms = (time.perf_counter() - start) * 1000
    logger.info(
        "Bridge user event: user=%s origin=%s timestamp=%s duration_ms=%.2f",
        event.user,
        event.origin,
        timestamp,
        duration_ms,
    )
    return {"status": "logged", "user": event.user, "origin": event.origin, "timestamp": timestamp}
