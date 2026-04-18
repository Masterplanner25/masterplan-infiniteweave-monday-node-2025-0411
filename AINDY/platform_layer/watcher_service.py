from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

_VALID_SIGNAL_TYPES = {
    "app_focus",
    "app_switch",
    "session_started",
    "session_ended",
    "distraction_detected",
    "idle_detected",
}


def list_signals(
    db: Session,
    *,
    session_id: str | None = None,
    signal_type: str | None = None,
    user_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """
    Query stored watcher signals with optional filters.

    Validates signal_type and user_id before querying.
    Raises HTTPException on invalid inputs.
    """
    from AINDY.db.models.watcher_signal import WatcherSignal

    if signal_type and signal_type not in _VALID_SIGNAL_TYPES:
        raise HTTPException(status_code=422, detail=f"Unknown signal_type: {signal_type!r}")

    parsed_user_id: UUID | None = None
    if user_id:
        try:
            parsed_user_id = UUID(str(user_id))
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"Invalid user_id: {user_id!r}") from exc

    query = db.query(WatcherSignal)
    if session_id:
        query = query.filter(WatcherSignal.session_id == session_id)
    if signal_type:
        query = query.filter(WatcherSignal.signal_type == signal_type)
    if parsed_user_id is not None:
        query = query.filter(WatcherSignal.user_id == parsed_user_id)

    signals = (
        query.order_by(WatcherSignal.signal_timestamp.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return [
        {
            "id": s.id,
            "signal_type": s.signal_type,
            "session_id": s.session_id,
            "app_name": s.app_name,
            "window_title": s.window_title,
            "activity_type": s.activity_type,
            "signal_timestamp": s.signal_timestamp.isoformat(),
            "received_at": s.received_at.isoformat(),
            "duration_seconds": s.duration_seconds,
            "focus_score": s.focus_score,
            "metadata": s.signal_metadata,
        }
        for s in signals
    ]
