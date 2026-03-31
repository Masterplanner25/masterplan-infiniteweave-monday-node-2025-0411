"""
watcher_router.py — A.I.N.D.Y. Watcher signal receiver.

Endpoints:
  POST /watcher/signals   — receive batched signals from Watcher process
  GET  /watcher/signals   — query stored signals (paginated)

Auth: API key (X-API-Key header) — Watcher is a headless background process.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from core.execution_helper import execute_with_pipeline_sync
from db.database import get_db
from db.models.watcher_signal import WatcherSignal
from services.auth_service import verify_api_key
from services.autonomous_controller import build_decision_response
from services.autonomous_controller import evaluate_live_trigger
from services.autonomous_controller import record_decision
from services.async_job_service import build_deferred_response
from services.async_job_service import defer_async_job
from services.flow_engine import execute_intent
from utils.trace_context import ensure_trace_id

router = APIRouter(
    prefix="/watcher",
    tags=["Watcher"],
    dependencies=[Depends(verify_api_key)],
)


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class SignalPayload(BaseModel):
    signal_type: str = Field(..., description="session_started | session_ended | distraction_detected | focus_achieved | context_switch | heartbeat")
    session_id: str = Field(..., description="UUID string grouping signals within one session")
    timestamp: str = Field(..., description="ISO 8601 UTC timestamp from watcher")
    app_name: str = Field(..., description="Active application name")
    window_title: str = Field(default="", description="Active window title")
    activity_type: str = Field(..., description="work | communication | distraction | idle | unknown")
    metadata: Dict[str, Any] = Field(default_factory=dict)
    user_id: Optional[str] = Field(default=None, description="User ID to associate with this signal batch")


class SignalBatch(BaseModel):
    signals: List[SignalPayload] = Field(..., min_length=1, max_length=100)


class SignalResponse(BaseModel):
    id: int
    signal_type: str
    session_id: str
    app_name: str
    window_title: Optional[str]
    activity_type: str
    signal_timestamp: str
    received_at: str
    duration_seconds: Optional[float]
    focus_score: Optional[float]
    metadata: Optional[Dict[str, Any]]


class WatcherIngestResponse(BaseModel):
    accepted: int
    session_ended_count: int
    orchestration: Optional[Dict[str, Any]] = None


_VALID_SIGNAL_TYPES = frozenset(
    [
        "session_started",
        "session_ended",
        "distraction_detected",
        "focus_achieved",
        "context_switch",
        "heartbeat",
    ]
)

_VALID_ACTIVITY_TYPES = frozenset(
    ["work", "communication", "distraction", "idle", "unknown"]
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_timestamp(ts_str: str) -> datetime:
    """Parse ISO 8601 UTC timestamp. Raises ValueError on failure."""
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception as exc:
        raise ValueError(f"Invalid timestamp: {ts_str!r}") from exc


def _signal_to_response(s: WatcherSignal) -> SignalResponse:
    return SignalResponse(
        id=s.id,
        signal_type=s.signal_type,
        session_id=s.session_id,
        app_name=s.app_name,
        window_title=s.window_title,
        activity_type=s.activity_type,
        signal_timestamp=s.signal_timestamp.isoformat(),
        received_at=s.received_at.isoformat(),
        duration_seconds=s.duration_seconds,
        focus_score=s.focus_score,
        metadata=s.signal_metadata,
    )


def _validate_signal(sig: SignalPayload, idx: int) -> None:
    if sig.signal_type not in _VALID_SIGNAL_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Signal [{idx}]: unknown signal_type {sig.signal_type!r}",
        )
    if sig.activity_type not in _VALID_ACTIVITY_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Signal [{idx}]: unknown activity_type {sig.activity_type!r}",
        )
    try:
        _parse_timestamp(sig.timestamp)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if sig.user_id:
        try:
            UUID(str(sig.user_id))
        except Exception as exc:
            raise HTTPException(
                status_code=422,
                detail=f"Signal [{idx}]: invalid user_id {sig.user_id!r}",
            ) from exc


def _extract_ingest_result(result: Dict[str, Any]) -> Dict[str, Any]:
    if result.get("status") != "SUCCESS":
        raise HTTPException(status_code=500, detail="Watcher ingest failed")

    payload = result.get("result") or {}
    return {
        "accepted": int(payload.get("accepted") or 0),
        "session_ended_count": int(payload.get("session_ended_count") or 0),
        "orchestration": payload.get("orchestration"),
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/signals", status_code=201)
def receive_signals(
    batch: SignalBatch,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Receive a batch of watcher signals. Validates, persists, and returns counts.
    Invalid signals are rejected wholesale (entire batch) if any signal has
    an unknown signal_type — partial persistence is not supported.
    """
    def handler(ctx):
        for idx, sig in enumerate(batch.signals):
            _validate_signal(sig, idx)

        trace_id = str(ctx.request_id or ensure_trace_id())
        trigger_context = {
            "goal": "watcher_ingest",
            "importance": 0.40,
            "goal_alignment": 0.45,
        }
        user_id = next((sig.user_id for sig in batch.signals if sig.user_id), None)
        evaluation = evaluate_live_trigger(
            db=db,
            trigger={"trigger_type": "watcher", "source": "watcher_router", "goal": "watcher_ingest"},
            user_id=user_id,
            context=trigger_context,
        )
        record_decision(
            db=db,
            trigger={"trigger_type": "watcher", "source": "watcher_router", "goal": "watcher_ingest"},
            evaluation=evaluation,
            user_id=user_id,
            trace_id=trace_id,
            context=trigger_context,
        )
        if evaluation["decision"] == "ignore":
            return build_decision_response(
                evaluation,
                trace_id=trace_id,
                result={"accepted": 0, "session_ended_count": 0, "orchestration": None},
            )
        if evaluation["decision"] == "defer":
            log_id = defer_async_job(
                task_name="watcher.ingest",
                payload={
                    "signals": [sig.model_dump() for sig in batch.signals],
                    "user_id": user_id,
                    "__autonomy": {"trigger_type": "watcher", "source": "watcher_router", "context": trigger_context},
                },
                user_id=user_id,
                source="watcher_router",
                decision=evaluation,
            )
            return build_deferred_response(
                log_id,
                task_name="watcher.ingest",
                source="watcher_router",
                decision=evaluation,
            )

        result = execute_intent(
            intent_data={
                "workflow_type": "watcher_ingest",
                "signals": [sig.model_dump() for sig in batch.signals],
            },
            db=db,
            user_id=user_id,
        )
        return _extract_ingest_result(result)

    return execute_with_pipeline_sync(
        request=None,
        route_name="watcher.signals.receive",
        handler=handler,
        user_id=next((sig.user_id for sig in batch.signals if sig.user_id), None),
        input_payload=batch.model_dump(),
        metadata={"db": db},
        success_status_code=201,
    )


@router.get("/signals")
def list_signals(
    session_id: Optional[str] = Query(default=None, description="Filter by session UUID"),
    signal_type: Optional[str] = Query(default=None, description="Filter by signal type"),
    user_id: Optional[str] = Query(default=None, description="Filter by user UUID"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Query stored watcher signals. Supports filtering by session_id and signal_type.
    Returns signals ordered by signal_timestamp descending.
    """
    def handler(ctx):
        q = db.query(WatcherSignal)
        if session_id:
            q = q.filter(WatcherSignal.session_id == session_id)
        if user_id:
            try:
                q = q.filter(WatcherSignal.user_id == UUID(str(user_id)))
            except Exception as exc:
                raise HTTPException(
                    status_code=422,
                    detail=f"Invalid user_id filter: {user_id!r}",
                ) from exc
        if signal_type:
            if signal_type not in _VALID_SIGNAL_TYPES:
                raise HTTPException(
                    status_code=422,
                    detail=f"Unknown signal_type: {signal_type!r}",
                )
            q = q.filter(WatcherSignal.signal_type == signal_type)

        signals = (
            q.order_by(WatcherSignal.signal_timestamp.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return [_signal_to_response(s).model_dump() for s in signals]

    return execute_with_pipeline_sync(
        request=None,
        route_name="watcher.signals.list",
        handler=handler,
        user_id=user_id,
        metadata={"db": db},
        input_payload={
            "session_id": session_id,
            "signal_type": signal_type,
            "user_id": user_id,
            "limit": limit,
            "offset": offset,
        },
    )
