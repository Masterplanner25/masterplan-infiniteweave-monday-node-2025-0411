from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from AINDY.agents.agent_coordinator import detect_memory_write_conflict
from AINDY.agents.agent_coordinator import detect_run_conflict
from AINDY.core.execution_helper import execute_with_pipeline_sync
from AINDY.agents.agent_message_bus import acknowledge_message
from AINDY.agents.agent_message_bus import get_inbox
from AINDY.agents.agent_runtime.shared import LOCAL_AGENT_ID
from AINDY.agents.agent_coordinator import _is_stale
from AINDY.db.database import get_db
from AINDY.platform_layer.rate_limiter import limiter
from AINDY.agents.agent_coordinator import coordination_graph
from AINDY.agents.agent_coordinator import get_agent_status
from AINDY.agents.agent_coordinator import list_agents
from AINDY.agents.agent_coordinator import register_or_update_agent
from AINDY.agents.agent_coordinator import serialize_agent_registry
from AINDY.agents.agent_runtime.presentation import run_to_dict
from AINDY.db.models.agent_run import AgentRun
from AINDY.db.models.agent_registry import AgentRegistry
from AINDY.memory.memory_persistence import MemoryNodeModel
from AINDY.services.auth_service import get_current_user
from AINDY.utils.uuid_utils import normalize_uuid


router = APIRouter(prefix="/coordination", tags=["Coordination"])


class AgentRegisterRequest(BaseModel):
    agent_id: str
    capabilities: list[str] = []
    current_state: dict = {}
    load: float = Field(0.0, ge=0.0, le=1.0)
    health_status: str = "healthy"


class AgentHeartbeatRequest(BaseModel):
    load: float = Field(0.0, ge=0.0, le=1.0)
    health_status: str = "healthy"
    current_state: dict | None = None


class MessageAcknowledgeRequest(BaseModel):
    agent_id: str


class RunConflictRequest(BaseModel):
    objective: str
    agent_id: str | None = None


class MemoryConflictRequest(BaseModel):
    memory_path: str
    agent_id: str | None = None


@router.get("/agents")
@limiter.limit("60/minute")
def get_agents(
    request: Request,
    include_stale: bool = False,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return execute_with_pipeline_sync(
        request=None,
        route_name="coordination.agents.list",
        handler=lambda ctx: list_agents(db, include_stale=include_stale),
        user_id=str(current_user["sub"]),
        metadata={"db": db},
    )


@router.get("/agents/status")
@limiter.limit("60/minute")
def get_agents_status(
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return execute_with_pipeline_sync(
        request=None,
        route_name="coordination.agents.status",
        handler=lambda ctx: get_agent_status(db),
        user_id=str(current_user["sub"]),
        metadata={"db": db},
    )


@router.get("/graph")
@limiter.limit("60/minute")
def get_coordination_graph(
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return execute_with_pipeline_sync(
        request=None,
        route_name="coordination.graph.get",
        handler=lambda ctx: coordination_graph(db, user_id=current_user["sub"]),
        user_id=str(current_user["sub"]),
        metadata={"db": db},
    )


@router.post("/agents/register")
@limiter.limit("30/minute")
def register_agent(
    request: Request,
    body: AgentRegisterRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return execute_with_pipeline_sync(
        request=None,
        route_name="coordination.agents.register",
        handler=lambda ctx: register_or_update_agent(
            db,
            agent_id=body.agent_id,
            capabilities=body.capabilities,
            current_state=body.current_state,
            load=body.load,
            health_status=body.health_status,
        ),
        user_id=str(current_user["sub"]),
        metadata={"db": db},
        input_payload=body.model_dump(),
    )


@router.post("/agents/{agent_id}/heartbeat")
@limiter.limit("60/minute")
def heartbeat_agent(
    request: Request,
    agent_id: str,
    body: AgentHeartbeatRequest | None = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    heartbeat = body or AgentHeartbeatRequest()

    def handler(ctx):
        if str(agent_id) == LOCAL_AGENT_ID:
            raise HTTPException(
                status_code=400,
                detail="Cannot heartbeat the built-in local agent via API — it self-registers during execution.",
            )

        normalized_agent_id = normalize_uuid(agent_id)
        row = db.query(AgentRegistry).filter(AgentRegistry.agent_id == normalized_agent_id).first()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")

        was_stale = _is_stale(row.last_seen, datetime.now(timezone.utc))
        result = register_or_update_agent(
            db,
            agent_id=str(normalized_agent_id),
            capabilities=list(row.capabilities or []),
            current_state=heartbeat.current_state if heartbeat.current_state is not None else dict(row.current_state or {}),
            load=heartbeat.load,
            health_status=heartbeat.health_status,
        )
        result["was_stale"] = was_stale
        return result

    return execute_with_pipeline_sync(
        request=None,
        route_name="coordination.agents.heartbeat",
        handler=handler,
        user_id=str(current_user["sub"]),
        metadata={"db": db},
        input_payload={"agent_id": agent_id, **heartbeat.model_dump(exclude_none=True)},
    )


@router.delete("/agents/{agent_id}")
@limiter.limit("10/minute")
def deregister_agent(
    request: Request,
    agent_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    def handler(ctx):
        if str(agent_id) == LOCAL_AGENT_ID:
            raise HTTPException(
                status_code=400,
                detail="Cannot deregister the built-in local agent.",
            )

        normalized_agent_id = normalize_uuid(agent_id)
        row = db.query(AgentRegistry).filter(AgentRegistry.agent_id == normalized_agent_id).first()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")

        db.delete(row)
        db.commit()
        return {"agent_id": agent_id, "status": "deregistered"}

    return execute_with_pipeline_sync(
        request=None,
        route_name="coordination.agents.deregister",
        handler=handler,
        user_id=str(current_user["sub"]),
        metadata={"db": db},
        input_payload={"agent_id": agent_id},
    )


@router.get("/runs")
@limiter.limit("30/minute")
def get_coordination_runs(
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = normalize_uuid(current_user["sub"])
    return execute_with_pipeline_sync(
        request=None,
        route_name="coordination.runs.list",
        handler=lambda ctx: [
            run_to_dict(run)
            for run in (
                db.query(AgentRun)
                .filter(
                    AgentRun.user_id == user_id,
                    AgentRun.coordination_role.isnot(None),
                )
                .order_by(AgentRun.created_at.desc())
                .limit(50)
                .all()
            )
        ],
        user_id=str(current_user["sub"]),
        metadata={"db": db},
    )


@router.get("/runs/{parent_run_id}/children")
@limiter.limit("60/minute")
def get_coordination_run_children(
    request: Request,
    parent_run_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    def handler(ctx):
        user_id = normalize_uuid(current_user["sub"])
        parent = db.query(AgentRun).filter(AgentRun.id == normalize_uuid(parent_run_id)).first()
        if parent is None:
            raise HTTPException(status_code=404, detail=f"Parent run {parent_run_id} not found")
        if parent.user_id != user_id:
            raise HTTPException(status_code=403, detail="Not authorized to view this run")
        return [
            run_to_dict(run)
            for run in (
                db.query(AgentRun)
                .filter(AgentRun.parent_run_id == parent.id)
                .order_by(AgentRun.created_at.desc())
                .all()
            )
        ]

    return execute_with_pipeline_sync(
        request=None,
        route_name="coordination.runs.children",
        handler=handler,
        user_id=str(current_user["sub"]),
        metadata={"db": db},
        input_payload={"parent_run_id": parent_run_id},
    )


@router.get("/messages/inbox")
@limiter.limit("60/minute")
def get_coordination_inbox(
    request: Request,
    agent_id: str,
    message_type: str | None = None,
    include_acknowledged: bool = False,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    def handler(ctx):
        messages = get_inbox(
            db,
            agent_id=agent_id,
            user_id=str(current_user["sub"]),
            message_type=message_type,
            include_acknowledged=include_acknowledged,
            limit=min(limit, 100),
        )
        return {"messages": messages, "count": len(messages)}

    return execute_with_pipeline_sync(
        request=None,
        route_name="coordination.messages.inbox",
        handler=handler,
        user_id=str(current_user["sub"]),
        metadata={"db": db},
        input_payload={
            "agent_id": agent_id,
            "message_type": message_type,
            "include_acknowledged": include_acknowledged,
            "limit": min(limit, 100),
        },
    )


@router.post("/messages/{message_id}/acknowledge")
@limiter.limit("60/minute")
def acknowledge_coordination_message(
    request: Request,
    message_id: str,
    body: MessageAcknowledgeRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    def handler(ctx):
        ack_id = acknowledge_message(
            db,
            message_id=message_id,
            agent_id=body.agent_id,
            user_id=str(current_user["sub"]),
        )
        return {
            "acknowledged": True,
            "message_id": message_id,
            "acknowledgment_event_id": ack_id,
        }

    return execute_with_pipeline_sync(
        request=None,
        route_name="coordination.messages.acknowledge",
        handler=handler,
        user_id=str(current_user["sub"]),
        metadata={"db": db},
        input_payload={"message_id": message_id, **body.model_dump()},
    )


@router.get("/memory/shared")
@limiter.limit("60/minute")
def get_shared_memory(
    request: Request,
    limit: int = 20,
    tags: str | None = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    def handler(ctx):
        user_id = normalize_uuid(current_user["sub"])
        query = (
            db.query(MemoryNodeModel)
            .filter(MemoryNodeModel.user_id == user_id)
            .filter(MemoryNodeModel.visibility.in_(["shared", "global"]))
            .order_by(MemoryNodeModel.created_at.desc())
            .limit(min(limit, 100))
        )
        nodes = [_serialize_memory_node(row) for row in query.all()]
        if tags:
            tag_list = [t.strip() for t in tags.split(",") if t.strip()]
            nodes = [
                node
                for node in nodes
                if any(tag in (node.get("tags") or []) for tag in tag_list)
            ]
        return {"nodes": nodes[:limit], "count": len(nodes[:limit])}

    return execute_with_pipeline_sync(
        request=None,
        route_name="coordination.memory.shared",
        handler=handler,
        user_id=str(current_user["sub"]),
        metadata={"db": db},
        input_payload={"limit": min(limit, 100), "tags": tags},
    )


@router.post("/conflict/run")
@limiter.limit("30/minute")
def detect_run_conflict_route(
    request: Request,
    body: RunConflictRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return execute_with_pipeline_sync(
        request=None,
        route_name="coordination.conflict.run",
        handler=lambda ctx: detect_run_conflict(
            db,
            user_id=str(current_user["sub"]),
            objective=body.objective,
            agent_id=body.agent_id,
        ),
        user_id=str(current_user["sub"]),
        metadata={"db": db},
        input_payload=body.model_dump(),
    )


@router.post("/conflict/memory")
@limiter.limit("30/minute")
def detect_memory_conflict_route(
    request: Request,
    body: MemoryConflictRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return execute_with_pipeline_sync(
        request=None,
        route_name="coordination.conflict.memory",
        handler=lambda ctx: detect_memory_write_conflict(
            db,
            user_id=str(current_user["sub"]),
            memory_path=body.memory_path,
            agent_id=body.agent_id,
        ),
        user_id=str(current_user["sub"]),
        metadata={"db": db},
        input_payload=body.model_dump(),
    )


def _serialize_memory_node(row: MemoryNodeModel) -> dict:
    return {
        "id": str(row.id),
        "content": row.content,
        "tags": row.tags or [],
        "visibility": row.visibility,
        "memory_type": row.memory_type,
        "source": row.source,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }

