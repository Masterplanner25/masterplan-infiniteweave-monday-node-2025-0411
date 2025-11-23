# /routes/bridge_router.py
from __future__ import annotations
import os
import hmac
import hashlib
import time
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from services.memory_persistence import MemoryNodeDAO
from config import settings
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from services import rippletrace_services

# --- Environment / Config -------------------------------------------------
if not settings.DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not configured in .env or Settings.")
PERMISSION_SECRET = os.getenv("PERMISSION_SECRET", "dev-secret-must-change")

# ✅ Use centralized configuration
DATABASE_URL = settings.DATABASE_URL
_engine = create_engine(DATABASE_URL, future=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)

def get_db():
    db: Session = _SessionLocal()
    try:
        yield db
    finally:
        db.close()


# --- Permission Models ----------------------------------------------------
class TracePermission(BaseModel):
    nonce: str
    ts: int
    ttl: int
    scopes: List[str] = Field(default_factory=list)
    signature: str


def compute_perm_sig(nonce: str, ts: int, ttl: int, scopes: List[str]) -> str:
    payload = f"{nonce}|{ts}|{ttl}|{','.join(sorted(scopes))}"
    return hmac.new(PERMISSION_SECRET.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_permission_or_403(permission: TracePermission):
    expected = compute_perm_sig(permission.nonce, permission.ts, permission.ttl, permission.scopes)
    if not hmac.compare_digest(expected, permission.signature):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid permission signature")
    now = int(time.time())
    if permission.ts + permission.ttl < now:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission expired")
    return permission


# --- Node + Link Models ---------------------------------------------------
class NodeCreateRequest(BaseModel):
    content: str
    tags: Optional[List[str]] = Field(default_factory=list)
    node_type: Optional[str] = "generic"
    extra: Optional[dict] = Field(default_factory=dict)
    permission: TracePermission


class NodeResponse(BaseModel):
    id: str
    content: str
    tags: List[str]
    node_type: str
    extra: dict


class NodeSearchResponse(BaseModel):
    nodes: List[NodeResponse]


class LinkCreateRequest(BaseModel):
    source_id: str
    target_id: str
    link_type: Optional[str] = "related"
    permission: TracePermission


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
def create_node(payload: NodeCreateRequest, db: Session = Depends(get_db)):
    verify_permission_or_403(payload.permission)
    dao = MemoryNodeDAO(db)

    class _NodeLike:
        def __init__(self, content, tags, node_type, extra):
            self.id = None
            self.content = content
            self.tags = tags or []
            self.node_type = node_type or "generic"
            self.extra = extra or {}

    saved = dao.save_memory_node(_NodeLike(payload.content, payload.tags, payload.node_type, payload.extra))

    # 🔁 Emit RippleTrace event
    rippletrace_services.log_ripple_event(db, {
        "drop_point_id": "bridge",
        "ping_type": "node_creation",
        "source_platform": "AINDY",
        "summary": f"Node created: {saved.content[:50]}",
    })

    return NodeResponse(
        id=str(saved.id),
        content=saved.content,
        tags=saved.tags,
        node_type=saved.node_type,
        extra=saved.extra or {},
    )


@router.get("/nodes", response_model=NodeSearchResponse)
def search_nodes(tag: Optional[List[str]] = None, mode: Optional[str] = "OR", limit: int = 100, db: Session = Depends(get_db)):
    dao = MemoryNodeDAO(db)
    nodes = dao.find_by_tags(tag or [], limit=limit, mode=mode)
    result = [NodeResponse(**{
        "id": str(getattr(n, "id", n.get("id"))),
        "content": getattr(n, "content", n.get("content", "")),
        "tags": getattr(n, "tags", n.get("tags", [])),
        "node_type": getattr(n, "node_type", n.get("node_type", "generic")),
        "extra": getattr(n, "extra", n.get("extra", {})) or {},
    }) for n in nodes]
    return NodeSearchResponse(nodes=result)


@router.post("/link", response_model=LinkResponse, status_code=status.HTTP_201_CREATED)
def create_link(payload: LinkCreateRequest, db: Session = Depends(get_db)):
    verify_permission_or_403(payload.permission)
    dao = MemoryNodeDAO(db)
    link = dao.create_link(payload.source_id, payload.target_id, link_type=payload.link_type)
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


@router.post("/user_event")
def bridge_user_event(event: UserEvent):
    """Accept symbolic user join or runtime events."""
    timestamp = event.timestamp or time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
    print(f"🔗 {event.user} joined from {event.origin} at {timestamp}")
    return {"status": "logged", "user": event.user, "origin": event.origin, "timestamp": timestamp}
