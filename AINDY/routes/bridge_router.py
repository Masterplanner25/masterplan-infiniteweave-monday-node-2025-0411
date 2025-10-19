# bridge_router.py
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

# --- DB session dependency ---------------------------------------------------
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg2://postgres:140671aA%40@localhost:5433/base")
_engine = create_engine(DATABASE_URL, future=True)
_SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False)

def get_db():
    db: Session = _SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- Permission model & verification (HMAC) --------------------------------
# Lightweight TracePermission model
class TracePermission(BaseModel):
    nonce: str
    ts: int  # epoch seconds
    ttl: int  # seconds
    scopes: List[str] = Field(default_factory=list)
    signature: str  # hex HMAC signature computed over "nonce|ts|ttl|','.join(sorted(scopes))"

# Secret to sign/verify permission tokens. Set in env var in production.
PERMISSION_SECRET = os.getenv("PERMISSION_SECRET", "dev-secret-must-change")

def compute_perm_sig(nonce: str, ts: int, ttl: int, scopes: List[str]) -> str:
    payload = f"{nonce}|{ts}|{ttl}|{','.join(sorted(scopes))}"
    sig = hmac.new(PERMISSION_SECRET.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return sig

def verify_permission_or_403(permission: TracePermission):
    # Basic validation: signature & expiry & simple TTL
    expected = compute_perm_sig(permission.nonce, permission.ts, permission.ttl, permission.scopes)
    if not hmac.compare_digest(expected, permission.signature):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid permission signature")
    now = int(time.time())
    if permission.ts + permission.ttl < now:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission expired")
    return permission

# --- Pydantic models for API -----------------------------------------------
class NodeCreateRequest(BaseModel):
    content: str
    tags: Optional[List[str]] = Field(default_factory=list)
    node_type: Optional[str] = "generic"
    extra: Optional[dict] = Field(default_factory=dict)
    permission: TracePermission  # require permission to create

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

# --- Router ---------------------------------------------------------------
router = APIRouter(prefix="/bridge", tags=["bridge"])

@router.post("/nodes", response_model=NodeResponse, status_code=status.HTTP_201_CREATED)
def create_node(payload: NodeCreateRequest, db: Session = Depends(get_db)):
    # verify permission (will raise 403 if invalid)
    verify_permission_or_403(payload.permission)

    dao = MemoryNodeDAO(db)
    # create a simple pseudo-object expected by the DAO
    class _NodeLike:
        def __init__(self, content, tags, node_type, extra):
            self.id = None
            self.content = content
            self.tags = tags or []
            self.node_type = node_type or "generic"
            self.extra = extra or {}

    saved = dao.save_memory_node(_NodeLike(payload.content, payload.tags, payload.node_type, payload.extra))
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
    tags = list(tag) if tag else []
    nodes = dao.find_by_tags(tags, limit=limit, mode=mode)
    # dao returns list of dict-like rows; normalize to NodeResponse
    result = []
    for n in nodes:
        if isinstance(n, dict):
            node = NodeResponse(
                id=n["id"],
                content=n.get("content", ""),
                tags=n.get("tags", []),
                node_type=n.get("node_type", "generic"),
                extra=n.get("extra", {}) or {},
            )
        else:
            node = NodeResponse(
                id=str(getattr(n, "id")),
                content=getattr(n, "content", ""),
                tags=getattr(n, "tags", []),
                node_type=getattr(n, "node_type", "generic"),
                extra=getattr(n, "extra", {}) or {},
            )
        result.append(node)
    return NodeSearchResponse(nodes=result)

@router.post("/link", response_model=LinkResponse, status_code=status.HTTP_201_CREATED)
def create_link(payload: LinkCreateRequest, db: Session = Depends(get_db)):
    # verify permission
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
