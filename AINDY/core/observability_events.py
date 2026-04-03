"""
core/observability_events.py — DB-backed observability event emission.

Writes a SystemEvent row so dashboards and v1 contract gates can observe
key operation lifecycle points.  All imports and DB access are deferred
to call time so this module is safe to import before the DB is ready.

Never raises — any failure is logged as a warning and execution continues.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def emit_observability_event(
    *,
    event_type: str,
    user_id: str | None = None,
    payload: dict[str, Any] | None = None,
    source: str = "observability",
) -> None:
    """
    Write a SystemEvent row for the given event_type.

    Parameters
    ----------
    event_type:  SystemEventTypes constant string (e.g. "genesis.message.started").
    user_id:     Owner of the operation — string UUID or None.
    payload:     Arbitrary context dict persisted alongside the event.
    source:      Subsystem label stored on the SystemEvent row.
    """
    try:
        # Lazy imports so this module is importable before DB initialises.
        # db.database.SessionLocal is patched to the test session factory
        # during tests, so this picks up the correct session automatically.
        from db.database import SessionLocal
        from core.execution_signal_helper import queue_system_event

        db = SessionLocal()
        try:
            queue_system_event(
                db=db,
                event_type=event_type,
                user_id=user_id,
                source=source,
                payload=payload or {},
                required=False,
            )
        finally:
            db.close()
    except Exception as exc:
        logger.warning(
            "[observability] emit_observability_event failed for %r: %s",
            event_type,
            exc,
        )
