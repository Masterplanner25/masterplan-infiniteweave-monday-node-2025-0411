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
        from AINDY.db.database import SessionLocal
        from AINDY.core.execution_signal_helper import queue_system_event

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


def emit_error_event(
    *,
    event_type: str,
    user_id: str | None = None,
    payload: dict[str, Any] | None = None,
    source: str = "observability",
) -> None:
    """
    Backwards-compatible alias for emit_observability_event when routers log error states.
    """
    emit_observability_event(
        event_type=event_type,
        user_id=user_id,
        payload=payload,
        source=source,
    )


def emit_recovery_failure(
    recovery_type: str,
    exc: Exception,
    db,
    *,
    logger,
) -> None:
    """Emit best-effort monitoring signals for startup/background recovery failures."""
    try:
        from AINDY.platform_layer.metrics import startup_recovery_failure_total

        startup_recovery_failure_total.labels(recovery_type=recovery_type).inc()
    except Exception:
        pass

    event_payload = {
        "recovery_type": recovery_type,
        "error": str(exc),
        "error_class": type(exc).__name__,
    }

    target_db = db
    owns_db = False
    if target_db is None:
        try:
            from AINDY.db.database import SessionLocal

            target_db = SessionLocal()
            owns_db = True
        except Exception as inner:
            logger.warning(
                "[recovery] Could not open SystemEvent session for %s failure: %s",
                recovery_type,
                inner,
            )
            target_db = None

    if target_db is not None:
        try:
            try:
                target_db.rollback()
            except Exception:
                pass

            from AINDY.core.system_event_service import emit_error_event as persist_error_event
            from AINDY.core.system_event_types import SystemEventTypes

            persist_error_event(
                db=target_db,
                error_type=getattr(
                    SystemEventTypes,
                    "STARTUP_RECOVERY_FAILED",
                    "startup.recovery.failed",
                ),
                message=f"Startup recovery failed [{recovery_type}]: {exc}",
                payload=event_payload,
                source="startup_recovery",
                required=False,
            )
            target_db.commit()
        except Exception as inner:
            logger.warning(
                "[recovery] Could not emit SystemEvent for %s failure: %s",
                recovery_type,
                inner,
            )
            try:
                target_db.rollback()
            except Exception:
                pass
        finally:
            if owns_db:
                try:
                    target_db.close()
                except Exception:
                    pass

    logger.error(
        "[startup] Recovery scan FAILED [%s]: %s - stuck runs may exist. "
        "Check the SystemEvent table for recovery_type='%s'.",
        recovery_type,
        exc,
        recovery_type,
        exc_info=True,
    )
