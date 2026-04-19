from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from uuid import UUID

from AINDY.core.execution_helper import execute_with_pipeline

from AINDY.db.database import get_db
from AINDY.platform_layer.rate_limiter import limiter

from apps.rippletrace.services import rippletrace_services
from AINDY.services.auth_service import get_current_user
from apps.rippletrace.services.rippletrace_service import (
    build_trace_graph,
    calculate_ripple_span,
    detect_root_event,
    detect_terminal_events,
    generate_trace_insights,
)


router = APIRouter(
    prefix="/rippletrace",
    tags=["RippleTrace"],
    dependencies=[Depends(get_current_user)],
)


# === Schemas ===
class DropPoint(BaseModel):
    id: str
    title: str
    platform: str
    url: Optional[str] = None
    date_dropped: Optional[datetime] = None
    core_themes: List[str]
    tagged_entities: List[str]
    intent: str


class Ping(BaseModel):
    id: str
    drop_point_id: str
    ping_type: str
    source_platform: str
    date_detected: Optional[datetime] = None
    connection_summary: Optional[str] = None
    external_url: Optional[str] = None
    reaction_notes: Optional[str] = None
    strength: Optional[float] = Field(1.0, ge=0.0)


class RippleEvent(BaseModel):
    ping_type: str
    source_platform: Optional[str] = "AINDY"
    summary: Optional[str] = None
    url: Optional[str] = None
    notes: Optional[str] = None
    drop_point_id: Optional[str] = "bridge"


# === ROUTES ===

@router.post("/drop_point")
@limiter.limit("30/minute")
async def create_drop_point(
    request: Request,
    dp: DropPoint,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    def handler(ctx):
        return rippletrace_services.add_drop_point(
            db, dp, user_id=str(current_user["sub"])
        )

    return await execute_with_pipeline(request, "rippletrace_create_drop_point", handler)


@router.post("/ping")
@limiter.limit("30/minute")
async def create_ping(
    request: Request,
    pg: Ping,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    def handler(ctx):
        return rippletrace_services.add_ping(
            db, pg, user_id=str(current_user["sub"])
        )

    return await execute_with_pipeline(request, "rippletrace_create_ping", handler)


@router.get("/ripples/{drop_point_id}")
@limiter.limit("60/minute")
async def get_ripples(
    request: Request,
    drop_point_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    def handler(ctx):
        return rippletrace_services.get_ripples(
            db, drop_point_id, user_id=str(current_user["sub"])
        )

    return await execute_with_pipeline(request, "rippletrace_get_ripples", handler)


@router.get("/drop_points")
@limiter.limit("60/minute")
async def all_drop_points(
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    def handler(ctx):
        return rippletrace_services.get_all_drop_points(
            db, user_id=str(current_user["sub"])
        )

    return await execute_with_pipeline(request, "rippletrace_all_drop_points", handler)


@router.get("/pings")
@limiter.limit("60/minute")
async def all_pings(
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    def handler(ctx):
        return rippletrace_services.get_all_pings(
            db, user_id=str(current_user["sub"])
        )

    return await execute_with_pipeline(request, "rippletrace_all_pings", handler)


@router.get("/recent")
@limiter.limit("60/minute")
async def recent_ripples(
    request: Request,
    limit: int = 10,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    def handler(ctx):
        return rippletrace_services.get_recent_ripples(
            db, limit, user_id=str(current_user["sub"])
        )

    return await execute_with_pipeline(request, "rippletrace_recent", handler)


@router.post("/event")
@limiter.limit("30/minute")
async def log_ripple_event(
    request: Request,
    event: RippleEvent,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    def handler(ctx):
        # convert direct event emission → execution_signals
        return {
            "data": {
                "status": "logged",
                "event": event.model_dump(),
            },
            "execution_signals": {
                "events": [
                    {
                        "type": "ripple_event",
                        "payload": event.model_dump(),
                    }
                ]
            },
        }

    return await execute_with_pipeline(request, "rippletrace_log_event", handler)


@router.get("/{trace_id}")
@limiter.limit("60/minute")
async def get_trace_graph(
    request: Request,
    trace_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    def handler(ctx):
        from apps.rippletrace.services.rippletrace_service import count_trace_events

        user_id = str(current_user["sub"])
        events = count_trace_events(db, trace_id, user_id)

        if events == 0:
            return {
                "trace_id": trace_id,
                "nodes": [],
                "edges": [],
                "root_event": None,
                "terminal_events": [],
                "ripple_span": {
                    "node_count": 0,
                    "edge_count": 0,
                    "depth": 0,
                    "terminal_count": 0,
                },
                "insights": {
                    "root_cause": None,
                    "dominant_path": [],
                    "failure_clusters": [],
                    "summary": "No causal insight available for this trace.",
                    "recommendations": [],
                },
            }

        graph = build_trace_graph(db, trace_id)

        return {
            "trace_id": trace_id,
            "nodes": graph["nodes"],
            "edges": graph["edges"],
            "root_event": detect_root_event(db, trace_id),
            "terminal_events": detect_terminal_events(db, trace_id),
            "ripple_span": calculate_ripple_span(db, trace_id),
            "insights": generate_trace_insights(db, trace_id),
        }

    return await execute_with_pipeline(request, "rippletrace_trace_graph", handler)
