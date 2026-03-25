"""
AgentEventService — thin helper for emitting lifecycle events (Sprint N+8).

emit_event() is the single entry point. It is always non-fatal:
  - Wrapped in try/except
  - Logs failures at WARNING level
  - Never raises to caller
  - Caller does not need to handle any return value

Usage:
    from services.agent_event_service import emit_event
    emit_event(
        run_id=str(run.id),
        user_id=run.user_id,
        correlation_id=run.correlation_id,
        event_type="PLAN_CREATED",
        payload={"overall_risk": "low", "steps_total": 3},
        db=db,
    )
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def emit_event(
    run_id: str,
    user_id: str,
    event_type: str,
    db: Session,
    correlation_id: Optional[str] = None,
    payload: Optional[dict] = None,
) -> None:
    """
    Persist one AgentEvent lifecycle row.

    Always non-fatal — exceptions are caught, logged, and swallowed.
    Never raises to caller.

    Args:
        run_id:         UUID string of the AgentRun
        user_id:        Owner user ID
        event_type:     One of AGENT_EVENT_TYPES (PLAN_CREATED, APPROVED, etc.)
        db:             SQLAlchemy session
        correlation_id: Optional run_<uuid4> token (None for pre-N+8 runs)
        payload:        Optional dict of event-specific data
    """
    try:
        from db.models.agent_event import AgentEvent
        import uuid

        event = AgentEvent(
            id=uuid.uuid4(),
            run_id=uuid.UUID(run_id) if isinstance(run_id, str) else run_id,
            correlation_id=correlation_id,
            user_id=user_id,
            event_type=event_type,
            payload=payload or {},
            occurred_at=datetime.now(timezone.utc),
        )
        db.add(event)
        db.commit()

        logger.debug(
            "[AgentEventService] Emitted %s for run %s (correlation=%s)",
            event_type,
            run_id,
            correlation_id,
        )

    except Exception as exc:
        logger.warning(
            "[AgentEventService] Failed to emit %s for run %s: %s",
            event_type,
            run_id,
            exc,
        )
