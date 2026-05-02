"""
Runtime-owned lifecycle event log for agent runs.
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
    correlation_id = Column(String(72), nullable=True, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    event_type = Column(String(32), nullable=False, index=True)
    payload = Column(JSONB, nullable=True)
    system_event_id = Column(UUID(as_uuid=True), ForeignKey("system_events.id"), nullable=True, index=True)
    occurred_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_agent_events_run_id_occurred_at", "run_id", "occurred_at"),
        Index("ix_agent_events_user_id_occurred_at", "user_id", "occurred_at"),
    )
