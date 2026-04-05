# /routes/bridge_router.py
from __future__ import annotations

import time
import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from core.execution_helper import execute_with_pipeline
from core.execution_signal_helper import queue_memory_capture
from db.dao.memory_node_dao import MemoryNodeDAO
from db.database import get_db
from db.models.bridge_user_event import BridgeUserEvent
from config import settings
from services.auth_service import get_current_user, verify_api_key

logger = logging.getLogger(__name__)

# --- Config Guard ---------------------------------------------------------
if not settings.DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not configured in .env or Settings.")


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


# --------------------------------------------------------------------------
# CREATE NODE
# --------------------------------------------------------------------------
@router.post("/nodes", response_model=NodeResponse, status_code=status.HTTP_201_CREATED)
async def create_node(
    request: Request,
    payload: NodeCreateRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):

    def handler(ctx):
        saved = queue_memory_capture(
            db=db,
            user_id=str(current_user["sub"]),
            agent_namespace=payload.source_agent or "user",
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
                detail={
                    "error": "bridge_node_create_failed",
                    "message": "Failed to create memory node",
                },
            )

        return {
            "data": NodeResponse(
                id=str(saved.get("id")),
                content=saved.get("content"),
                tags=saved.get("tags", []),
                node_type=saved.get("node_type"),
                extra=saved.get("extra") or {},
            ),
            "execution_signals": {
                "events": [
                    {
                        "type": "node_creation",
                        "payload": {
                            "drop_point_id": "bridge",
                            "summary": f"Node created: {(saved.get('content') or '')[:50]}",
                        },
                    }
                ]
            },
        }

    return await execute_with_pipeline(
        request=request,
        route_name="bridge.create_node",
        handler=handler,
        success_status_code=status.HTTP_201_CREATED,
    )


# --------------------------------------------------------------------------
# SEARCH NODES
# --------------------------------------------------------------------------
@router.get("/nodes", response_model=NodeSearchResponse)
async def search_nodes(
    request: Request,
    tag: Optional[List[str]] = None,
    mode: Optional[str] = "OR",
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):

    def handler(ctx):
        dao = MemoryNodeDAO(db)
        nodes = dao.find_by_tags(
            tag or [], limit=limit, mode=mode, user_id=str(current_user["sub"])
        )

        result = [
            NodeResponse(
                id=str(getattr(n, "id", n.get("id"))),
                content=getattr(n, "content", n.get("content", "")),
                tags=getattr(n, "tags", n.get("tags", [])),
                node_type=getattr(n, "node_type", n.get("node_type")),
                extra=getattr(n, "extra", n.get("extra", {})) or {},
            )
            for n in nodes
        ]

        return {"data": NodeSearchResponse(nodes=result)}

    return await execute_with_pipeline(
        request=request,
        route_name="bridge.search_nodes",
        handler=handler,
    )


# --------------------------------------------------------------------------
# CREATE LINK
# --------------------------------------------------------------------------
@router.post("/link", response_model=LinkResponse, status_code=status.HTTP_201_CREATED)
async def create_link(
    request: Request,
    payload: LinkCreateRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):

    def handler(ctx):
        dao = MemoryNodeDAO(db)

        source = dao.load_memory_node(payload.source_id)
        target = dao.load_memory_node(payload.target_id)

        if not source or not target:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": "bridge_link_nodes_not_found",
                    "message": "Source or target node not found",
                },
            )

        if source.get("user_id") != str(current_user["sub"]) or target.get(
            "user_id"
        ) != str(current_user["sub"]):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "bridge_link_forbidden",
                    "message": "Cannot link nodes you do not own",
                },
            )

        link = dao.create_link(
            payload.source_id,
            payload.target_id,
            link_type=payload.link_type,
        )

        return {
            "data": LinkResponse(
                id=link["id"],
                source_node_id=link["source_node_id"],
                target_node_id=link["target_node_id"],
                link_type=link["link_type"],
                strength=link["strength"],
                created_at=str(link["created_at"])
                if link.get("created_at")
                else None,
            )
        }

    return await execute_with_pipeline(
        request=request,
        route_name="bridge.create_link",
        handler=handler,
        success_status_code=status.HTTP_201_CREATED,
    )


# --------------------------------------------------------------------------
# USER EVENT
# --------------------------------------------------------------------------
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
async def bridge_user_event(
    request: Request,
    event: UserEvent,
    _key: str = Depends(verify_api_key),
    db: Session = Depends(get_db),
):

    def handler(ctx):
        timestamp = event.timestamp or time.strftime(
            "%Y-%m-%d %H:%M:%S", time.gmtime()
        )
        occurred_at = _parse_event_timestamp(event.timestamp) or datetime.now(
            timezone.utc
        )

        try:
            db.add(
                BridgeUserEvent(
                    user_name=event.user,
                    origin=event.origin,
                    raw_timestamp=event.timestamp,
                    occurred_at=occurred_at,
                )
            )
            db.commit()
        except Exception as exc:
            db.rollback()
            logger.warning("Failed to persist bridge user event: %s", exc)

        return {
            "status": "logged",
            "user": event.user,
            "origin": event.origin,
            "timestamp": timestamp,
        }

    return await execute_with_pipeline(
        request=request,
        route_name="bridge.user_event",
        handler=handler,
    )
