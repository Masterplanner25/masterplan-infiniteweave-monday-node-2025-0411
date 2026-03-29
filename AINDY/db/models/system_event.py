import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB, UUID

from db.database import Base


class SystemEvent(Base):
    __tablename__ = "system_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    type = Column(String(64), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agent_registry.agent_id"), nullable=True, index=True)
    trace_id = Column(String(128), nullable=True, index=True)
    parent_event_id = Column(UUID(as_uuid=True), ForeignKey("system_events.id"), nullable=True, index=True)
    source = Column(String(32), nullable=True, index=True)
    payload = Column(JSONB, nullable=True)
    timestamp = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    __table_args__ = (
        Index("ix_system_events_user_id_timestamp", "user_id", "timestamp"),
        Index("ix_system_events_agent_id_timestamp", "agent_id", "timestamp"),
        Index("ix_system_events_trace_id_timestamp", "trace_id", "timestamp"),
        Index("ix_system_events_parent_event_id_timestamp", "parent_event_id", "timestamp"),
    )
