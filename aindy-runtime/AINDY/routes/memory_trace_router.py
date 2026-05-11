import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from AINDY.core.execution_helper import execute_with_pipeline_sync
from AINDY.db.dao.memory_node_dao import MemoryNodeDAO
from AINDY.db.dao.memory_trace_dao import MemoryTraceDAO
from AINDY.db.database import get_db
from AINDY.platform_layer.rate_limiter import limiter
from AINDY.services.auth_service import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/memory", tags=["Memory"])


def _execute_memory_trace(request: Request, route_name: str, handler, *, db: Session, user_id: str, success_status_code: int = 200):
    return execute_with_pipeline_sync(
        request=request,
        route_name=route_name,
        handler=handler,
        user_id=user_id,
        metadata={"db": db, "source": "memory_trace_router"},
        success_status_code=success_status_code,
    )


class CreateTraceRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    source: Optional[str] = None
    extra: Optional[dict] = None


class AppendTraceRequest(BaseModel):
    node_id: str
    position: Optional[int] = None


@router.post("/traces", status_code=201)
@limiter.limit("30/minute")
def create_trace(
    request: Request,
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
    def handler(_ctx):
        return trace
    return _execute_memory_trace(request, "memory.traces.create", handler, db=db, user_id=str(current_user["sub"]), success_status_code=201)


@router.get("/traces")
@limiter.limit("60/minute")
def list_traces(
    request: Request,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    dao = MemoryTraceDAO(db)
    traces = dao.list_traces(user_id=str(current_user["sub"]), limit=limit)
    def handler(_ctx):
        return {"traces": traces, "count": len(traces)}
    return _execute_memory_trace(request, "memory.traces.list", handler, db=db, user_id=str(current_user["sub"]))


@router.get("/traces/{trace_id}")
@limiter.limit("60/minute")
def get_trace(
    request: Request,
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
    def handler(_ctx):
        return trace
    return _execute_memory_trace(request, "memory.traces.get", handler, db=db, user_id=str(current_user["sub"]))


@router.get("/traces/{trace_id}/nodes")
@limiter.limit("60/minute")
def get_trace_nodes(
    request: Request,
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
        def empty_handler(_ctx):
            return {"trace_id": trace_id, "nodes": [], "count": 0}
        return _execute_memory_trace(request, "memory.traces.nodes", empty_handler, db=db, user_id=str(current_user["sub"]))

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

    def handler(_ctx):
        return {"trace_id": trace_id, "nodes": nodes, "count": len(nodes)}
    return _execute_memory_trace(request, "memory.traces.nodes", handler, db=db, user_id=str(current_user["sub"]))


@router.post("/traces/{trace_id}/append", status_code=201)
@limiter.limit("30/minute")
def append_trace_node(
    request: Request,
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
    def handler(_ctx):
        return appended
    return _execute_memory_trace(request, "memory.traces.append", handler, db=db, user_id=str(current_user["sub"]), success_status_code=201)
