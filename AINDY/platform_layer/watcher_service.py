from __future__ import annotations

import logging
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

logger = logging.getLogger(__name__)


def list_signals(
    db: Session,
    *,
    session_id: str | None = None,
    signal_type: str | None = None,
    user_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    """
    Query stored watcher signals with optional filters.

    Validates signal_type and user_id before querying.
    Raises HTTPException on invalid inputs.
    """
    from AINDY.kernel.syscall_dispatcher import SyscallContext, get_dispatcher

    if signal_type and signal_type not in _VALID_SIGNAL_TYPES:
        raise HTTPException(status_code=422, detail=f"Unknown signal_type: {signal_type!r}")

    if user_id:
        try:
            UUID(str(user_id))
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"Invalid user_id: {user_id!r}") from exc

    dispatcher = get_dispatcher()
    ctx = SyscallContext(
        user_id=user_id or "",
        trace_id="",
        execution_unit_id="",
        capabilities=["watcher.query"],
        metadata={"_db": db},
    )
    result = dispatcher.dispatch(
        "sys.v1.watcher.query",
        {
            "user_id": user_id,
            "session_id": session_id,
            "signal_type": signal_type,
            "limit": limit,
            "offset": offset,
        },
        ctx,
    )
    if result["status"] != "success":
        logger.warning(
            "watcher.query syscall failed for user_id=%s session_id=%s signal_type=%s: %s",
            user_id,
            session_id,
            signal_type,
            result.get("error"),
        )
        return {"signals": [], "total": 0}
    data = result.get("data") or {}
    return {
        "signals": list(data.get("signals") or []),
        "total": int(data.get("total") or 0),
    }
