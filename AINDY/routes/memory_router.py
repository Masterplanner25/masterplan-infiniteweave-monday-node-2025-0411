from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import List, Literal, Optional
from pydantic import BaseModel
import logging

from core.execution_helper import execute_with_pipeline
from db.database import get_db
from services.auth_service import get_current_user

router = APIRouter(prefix="/memory", tags=["Memory"])
logger = logging.getLogger(__name__)

NodeType = Literal["decision", "outcome", "insight", "relationship"]


def _flow_failure(result: dict) -> str:
    direct_error = result.get("error")
    if isinstance(direct_error, str) and direct_error:
        return direct_error
    for key in ("data", "result"):
        payload = result.get(key)
        if isinstance(payload, dict):
            nested_error = payload.get("error") or payload.get("message")
            if isinstance(nested_error, str) and nested_error:
                return nested_error
    return ""


def _mem_run_flow(flow_name: str, payload: dict, db, user_id: str):
    """Run a memory flow and decode node HTTP errors."""
    from runtime.flow_engine import run_flow
    result = run_flow(flow_name, payload, db=db, user_id=user_id)
    data = result.get("data")

    if isinstance(data, dict) and data.get("_http_status") == 202:
        return JSONResponse(status_code=202, content=data.get("_http_response", {}))

    if result.get("status") == "FAILED":
        error = _flow_failure(result)
        if error.startswith("HTTP_"):
            parts = error.split(":", 1)
            code = int(parts[0].replace("HTTP_", ""))
            msg = parts[1] if len(parts) > 1 else error
            detail_map = {
                404: {"error": "memory_node_not_found", "message": msg},
                422: {"error": "invalid_request", "message": msg},
                400: {"error": "bad_request", "message": msg},
                403: {"error": "forbidden", "message": msg},
            }
            raise HTTPException(status_code=code, detail=detail_map.get(code, msg))
        if "uuid" in error.lower() or "invalid" in error.lower():
            raise HTTPException(status_code=400, detail={"error": "invalid_request", "message": error})
        raise HTTPException(status_code=500, detail=error or f"{flow_name} failed")

    return data


# ------------------------------------------------------------------
# Request schemas
# ------------------------------------------------------------------

class CreateNodeRequest(BaseModel):
    content: str
    source: Optional[str] = None
    tags: Optional[List[str]] = []
    node_type: Optional[NodeType] = None
    extra: Optional[dict] = {}


class UpdateNodeRequest(BaseModel):
    content: Optional[str] = None
    tags: Optional[List[str]] = None
    node_type: Optional[NodeType] = None
    source: Optional[str] = None


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
    weight: Optional[float] = 0.5


class ExpandRequest(BaseModel):
    node_ids: List[str]
    include_linked: Optional[bool] = True
    include_similar: Optional[bool] = True
    limit_per_node: Optional[int] = 3


class RecallV3Request(BaseModel):
    query: Optional[str] = None
    tags: Optional[List[str]] = None
    limit: Optional[int] = 5
    node_type: Optional[NodeType] = None
    expand_results: Optional[bool] = False


class FederatedRecallRequest(BaseModel):
    query: Optional[str] = None
    tags: Optional[list[str]] = None
    agent_namespaces: Optional[list[str]] = None
    limit: Optional[int] = 5


class FeedbackRequest(BaseModel):
    outcome: Literal["success", "failure", "neutral"]
    context: Optional[str] = None
    # context: optional note about why this outcome occurred


class SuggestRequest(BaseModel):
    query: Optional[str] = None
    tags: Optional[list[str]] = None
    context: Optional[str] = None
    limit: Optional[int] = 3


class NodusTaskRequest(BaseModel):
    task_name: str
    task_code: str  # The Nodus task block code
    session_tags: Optional[list[str]] = []
    context: Optional[dict] = {}
    allowed_operations: Optional[list[str]] = None
    execution_id: Optional[str] = None
    capability_token: Optional[dict] = None


class ExecutionLoopRequest(BaseModel):
    workflow: str
    # "arm_analysis" | "arm_generation" | "task" | "genesis" | "leadgen" | "nodus_task"
    input: dict
    session_tags: Optional[list[str]] = []
    recall_before: Optional[bool] = True
    remember_after: Optional[bool] = True
    auto_feedback: Optional[bool] = True


class ExecutionCompleteRequest(BaseModel):
    workflow: str
    outcome_content: str
    outcome: Literal["success", "failure", "neutral"]
    recalled_node_ids: Optional[list[str]] = []
    session_tags: Optional[list[str]] = []
    context: Optional[dict] = {}


async def _execute_memory(
    request: Request,
    route_name: str,
    handler,
    *,
    db: Session,
    current_user,
    input_payload=None,
    success_status_code: int = 200,
):
    return await execute_with_pipeline(
        request=request,
        route_name=route_name,
        handler=handler,
        user_id=str(current_user["sub"]),
        metadata={"db": db},
        input_payload=input_payload,
        success_status_code=success_status_code,
    )


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------

@router.post("/nodes", status_code=201)
async def create_node(
    request: Request,
    body: CreateNodeRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    def handler(ctx):
        return _mem_run_flow("memory_node_create", {
            "content": body.content, "source": body.source,
            "tags": body.tags, "node_type": body.node_type, "extra": body.extra,
        }, db, str(current_user["sub"]))

    return await _execute_memory(request, "memory.nodes.create", handler, db=db, current_user=current_user, input_payload=body.model_dump(), success_status_code=201)
@router.get("/nodes/{node_id}")
async def get_node(
    request: Request,
    node_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    def handler(ctx):
        return _mem_run_flow("memory_node_get", {"node_id": node_id}, db, str(current_user["sub"]))

    return await _execute_memory(request, "memory.nodes.get", handler, db=db, current_user=current_user)
@router.put("/nodes/{node_id}")
async def update_node(
    request: Request,
    node_id: str,
    body: UpdateNodeRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    def handler(ctx):
        return _mem_run_flow("memory_node_update", {
            "node_id": node_id, "content": body.content,
            "tags": body.tags, "node_type": body.node_type, "source": body.source,
        }, db, str(current_user["sub"]))

    return await _execute_memory(request, "memory.nodes.update", handler, db=db, current_user=current_user, input_payload=body.model_dump())
@router.get("/nodes/{node_id}/history")
async def get_node_history(
    request: Request,
    node_id: str,
    limit: Optional[int] = 20,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    def handler(ctx):
        return _mem_run_flow("memory_node_history", {"node_id": node_id, "limit": limit}, db, str(current_user["sub"]))

    return await _execute_memory(request, "memory.nodes.history", handler, db=db, current_user=current_user)
@router.get("/nodes/{node_id}/links")
async def get_linked_nodes(
    request: Request,
    node_id: str,
    direction: str = "both",
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    def handler(ctx):
        return _mem_run_flow("memory_node_links", {"node_id": node_id, "direction": direction}, db, str(current_user["sub"]))

    return await _execute_memory(request, "memory.nodes.links", handler, db=db, current_user=current_user)
@router.get("/nodes")
async def search_nodes_by_tags(
    request: Request,
    tags: str = "",
    mode: str = "AND",
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    def handler(ctx):
        return _mem_run_flow("memory_nodes_search_tags", {"tags": tags, "mode": mode, "limit": limit}, db, str(current_user["sub"]))

    return await _execute_memory(request, "memory.nodes.search_tags", handler, db=db, current_user=current_user)
@router.post("/links", status_code=201)
async def create_link(
    request: Request,
    body: CreateLinkRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    def handler(ctx):
        return _mem_run_flow("memory_link_create", {
            "source_id": body.source_id, "target_id": body.target_id,
            "link_type": body.link_type, "weight": body.weight,
        }, db, str(current_user["sub"]))

    return await _execute_memory(request, "memory.links.create", handler, db=db, current_user=current_user, input_payload=body.model_dump(), success_status_code=201)
@router.get("/nodes/{node_id}/traverse")
async def traverse_from_node(
    request: Request,
    node_id: str,
    max_depth: Optional[int] = 3,
    link_type: Optional[str] = None,
    min_strength: Optional[float] = 0.0,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    def handler(ctx):
        return _mem_run_flow("memory_node_traverse", {
            "node_id": node_id, "max_depth": max_depth,
            "link_type": link_type, "min_strength": min_strength,
        }, db, str(current_user["sub"]))

    return await _execute_memory(request, "memory.nodes.traverse", handler, db=db, current_user=current_user)
@router.post("/nodes/expand")
async def expand_nodes(
    request: Request,
    body: ExpandRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    def handler(ctx):
        return _mem_run_flow("memory_nodes_expand", {
            "node_ids": body.node_ids, "include_linked": body.include_linked,
            "include_similar": body.include_similar, "limit_per_node": body.limit_per_node,
        }, db, str(current_user["sub"]))

    return await _execute_memory(request, "memory.nodes.expand", handler, db=db, current_user=current_user, input_payload=body.model_dump())
@router.post("/nodes/search")
async def search_similar_nodes(
    request: Request,
    body: SimilaritySearchRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    def handler(ctx):
        return _mem_run_flow("memory_nodes_search_similar", {
            "query": body.query, "limit": body.limit,
            "node_type": body.node_type, "min_similarity": body.min_similarity,
        }, db, str(current_user["sub"]))

    return await _execute_memory(request, "memory.nodes.search_similar", handler, db=db, current_user=current_user, input_payload=body.model_dump())
@router.post("/recall")
async def recall_memories(
    request: Request,
    body: RecallRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    def handler(ctx):
        return _mem_run_flow("memory_recall", {
            "query": body.query, "tags": body.tags,
            "limit": body.limit, "node_type": body.node_type,
        }, db, str(current_user["sub"]))

    return await _execute_memory(request, "memory.recall", handler, db=db, current_user=current_user, input_payload=body.model_dump())
@router.post("/recall/v3")
async def recall_v3(
    request: Request,
    body: RecallV3Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    def handler(ctx):
        return _mem_run_flow("memory_recall_v3", {
            "query": body.query, "tags": body.tags, "limit": body.limit,
            "node_type": body.node_type, "expand_results": body.expand_results,
        }, db, str(current_user["sub"]))

    return await _execute_memory(request, "memory.recall.v3", handler, db=db, current_user=current_user, input_payload=body.model_dump())
@router.post("/federated/recall")
async def federated_recall(
    request: Request,
    body: FederatedRecallRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    def handler(ctx):
        return _mem_run_flow("memory_recall_federated", {
            "query": body.query, "tags": body.tags,
            "agent_namespaces": body.agent_namespaces, "limit": body.limit,
        }, db, str(current_user["sub"]))

    return await _execute_memory(request, "memory.recall.federated", handler, db=db, current_user=current_user, input_payload=body.model_dump())
@router.get("/agents")
async def list_agents(
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    def handler(ctx):
        return _mem_run_flow("memory_agents_list", {}, db, str(current_user["sub"]))

    return await _execute_memory(request, "memory.agents.list", handler, db=db, current_user=current_user)
@router.post("/nodes/{node_id}/share")
async def share_memory_node(
    request: Request,
    node_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    def handler(ctx):
        return _mem_run_flow("memory_node_share", {"node_id": node_id}, db, str(current_user["sub"]))

    return await _execute_memory(request, "memory.nodes.share", handler, db=db, current_user=current_user)
@router.get("/agents/{namespace}/recall")
async def recall_from_agent_endpoint(
    request: Request,
    namespace: str,
    query: Optional[str] = None,
    limit: Optional[int] = 5,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    def handler(ctx):
        return _mem_run_flow("memory_agent_recall", {"namespace": namespace, "query": query, "limit": limit}, db, str(current_user["sub"]))

    return await _execute_memory(request, "memory.agents.recall", handler, db=db, current_user=current_user)
@router.post("/nodes/{node_id}/feedback")
async def record_node_feedback(
    request: Request,
    node_id: str,
    body: FeedbackRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    def handler(ctx):
        return _mem_run_flow("memory_node_feedback", {"node_id": node_id, "outcome": body.outcome}, db, str(current_user["sub"]))

    return await _execute_memory(request, "memory.nodes.feedback", handler, db=db, current_user=current_user, input_payload=body.model_dump())
@router.get("/nodes/{node_id}/performance")
async def get_node_performance(
    request: Request,
    node_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    def handler(ctx):
        return _mem_run_flow("memory_node_performance", {"node_id": node_id}, db, str(current_user["sub"]))

    return await _execute_memory(request, "memory.nodes.performance", handler, db=db, current_user=current_user)
@router.post("/suggest")
async def get_suggestions(
    request: Request,
    body: SuggestRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    def handler(ctx):
        if not body.query and not body.tags:
            raise HTTPException(
                status_code=400,
                detail={"error": "query_or_tags_required", "message": "Provide at least one of: query, tags"},
            )
        return _mem_run_flow("memory_suggest", {
            "query": body.query, "tags": body.tags,
            "context": body.context, "limit": body.limit,
        }, db, str(current_user["sub"]))

    return await _execute_memory(request, "memory.suggest", handler, db=db, current_user=current_user, input_payload=body.model_dump())
@router.post("/nodus/execute")
async def execute_nodus_task(
    request: Request,
    body: NodusTaskRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    def handler(ctx):
        return _mem_run_flow("memory_nodus_execute", {
            "task_name": body.task_name,
            "task_code": body.task_code,
            "session_tags": body.session_tags,
            "allowed_operations": body.allowed_operations,
            "execution_id": body.execution_id,
            "capability_token": body.capability_token,
        }, db, str(current_user["sub"]))

    return await _execute_memory(request, "memory.nodus.execute", handler, db=db, current_user=current_user, input_payload=body.model_dump())
@router.post("/execute")
async def execute_with_memory(
    request: Request,
    body: ExecutionLoopRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    def handler(ctx):
        return _mem_run_flow("memory_execute_loop", {
            "original_workflow": body.workflow,
            "execution_input": body.input,
            "session_tags": body.session_tags,
        }, db, str(current_user["sub"]))

    return await _execute_memory(request, "memory.execute", handler, db=db, current_user=current_user, input_payload=body.model_dump())
@router.post("/execute/complete")
async def complete_memory_loop(
    request: Request,
    body: ExecutionCompleteRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    def handler(ctx):
        raise HTTPException(
            status_code=410,
            detail={
                "error": "memory_execute_complete_deprecated",
                "message": "Execution completion is now handled inside POST /memory/execute via the canonical flow pipeline.",
            },
        )

    return await _execute_memory(request, "memory.execute.complete", handler, db=db, current_user=current_user, input_payload=body.model_dump())

