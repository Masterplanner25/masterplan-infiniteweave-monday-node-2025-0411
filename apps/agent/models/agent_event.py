"""
AgentEvent — structured lifecycle event log for agent runs (Sprint N+8).

One row per lifecycle transition. Step-level events (STEP_EXECUTED, STEP_FAILED)
are NOT stored here — those live in AgentStep. This table captures semantic
lifecycle events only.

Event types:
  PLAN_CREATED       — AgentRun created, plan generated
  APPROVED           — Human approval received
  REJECTED           — Human rejection received
  EXECUTION_STARTED  — Execution handed to NodusAgentAdapter
  COMPLETED          — All steps succeeded, run finalised
  EXECUTION_FAILED   — Run failed during execution
  CAPABILITY_DENIED  — Run blocked by scoped capability enforcement
  RECOVERED          — Stuck run recovered via /recover
  REPLAY_CREATED     — New run created via /replay

run_id now carries a DB-level FK to agent_runs so lifecycle events cannot outlive
their parent run. Nullable columns still allow graceful handling of pre-N+8
runs where applicable.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB, UUID

from AINDY.db.database import Base


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


class AgentEvent(Base):
    __tablename__ = "agent_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agent_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Propagated correlation token — format: run_<uuid4>
    # Nullable: pre-N+8 runs have no correlation_id
    correlation_id = Column(String(72), nullable=True, index=True)

    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)

    # One of AGENT_EVENT_TYPES
    event_type = Column(String(32), nullable=False, index=True)

    # Event-specific structured data
    payload = Column(JSONB, nullable=True)

    # Canonical ledger link back to SystemEvent
    system_event_id = Column(UUID(as_uuid=True), ForeignKey("system_events.id"), nullable=True, index=True)

    # When the event occurred (set by emitter, not server_default)
    occurred_at = Column(DateTime(timezone=True), nullable=False)

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        # Composite indexes for timeline queries
        Index("ix_agent_events_run_id_occurred_at", "run_id", "occurred_at"),
        Index("ix_agent_events_user_id_occurred_at", "user_id", "occurred_at"),
        # Single-column indexes for run_id, correlation_id, user_id, event_type
        # are created via index=True on each column above
    )
