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

from core.execution_gate import to_envelope
from core.execution_helper import execute_with_pipeline_sync
from db.database import get_db
from runtime.flow_engine import execute_intent
from services.auth_service import verify_api_key

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
# Helpers (validation only — no DB access)
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


def _run_flow_watcher(flow_name: str, payload: dict, db: Session, user_id: str | None):
    from runtime.flow_engine import run_flow
    result = run_flow(flow_name, payload, db=db, user_id=user_id)
    if result.get("status") == "FAILED":
        error = result.get("error", "")
        if error.startswith("HTTP_"):
            parts = error.split(":", 1)
            code = int(parts[0].replace("HTTP_", ""))
            msg = parts[1] if len(parts) > 1 else error
            raise HTTPException(status_code=code, detail=msg)
        raise HTTPException(status_code=500, detail=error or f"{flow_name} failed")
    data = result.get("data") or {}
    if not isinstance(data, dict):
        data = {"result": data}
    data.setdefault("execution_envelope", to_envelope(
        eu_id=result.get("run_id"), trace_id=result.get("trace_id"),
        status=str(result.get("status") or "UNKNOWN").upper(),
        output=None, error=result.get("error"), duration_ms=None, attempt_count=None,
    ))
    return data


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
    user_id = next((sig.user_id for sig in batch.signals if sig.user_id), None)

    def handler(ctx):
        for idx, sig in enumerate(batch.signals):
            _validate_signal(sig, idx)
        result = execute_intent(
            intent_data={
                "workflow_type": "watcher_ingest",
                "signals": [sig.model_dump() for sig in batch.signals],
                "user_id": user_id,
            },
            db=db,
            user_id=user_id,
        )
        if result.get("status") == "FAILED":
            error = result.get("error", "")
            if error.startswith("HTTP_"):
                parts = error.split(":", 1)
                code = int(parts[0].replace("HTTP_", ""))
                msg = parts[1] if len(parts) > 1 else error
                raise HTTPException(status_code=code, detail=msg)
            raise HTTPException(status_code=500, detail=error or "watcher_ingest failed")
        payload = result.get("result") or result.get("data") or {}
        if not isinstance(payload, dict):
            payload = {"result": payload}
        payload.setdefault("execution_envelope", to_envelope(
            eu_id=result.get("run_id"), trace_id=result.get("trace_id"),
            status=str(result.get("status") or "UNKNOWN").upper(),
            output=None, error=result.get("error"), duration_ms=None, attempt_count=None,
        ))
        return payload

    return execute_with_pipeline_sync(
        request=None,
        route_name="watcher.signals.receive",
        handler=handler,
        user_id=user_id,
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
    """Query stored watcher signals."""
    def handler(ctx):
        from domain.watcher_service import list_signals as svc_list_signals
        rows = svc_list_signals(
            db,
            session_id=session_id,
            signal_type=signal_type,
            user_id=user_id,
            limit=limit,
            offset=offset,
        )
        return {
            "signals": rows,
            "count": len(rows),
            "execution_envelope": to_envelope(
                eu_id=None, trace_id=None, status="SUCCESS",
                output=None, error=None, duration_ms=None, attempt_count=1,
            ),
        }

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

