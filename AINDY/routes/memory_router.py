from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Literal, Optional
from pydantic import BaseModel

from db.database import get_db
from db.dao.memory_node_dao import MemoryNodeDAO
from services.auth_service import get_current_user

router = APIRouter(prefix="/memory", tags=["Memory"])

NodeType = Literal["decision", "outcome", "insight", "relationship"]


# ------------------------------------------------------------------
# Request schemas
# ------------------------------------------------------------------

class CreateNodeRequest(BaseModel):
    content: str
    source: Optional[str] = None
    tags: Optional[List[str]] = []
    node_type: Optional[NodeType] = None
    extra: Optional[dict] = {}


class SimilaritySearchRequest(BaseModel):
    query: str
    limit: Optional[int] = 5
    node_type: Optional[NodeType] = None
    min_similarity: Optional[float] = 0.0


class RecallRequest(BaseModel):
    query: Optional[str] = None
    tags: Optional[List[str]] = None
    limit: Optional[int] = 5
    node_type: Optional[NodeType] = None


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
    """Retrieve a memory node by UUID owned by the current user."""
    dao = MemoryNodeDAO(db)
    node = dao.get_by_id(node_id)
    if not node or node.get("user_id") != str(current_user["sub"]):
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


@router.post("/nodes/search")
def search_similar_nodes(
    body: SimilaritySearchRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Semantic similarity search via pgvector."""
    from services.embedding_service import generate_query_embedding
    query_embedding = generate_query_embedding(body.query)
    dao = MemoryNodeDAO(db)
    results = dao.find_similar(
        query_embedding=query_embedding,
        limit=body.limit,
        user_id=str(current_user["sub"]),
        node_type=body.node_type,
        min_similarity=body.min_similarity,
    )
    return {
        "query": body.query,
        "results": results,
        "count": len(results),
    }


@router.post("/recall")
def recall_memories(
    body: RecallRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Retrieve memories using resonance scoring.
    score = (semantic*0.6) + (tag*0.2) + (recency*0.2)
    Primary retrieval API for all Phase 3 hooks.
    """
    if not body.query and not body.tags:
        raise HTTPException(status_code=400, detail="Provide at least one of: query, tags")

    dao = MemoryNodeDAO(db)
    results = dao.recall(
        query=body.query,
        tags=body.tags,
        limit=body.limit,
        user_id=str(current_user["sub"]),
        node_type=body.node_type,
    )
    return {
        "query": body.query,
        "tags": body.tags,
        "results": results,
        "count": len(results),
        "scoring": {
            "semantic_weight": 0.6,
            "tag_weight": 0.2,
            "recency_weight": 0.2,
        },
    }
