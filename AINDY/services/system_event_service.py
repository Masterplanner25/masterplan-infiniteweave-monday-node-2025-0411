from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from utils.trace_context import get_current_trace_id
from utils.user_ids import parse_user_id

logger = logging.getLogger(__name__)
_VERBOSE_SYSTEM_EVENT_LOGS = os.getenv("AINDY_DEBUG_SYSTEM_EVENTS", "false").lower() in {
    "1",
    "true",
    "yes",
}


class SystemEventEmissionError(RuntimeError):
    """Raised when required system event persistence fails."""


def _persist_system_event(
    *,
    db,
    event_type: str,
    user_id: str | uuid.UUID | None,
    trace_id: str | None,
    payload: Optional[dict[str, Any]],
 ) -> uuid.UUID:
    from db.models.system_event import SystemEvent

    event = SystemEvent(
        id=uuid.uuid4(),
        type=event_type,
        user_id=parse_user_id(user_id),
        trace_id=str(trace_id) if trace_id else None,
        payload=payload or {},
        timestamp=datetime.now(timezone.utc),
    )
    db.add(event)
    db.flush()
    event_id = event.id
    db.commit()
    return event_id


def emit_system_event(
    *,
    db,
    event_type: str,
    user_id: str | uuid.UUID | None = None,
    trace_id: str | None = None,
    payload: Optional[dict[str, Any]] = None,
    required: bool = False,
) -> None:
    """Durable system event emission; may raise when required=True."""
    effective_trace_id = trace_id or get_current_trace_id()
    logger_method = logger.info if _VERBOSE_SYSTEM_EVENT_LOGS else logger.debug
    logger_method(
        "[SystemEvent] Attempt %s trace=%s user=%s required=%s payload_keys=%s",
        event_type,
        effective_trace_id,
        user_id,
        required,
        sorted((payload or {}).keys()),
    )
    try:
        event_id = _persist_system_event(
            db=db,
            event_type=event_type,
            user_id=user_id,
            trace_id=effective_trace_id,
            payload=payload,
        )
        logger_method(
            "[SystemEvent] Persisted %s id=%s trace=%s user=%s",
            event_type,
            event_id,
            effective_trace_id,
            user_id,
        )
    except Exception as exc:
        logger.warning(
            "[SystemEvent] Failed to emit %s trace=%s user=%s: %s",
            event_type,
            effective_trace_id,
            user_id,
            exc,
        )
        if required:
            raise SystemEventEmissionError(
                f"Required system event '{event_type}' failed for trace {effective_trace_id}"
            ) from exc


def emit_error_event(
    *,
    db,
    error_type: str,
    message: str,
    user_id: str | uuid.UUID | None = None,
    trace_id: str | None = None,
    payload: Optional[dict[str, Any]] = None,
    required: bool = False,
) -> None:
    error_payload = {
        "message": message,
        **(payload or {}),
    }
    emit_system_event(
        db=db,
        event_type=f"error.{error_type}",
        user_id=user_id,
        trace_id=trace_id,
        payload=error_payload,
        required=required,
    )
