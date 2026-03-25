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

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from db.database import get_db
from db.models.watcher_signal import WatcherSignal
from services.auth_service import verify_api_key

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


def _trigger_eta_update(db: Session, user_id: str = None) -> None:
    """Fire-and-forget ETA + Infinity score recalculation on session_ended. Never propagates."""
    try:
        from db.models.masterplan import MasterPlan
        from services.eta_service import recalculate_all_etas
        recalculate_all_etas(db=db)
        logger.debug("ETA recalculation triggered by watcher session_ended")
    except Exception as exc:
        logger.debug("ETA recalculation skipped (non-fatal): %s", exc)

    # Trigger Infinity score recalculation (fire-and-forget)
    try:
        from services.infinity_service import calculate_infinity_score
        # WatcherSignal has no user_id; when user_id is provided by caller, recalculate
        if user_id:
            calculate_infinity_score(
                user_id=user_id,
                db=db,
                trigger_event="session_ended",
            )
    except Exception as exc:
        logger.warning("Infinity score after session failed: %s", exc)


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
    # Validate all signals before persisting any
    for i, sig in enumerate(batch.signals):
        if sig.signal_type not in _VALID_SIGNAL_TYPES:
            raise HTTPException(
                status_code=422,
                detail=f"Signal [{i}]: unknown signal_type {sig.signal_type!r}",
            )
        if sig.activity_type not in _VALID_ACTIVITY_TYPES:
            raise HTTPException(
                status_code=422,
                detail=f"Signal [{i}]: unknown activity_type {sig.activity_type!r}",
            )

    persisted = 0
    session_ended_count = 0

    for sig in batch.signals:
        try:
            ts = _parse_timestamp(sig.timestamp)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        meta = sig.metadata or {}
        row = WatcherSignal(
            signal_type=sig.signal_type,
            session_id=sig.session_id,
            user_id=sig.user_id or None,
            app_name=sig.app_name,
            window_title=sig.window_title or None,
            activity_type=sig.activity_type,
            signal_timestamp=ts,
            received_at=datetime.now(timezone.utc),
            duration_seconds=meta.get("duration_seconds"),
            focus_score=meta.get("focus_score"),
            signal_metadata=meta if meta else None,
        )
        db.add(row)
        if sig.signal_type == "session_ended":
            session_ended_count += 1
        persisted += 1

    db.commit()
    logger.info("Watcher: persisted %d signals (%d session_ended)", persisted, session_ended_count)

    # ETA recalculation on any session_ended signal
    if session_ended_count > 0:
        # Use user_id from first signal in batch that has one
        batch_user_id = next((s.user_id for s in batch.signals if s.user_id), None)
        _trigger_eta_update(db, user_id=batch_user_id)

    return {"accepted": persisted, "session_ended_count": session_ended_count}


@router.get("/signals", response_model=List[SignalResponse])
def list_signals(
    session_id: Optional[str] = Query(default=None, description="Filter by session UUID"),
    signal_type: Optional[str] = Query(default=None, description="Filter by signal type"),
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
