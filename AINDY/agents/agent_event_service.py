"""
AgentEventService — thin helper for emitting lifecycle events (Sprint N+8).

emit_event() is the single entry point for agent lifecycle persistence.
Critical execution paths pass required=True so missing audit events fail closed.

Usage:
    from AINDY.agents.agent_event_service import emit_event
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
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from AINDY.core.execution_signal_helper import queue_system_event
from AINDY.core.system_event_service import SystemEventEmissionError
from AINDY.utils.trace_context import get_parent_event_id
from AINDY.utils.trace_context import get_trace_id
from AINDY.utils.uuid_utils import normalize_uuid

logger = logging.getLogger(__name__)

AGENT_EVENT_TYPES = {
    "PLAN_CREATED",
    "APPROVED",
    "REJECTED",
    "EXECUTION_STARTED",
    "COMPLETED",
    "EXECUTION_FAILED",
    "CAPABILITY_DENIED",
    "RECOVERED",
    "REPLAY_CREATED",
}


def emit_event(
    run_id: str,
    user_id: str,
    event_type: str,
    db: Session,
    correlation_id: Optional[str] = None,
    payload: Optional[dict] = None,
    required: bool = False,
) -> str | None:
    """
    Persist one AgentEvent lifecycle row.

    Raises when required=True and either the AgentEvent row or matching
    SystemEvent cannot be persisted.

    Args:
        run_id:         UUID string of the AgentRun
        user_id:        Owner user ID
        event_type:     One of AGENT_EVENT_TYPES (PLAN_CREATED, APPROVED, etc.)
        db:             SQLAlchemy session
        correlation_id: Optional run_<uuid4> token (None for pre-N+8 runs)
        payload:        Optional dict of event-specific data
    """
    try:
        from AINDY.db.models.agent_event import AgentEvent

        if event_type not in AGENT_EVENT_TYPES:
            logger.warning(
                "[AgentEventService] Unknown event type %s for run %s",
                event_type,
                run_id,
            )

        parsed_run_id = run_id
        if isinstance(run_id, str):
            try:
                parsed_run_id = uuid.UUID(run_id)
            except ValueError:
                parsed_run_id = run_id

        normalized_user_id = normalize_uuid(user_id) if user_id is not None else None

        system_event_id = queue_system_event(
            db=db,
            event_type=f"agent.{str(event_type).lower()}",
            user_id=user_id,
            trace_id=get_trace_id() or correlation_id or run_id,
            parent_event_id=get_parent_event_id(),
            source="agent",
            payload={
                "run_id": run_id,
                "correlation_id": correlation_id,
                "event_type": event_type,
                **(payload or {}),
            },
            required=required,
        )

        normalized_system_event_id = (
            normalize_uuid(system_event_id) if system_event_id else None
        )

        event = AgentEvent(
            id=uuid.uuid4(),
            run_id=parsed_run_id,
            correlation_id=correlation_id,
            user_id=normalized_user_id,
            event_type=event_type,
            payload=payload or {},
            system_event_id=normalized_system_event_id,
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
        return str(system_event_id) if system_event_id else None

    except Exception as exc:
        logger.warning(
            "[AgentEventService] Failed to emit %s for run %s: %s",
            event_type,
            run_id,
            exc,
        )
        if required:
            raise SystemEventEmissionError(
                f"Required agent event '{event_type}' failed for run {run_id}"
            ) from exc
        return None

