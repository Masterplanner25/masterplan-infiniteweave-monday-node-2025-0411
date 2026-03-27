"""
watcher_router.py — A.I.N.D.Y. Watcher signal receiver.

Endpoints:
  POST /watcher/signals   — receive batched signals from Watcher process
  GET  /watcher/signals   — query stored signals (paginated)

Auth: API key (X-API-Key header) — Watcher is a headless background process.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from db.database import get_db
from db.models.watcher_signal import WatcherSignal
from services.auth_service import verify_api_key
from services.flow_engine import execute_intent

logger = logging.getLogger(__name__)

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


def _extract_ingest_result(result: Dict[str, Any]) -> WatcherIngestResponse:
    if result.get("status") != "SUCCESS":
        raise HTTPException(status_code=500, detail="Watcher ingest failed")

    payload = result.get("result") or {}
    return WatcherIngestResponse(
        accepted=int(payload.get("accepted") or 0),
        session_ended_count=int(payload.get("session_ended_count") or 0),
        orchestration=payload.get("orchestration"),
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/signals", status_code=201, response_model=WatcherIngestResponse)
def receive_signals(
    batch: SignalBatch,
    db: Session = Depends(get_db),
) -> WatcherIngestResponse:
    """
    Receive a batch of watcher signals. Validates, persists, and returns counts.
    Invalid signals are rejected wholesale (entire batch) if any signal has
    an unknown signal_type — partial persistence is not supported.
    """
    for idx, sig in enumerate(batch.signals):
        _validate_signal(sig, idx)

    result = execute_intent(
        intent_data={
            "workflow_type": "watcher_ingest",
            "signals": [sig.model_dump() for sig in batch.signals],
        },
        db=db,
        user_id=None,
    )
    return _extract_ingest_result(result)


@router.get("/signals", response_model=List[SignalResponse])
def list_signals(
    session_id: Optional[str] = Query(default=None, description="Filter by session UUID"),
    signal_type: Optional[str] = Query(default=None, description="Filter by signal type"),
    user_id: Optional[str] = Query(default=None, description="Filter by user UUID"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> List[SignalResponse]:
    """
    Query stored watcher signals. Supports filtering by session_id and signal_type.
    Returns signals ordered by signal_timestamp descending.
    """
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
    return [_signal_to_response(s) for s in signals]
