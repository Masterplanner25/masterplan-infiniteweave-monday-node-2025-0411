from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Literal, Optional
from pydantic import BaseModel
import logging

from db.database import get_db
from db.dao.memory_node_dao import MemoryNodeDAO
from services.auth_service import get_current_user

router = APIRouter(prefix="/memory", tags=["Memory"])
logger = logging.getLogger(__name__)

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


@router.put("/nodes/{node_id}")
def update_node(
    node_id: str,
    body: UpdateNodeRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Update a memory node.
    Previous state is automatically recorded in history.
    Only changed fields are recorded.
    """
    dao = MemoryNodeDAO(db)
    updated = dao.update(
        node_id=node_id,
        user_id=str(current_user["sub"]),
        content=body.content,
        tags=body.tags,
        node_type=body.node_type,
        source=body.source,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Memory node not found")
    return dao._node_to_dict(updated)


@router.get("/nodes/{node_id}/history")
def get_node_history(
    node_id: str,
    limit: Optional[int] = 20,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Get the change history for a memory node.
    Returns previous states in reverse chronological order.
    """
    dao = MemoryNodeDAO(db)
    history = dao.get_history(
        node_id=node_id,
        user_id=str(current_user["sub"]),
        limit=limit,
    )
    return {
        "node_id": node_id,
        "history": history,
        "count": len(history),
    }


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
    # Verify node exists and is owned by current user
    if not dao.get_by_id(node_id, user_id=str(current_user["sub"])):
        raise HTTPException(status_code=404, detail="Memory node not found")
    return {
        "nodes": dao.get_linked_nodes(
            node_id,
            direction=direction,
            user_id=str(current_user["sub"]),
        )
    }


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
    return {
        "nodes": dao.get_by_tags(
            tag_list,
            limit=limit,
            mode=mode,
            user_id=str(current_user["sub"]),
        )
    }


@router.post("/links", status_code=201)
def create_link(
    body: CreateLinkRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Create a directed relationship between two existing memory nodes."""
    dao = MemoryNodeDAO(db)
    user_id = str(current_user["sub"])
    source = dao.get_by_id(body.source_id, user_id=user_id)
    if not source:
        if dao._get_model_by_id(body.source_id) is not None:
            raise HTTPException(status_code=404, detail="Source node not found")
    target = dao.get_by_id(body.target_id, user_id=user_id)
    if not target:
        if dao._get_model_by_id(body.target_id) is not None:
            raise HTTPException(status_code=404, detail="Target node not found")
    try:
        return dao.create_link(body.source_id, body.target_id, body.link_type)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/nodes/{node_id}/traverse")
def traverse_from_node(
    node_id: str,
    max_depth: Optional[int] = 3,
    link_type: Optional[str] = None,
    min_strength: Optional[float] = 0.0,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    DFS traversal from a memory node.

    Follows chains of thought by exploring the strongest
    links depth-first up to max_depth hops.

    Returns the full traversal tree and a human-readable
    chain of thought narrative explaining WHY something
    matters - not just WHAT was found.
    """
    if max_depth > 5:
        max_depth = 5

    dao = MemoryNodeDAO(db)
    result = dao.traverse(
        start_node_id=node_id,
        max_depth=max_depth,
        link_type=link_type,
        user_id=str(current_user["sub"]),
        min_strength=min_strength,
    )

    if not result["found"]:
        raise HTTPException(status_code=404, detail="Memory node not found")

    return result


@router.post("/nodes/expand")
def expand_nodes(
    body: ExpandRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Expand a set of nodes to include their neighbors.

    Takes a list of node IDs and returns their connected
    context - both direct graph links and semantic neighbors.
    """
    if len(body.node_ids) > 10:
        raise HTTPException(
            status_code=400,
            detail="Maximum 10 nodes per expansion request",
        )

    dao = MemoryNodeDAO(db)
    result = dao.expand(
        node_ids=body.node_ids,
        user_id=str(current_user["sub"]),
        include_linked=body.include_linked,
        include_similar=body.include_similar,
        limit_per_node=body.limit_per_node,
    )
    return result


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
    score = (semantic*0.40) + (graph*0.15) + (recency*0.15)
            + (success_rate*0.20) + (usage_freq*0.10)
    Primary retrieval API for all Phase 3 hooks.
    """
    if not body.query and not body.tags:
        raise HTTPException(status_code=400, detail="Provide at least one of: query, tags")

    from runtime.memory import MemoryOrchestrator, memory_items_to_dicts

    metadata = {
        "tags": body.tags,
        "node_type": body.node_type,
        "limit": body.limit,
    }
    if body.node_type is None:
        metadata["node_types"] = []

    orchestrator = MemoryOrchestrator(MemoryNodeDAO)
    context = orchestrator.get_context(
        user_id=str(current_user["sub"]),
        query=body.query or "",
        task_type="analysis",
        db=db,
        max_tokens=1200,
        metadata=metadata,
    )
    results = memory_items_to_dicts(context.items)
    return {
        "query": body.query,
        "tags": body.tags,
        "results": results,
        "count": len(results),
        "scoring_version": "v2",
        "formula": {
            "semantic": 0.40,
            "graph": 0.15,
            "recency": 0.15,
            "success_rate": 0.20,
            "usage_frequency": 0.10,
            "note": "adaptive_weight multiplier applied; tag_score adds up to +0.1",
        },
    }


@router.post("/recall/v3")
def recall_v3(
    body: RecallV3Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    v3 recall - resonance scoring + optional expansion.
    """
    if not body.query and not body.tags:
        raise HTTPException(status_code=400, detail="Provide at least one of: query, tags")

    from runtime.memory import MemoryOrchestrator, memory_items_to_dicts

    metadata = {
        "tags": body.tags,
        "node_type": body.node_type,
        "limit": body.limit,
    }
    if body.node_type is None:
        metadata["node_types"] = []

    orchestrator = MemoryOrchestrator(MemoryNodeDAO)
    context = orchestrator.get_context(
        user_id=str(current_user["sub"]),
        query=body.query or "",
        task_type="analysis",
        db=db,
        max_tokens=1200,
        metadata=metadata,
    )
    results = memory_items_to_dicts(context.items)

    if body.expand_results and context.ids:
        dao = MemoryNodeDAO(db)
        expansion = dao.expand(
            node_ids=context.ids[:3],
            user_id=str(current_user["sub"]),
            include_linked=True,
            include_similar=True,
            limit_per_node=2,
        )
        return {
            "query": body.query,
            "tags": body.tags,
            "results": results,
            "expanded": expansion.get("expanded_nodes", []),
            "expansion_map": expansion.get("expansion_map", {}),
            "total_context_nodes": len(results) + len(expansion.get("expanded_nodes", [])),
            "scoring_version": "v2",
            "formula": {
                "semantic": 0.40,
                "graph": 0.15,
                "recency": 0.15,
                "success_rate": 0.20,
                "usage_frequency": 0.10,
                "note": "adaptive_weight multiplier applied; tag_score adds up to +0.1",
            },
        }

    return {
        "query": body.query,
        "tags": body.tags,
        "results": results,
        "count": len(results),
        "scoring_version": "v2",
        "formula": {
            "semantic": 0.40,
            "graph": 0.15,
            "recency": 0.15,
            "success_rate": 0.20,
            "usage_frequency": 0.10,
            "note": "adaptive_weight multiplier applied; tag_score adds up to +0.1",
        },
    }


@router.post("/federated/recall")
async def federated_recall(
    body: FederatedRecallRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Federated recall across multiple agent namespaces.

    Queries shared memory from each specified agent and
    returns merged results ranked by resonance.
    """
    if not body.query and not body.tags:
        raise HTTPException(
            status_code=400,
            detail="Provide at least one of: query, tags",
        )

    dao = MemoryNodeDAO(db)
    result = dao.recall_federated(
        query=body.query,
        tags=body.tags,
        agent_namespaces=body.agent_namespaces,
        limit=body.limit,
        user_id=str(current_user["sub"]),
    )
    return result


@router.get("/agents")
async def list_agents(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    List all registered agents and their memory stats.
    """
    from db.models.agent import Agent
    from services.memory_persistence import MemoryNodeModel

    agents = db.query(Agent).filter(
        Agent.is_active == True
    ).all()

    result = []
    for agent in agents:
        node_count = db.query(MemoryNodeModel).filter(
            MemoryNodeModel.source_agent == agent.memory_namespace,
            MemoryNodeModel.user_id == str(current_user["sub"]),
        ).count()

        shared_count = db.query(MemoryNodeModel).filter(
            MemoryNodeModel.source_agent == agent.memory_namespace,
            MemoryNodeModel.user_id == str(current_user["sub"]),
            MemoryNodeModel.is_shared == True,
        ).count()

        result.append({
            "id": agent.id,
            "name": agent.name,
            "agent_type": agent.agent_type,
            "description": agent.description,
            "memory_namespace": agent.memory_namespace,
            "is_active": agent.is_active,
            "memory_stats": {
                "total_nodes": node_count,
                "shared_nodes": shared_count,
                "private_nodes": node_count - shared_count,
            },
        })

    return {
        "agents": result,
        "total": len(result),
    }


@router.post("/nodes/{node_id}/share")
async def share_memory_node(
    node_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Share a private memory node with all agents.

    Once shared, any agent can read this node via
    federated recall. Sharing cannot be undone.
    """
    dao = MemoryNodeDAO(db)
    node = dao.share_memory(
        node_id=node_id,
        user_id=str(current_user["sub"]),
    )
    if not node:
        raise HTTPException(status_code=404, detail="Memory node not found")

    return {
        "node_id": node_id,
        "is_shared": node.is_shared,
        "source_agent": node.source_agent,
        "message": "Memory node is now shared with all agents.",
    }


@router.get("/agents/{namespace}/recall")
async def recall_from_agent_endpoint(
    namespace: str,
    query: Optional[str] = None,
    limit: Optional[int] = 5,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Query a specific agent's shared memory.
    """
    dao = MemoryNodeDAO(db)
    results = dao.recall_from_agent(
        agent_namespace=namespace,
        query=query,
        limit=limit,
        user_id=str(current_user["sub"]),
        include_private=False,
    )

    return {
        "agent_namespace": namespace,
        "query": query,
        "results": results,
        "count": len(results),
    }


@router.post("/nodes/{node_id}/feedback")
async def record_node_feedback(
    node_id: str,
    body: FeedbackRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Record explicit feedback on a memory node.

    Signals whether this memory led to a good or bad outcome.
    Updates the node's success/failure counts and adjusts
    its adaptive weight for future resonance v2 scoring.

    outcome values:
      "success" — this memory helped, boost its weight
      "failure" — this memory misled, suppress its weight
      "neutral" — acknowledged but no clear outcome

    Called explicitly by the user (thumbs up/down UI)
    or automatically by workflow hooks.
    """
    dao = MemoryNodeDAO(db)
    node = dao.record_feedback(
        node_id=node_id,
        outcome=body.outcome,
        user_id=str(current_user["sub"]),
    )
    if not node:
        raise HTTPException(status_code=404, detail="Memory node not found")

    return {
        "node_id": node_id,
        "outcome": body.outcome,
        "success_count": node.success_count,
        "failure_count": node.failure_count,
        "usage_count": node.usage_count,
        "adaptive_weight": node.weight,
        "success_rate": dao.get_success_rate(node),
        "message": {
            "success": "Weight boosted — memory reinforced",
            "failure": "Weight reduced — memory suppressed",
            "neutral": "Usage recorded — no weight change",
        }[body.outcome],
    }


@router.get("/nodes/{node_id}/performance")
async def get_node_performance(
    node_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Get performance metrics for a memory node.
    Shows how well this memory has performed over time.
    """
    dao = MemoryNodeDAO(db)
    node = dao._get_model_by_id(node_id, user_id=str(current_user["sub"]))
    if not node:
        raise HTTPException(status_code=404, detail="Memory node not found")

    success_rate = dao.get_success_rate(node)
    usage_freq = dao.get_usage_frequency_score(node)
    graph_score = dao.get_graph_connectivity_score(node_id)

    total_feedback = (node.success_count or 0) + (node.failure_count or 0)

    return {
        "node_id": node_id,
        "content_preview": (node.content or "")[:100],
        "node_type": node.node_type,
        "performance": {
            "success_count": node.success_count or 0,
            "failure_count": node.failure_count or 0,
            "usage_count": node.usage_count or 0,
            "success_rate": round(success_rate, 3),
            "adaptive_weight": round(node.weight or 1.0, 3),
            "last_outcome": node.last_outcome,
            "last_used_at": node.last_used_at.isoformat()
            if node.last_used_at
            else None,
            "total_feedback_signals": total_feedback,
            "graph_connectivity": round(graph_score, 3),
            "usage_frequency_score": round(usage_freq, 3),
        },
        "resonance_v2_preview": {
            "note": "Scores shown for this node in isolation. "
            "Actual resonance depends on query context.",
            "success_rate_component": round(success_rate * 0.20, 4),
            "usage_freq_component": round(usage_freq * 0.10, 4),
            "graph_component": round(graph_score * 0.15, 4),
            "adaptive_weight": round(node.weight or 1.0, 3),
        },
    }


@router.post("/suggest")
async def get_suggestions(
    body: SuggestRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Get suggestions based on past high-performing memories.

    Analyzes what worked before in similar contexts and
    returns actionable recommendations with reasoning.

    This is A.I.N.D.Y.'s "based on past, do this" layer —
    memory actively guides future decisions rather than
    just responding to queries.

    Confidence score = resonance_v2 × adaptive_weight
    Higher confidence = more validated by past outcomes.
    """
    if not body.query and not body.tags:
        raise HTTPException(
            status_code=400,
            detail="Provide at least one of: query, tags",
        )

    dao = MemoryNodeDAO(db)
    result = dao.suggest(
        query=body.query,
        tags=body.tags,
        context=body.context,
        user_id=str(current_user["sub"]),
        limit=body.limit,
    )
    return result


@router.post("/nodus/execute")
async def execute_nodus_task(
    body: NodusTaskRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Execute a Nodus task block with full Memory Bridge access.
    """
    from bridge.nodus_memory_bridge import create_nodus_bridge

    bridge = create_nodus_bridge(
        db=db,
        user_id=str(current_user["sub"]),
        session_tags=body.session_tags,
    )

    try:
        import sys

        nodus_path = r"C:\dev\Coding Language\src"
        if nodus_path not in sys.path:
            sys.path.insert(0, nodus_path)

        from nodus.runtime.embedding import NodusRuntime

        from db.dao.memory_node_dao import MemoryNodeDAO
        from runtime.memory import MemoryOrchestrator
        from runtime.memory.memory_feedback import MemoryFeedbackEngine
        from bridge import create_memory_node

        orchestrator = MemoryOrchestrator(MemoryNodeDAO)
        feedback_engine = MemoryFeedbackEngine()

        memory_context = orchestrator.get_context(
            user_id=str(current_user["sub"]),
            query=body.task_name or "",
            task_type="nodus_execution",
            db=db,
            max_tokens=800,
            metadata={
                "tags": body.session_tags or [],
                "node_types": [],
                "limit": 3,
            },
        )

        runtime = NodusRuntime()
        # Pattern C: host-builtins registered per-session via embedding API.
        runtime.register_function("recall", bridge.recall, arity=(0, 1, 2, 3, 4))
        runtime.register_function("recall_tool", bridge.recall_tool, arity=(0, 1, 2, 3))
        runtime.register_function("remember", bridge.remember, arity=(1, 2, 3, 4, 5))
        runtime.register_function("suggest", bridge.get_suggestions, arity=(0, 1, 2, 3))
        runtime.register_function("record_outcome", bridge.record_outcome, arity=2)
        runtime.register_function("recall_from", bridge.recall_from, arity=(1, 2, 3, 4))
        runtime.register_function("recall_all", bridge.recall_all_agents, arity=(0, 1, 2, 3))
        runtime.register_function("share", bridge.share, arity=1)

        result = runtime.run_source(
            body.task_code,
            filename=f"<nodus:{body.task_name}>",
            initial_globals={
                "memory_context": memory_context.formatted,
                "memory_ids": memory_context.ids,
            },
            host_globals={
                "memory_bridge": bridge,
                "memory_context": memory_context.formatted,
                "memory_ids": memory_context.ids,
            },
        )

        try:
            create_memory_node(
                content=f"Nodus task '{body.task_name}' executed: {result.get('stdout', '')[:500]}",
                source="nodus_task",
                tags=(body.session_tags or []) + ["nodus", "task_execution"],
                user_id=str(current_user["sub"]),
                db=db,
                node_type="outcome",
            )
        except Exception:
            pass

        try:
            success_score = 1.0 if result.get("ok") else 0.0
            feedback_engine.record_usage(
                memory_ids=memory_context.ids,
                success_score=success_score,
                db=db,
            )
        except Exception:
            pass

        return {
            "task_name": body.task_name,
            "status": "executed" if result.get("ok") else "failed",
            "memory_bridge": "active",
            "session_tags": body.session_tags,
            "result": result,
        }

    except ImportError:
        return {
            "task_name": body.task_name,
            "status": "bridge_ready",
            "message": (
                "Nodus runtime not found. Memory Bridge is available for "
                "direct API calls."
            ),
            "available_operations": [
                "POST /memory/recall/v3",
                "POST /memory/suggest",
                "POST /memory/nodes/{id}/feedback",
            ],
        }

    except Exception as exc:
        raise HTTPException(500, f"Task execution failed: {exc}")


@router.post("/execute")
async def execute_with_memory(
    body: ExecutionLoopRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Execute any workflow with the full v5 memory loop.
    """
    user_id = str(current_user["sub"])

    from bridge.nodus_memory_bridge import create_nodus_bridge

    bridge = create_nodus_bridge(
        db=db,
        user_id=user_id,
        session_tags=body.session_tags,
    )

    recalled_memories = []

    if body.recall_before:
        query = (
            body.input.get("query")
            or body.input.get("prompt")
            or body.input.get("message")
            or body.workflow
        )

        recalled_memories = bridge.recall(
            query=query,
            tags=body.session_tags,
            limit=3,
        )

    execution_context = {
        "workflow": body.workflow,
        "user_id": user_id,
        "session_tags": body.session_tags,
        "recalled_memories": recalled_memories,
        "recall_count": len(recalled_memories),
        "memory_bridge_version": "v5",
        "instructions": {
            "before_execution": (
                "Use recalled_memories as context for "
                "your workflow execution."
            ),
            "after_execution": (
                "Call POST /memory/execute/complete "
                "with your outcome to complete the loop."
            ),
        },
    }

    if recalled_memories:
        suggestions = bridge.get_suggestions(
            query=body.input.get("query", body.workflow),
            tags=body.session_tags,
            limit=2,
        )
        execution_context["suggestions"] = suggestions

    return execution_context


@router.post("/execute/complete")
async def complete_execution_loop(
    body: ExecutionCompleteRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Complete the v5 execution loop after workflow finishes.
    """
    user_id = str(current_user["sub"])

    from services.memory_capture_engine import (
        MemoryCaptureEngine,
        EVENT_SIGNIFICANCE,
    )
    from db.dao.memory_node_dao import MemoryNodeDAO

    engine = MemoryCaptureEngine(
        db=db,
        user_id=user_id,
        agent_namespace="user",
    )
    dao = MemoryNodeDAO(db)

    event_type = f"{body.workflow}_complete"
    if event_type not in EVENT_SIGNIFICANCE:
        event_type = "task_completed"

    node = engine.evaluate_and_capture(
        event_type=event_type,
        content=body.outcome_content,
        source=f"v5_execution_loop:{body.workflow}",
        tags=body.session_tags,
        context={
            **(body.context or {}),
            "outcome": body.outcome,
        },
    )

    feedback_results = []
    for node_id in body.recalled_node_ids:
        try:
            updated = dao.record_feedback(
                node_id=node_id,
                outcome=body.outcome,
                user_id=user_id,
            )
            if updated:
                feedback_results.append({
                    "node_id": node_id,
                    "new_weight": updated.weight,
                    "outcome": body.outcome,
                })
        except Exception as exc:
            logger.warning("Feedback failed for %s: %s", node_id, exc)

    return {
        "loop_complete": True,
        "memory_captured": node is not None,
        "captured_node_id": node.get("id") if node else None,
        "feedback_recorded": len(feedback_results),
        "feedback_results": feedback_results,
        "message": (
            "Execution loop complete. Memory captured "
            "and feedback recorded."
            if node else
            "Outcome below significance threshold — "
            "not stored. Feedback recorded on recalled nodes."
        ),
    }
