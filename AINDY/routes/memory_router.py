from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel

from db.database import get_db
from db.dao.memory_node_dao import MemoryNodeDAO
from services.auth_service import get_current_user

router = APIRouter(prefix="/memory", tags=["Memory"])


# ------------------------------------------------------------------
# Request schemas
# ------------------------------------------------------------------

class CreateNodeRequest(BaseModel):
    content: str
    source: Optional[str] = None
    tags: Optional[List[str]] = []
    node_type: Optional[str] = "generic"
    extra: Optional[dict] = {}


class CreateLinkRequest(BaseModel):
    source_id: str
    target_id: str
    link_type: Optional[str] = "related"


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------

@router.post("/nodes", status_code=201)
def create_node(
    body: CreateNodeRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Create and persist a new memory node owned by the current user."""
    user_id = str(current_user["sub"])
    dao = MemoryNodeDAO(db)
    return dao.save(
        content=body.content,
        source=body.source,
        tags=body.tags,
        user_id=user_id,
        node_type=body.node_type,
        extra=body.extra,
    )


@router.get("/nodes/{node_id}")
def get_node(
    node_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Retrieve a memory node by UUID."""
    dao = MemoryNodeDAO(db)
    node = dao.get_by_id(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Memory node not found")
    return node


@router.get("/nodes/{node_id}/links")
def get_linked_nodes(
    node_id: str,
    direction: str = "both",
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Return all nodes linked to the given node.
    direction: 'in' | 'out' | 'both' (default)
    """
    if direction not in ("in", "out", "both"):
        raise HTTPException(status_code=422, detail="direction must be 'in', 'out', or 'both'")
    dao = MemoryNodeDAO(db)
    # Verify node exists first
    if not dao.get_by_id(node_id):
        raise HTTPException(status_code=404, detail="Memory node not found")
    return {"nodes": dao.get_linked_nodes(node_id, direction=direction)}


@router.get("/nodes")
def search_nodes_by_tags(
    tags: str = "",
    mode: str = "AND",
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Search memory nodes by comma-separated tags.
    mode: 'AND' (all tags required, default) | 'OR' (any tag matches)
    limit: max results (default 50)
    """
    if mode.upper() not in ("AND", "OR"):
        raise HTTPException(status_code=422, detail="mode must be 'AND' or 'OR'")
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    dao = MemoryNodeDAO(db)
    return {"nodes": dao.get_by_tags(tag_list, limit=limit, mode=mode)}


@router.post("/links", status_code=201)
def create_link(
    body: CreateLinkRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Create a directed relationship between two existing memory nodes."""
    dao = MemoryNodeDAO(db)
    try:
        return dao.create_link(body.source_id, body.target_id, body.link_type)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
