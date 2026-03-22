from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db.dao.memory_node_dao import MemoryNodeDAO
from db.dao.memory_trace_dao import MemoryTraceDAO
from db.database import get_db
from services.auth_service import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/memory", tags=["Memory"])


class CreateTraceRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    source: Optional[str] = None
    extra: Optional[dict] = None


class AppendTraceRequest(BaseModel):
    node_id: str
    position: Optional[int] = None


@router.post("/traces", status_code=201)
def create_trace(
    body: CreateTraceRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    dao = MemoryTraceDAO(db)
    trace = dao.create_trace(
        user_id=str(current_user["sub"]),
        title=body.title,
        description=body.description,
        source=body.source,
        extra=body.extra,
    )
    return trace


@router.get("/traces")
def list_traces(
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    dao = MemoryTraceDAO(db)
    traces = dao.list_traces(user_id=str(current_user["sub"]), limit=limit)
    return {"traces": traces, "count": len(traces)}


@router.get("/traces/{trace_id}")
def get_trace(
    trace_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    dao = MemoryTraceDAO(db)
    trace = dao.get_trace(trace_id, user_id=str(current_user["sub"]))
    if not trace:
        raise HTTPException(
            status_code=404,
            detail={"error": "trace_not_found", "message": "Trace not found"},
        )
    return trace


@router.get("/traces/{trace_id}/nodes")
def get_trace_nodes(
    trace_id: str,
    limit: int = 200,
    include_nodes: bool = False,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    dao = MemoryTraceDAO(db)
    nodes = dao.get_trace_nodes(
        trace_id,
        user_id=str(current_user["sub"]),
        limit=limit,
    )
    if not nodes:
        return {"trace_id": trace_id, "nodes": [], "count": 0}

    if include_nodes:
        memory_dao = MemoryNodeDAO(db)
        hydrated = []
        for entry in nodes:
            node = memory_dao.get_by_id(entry["node_id"], user_id=str(current_user["sub"]))
            hydrated.append({
                **entry,
                "node": node,
            })
        nodes = hydrated

    return {"trace_id": trace_id, "nodes": nodes, "count": len(nodes)}


@router.post("/traces/{trace_id}/append", status_code=201)
def append_trace_node(
    trace_id: str,
    body: AppendTraceRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    memory_dao = MemoryNodeDAO(db)
    node = memory_dao.get_by_id(body.node_id, user_id=str(current_user["sub"]))
    if not node:
        raise HTTPException(
            status_code=404,
            detail={"error": "memory_node_not_found", "message": "Memory node not found"},
        )

    dao = MemoryTraceDAO(db)
    appended = dao.append_node(
        trace_id=trace_id,
        node_id=body.node_id,
        user_id=str(current_user["sub"]),
        position=body.position,
    )
    if not appended:
        raise HTTPException(
            status_code=404,
            detail={"error": "trace_not_found", "message": "Trace not found"},
        )
    return appended
