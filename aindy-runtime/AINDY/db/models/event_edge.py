import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, Column, DateTime, Float, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID

from AINDY.db.database import Base


class EventEdge(Base):
    __tablename__ = "event_edges"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_event_id = Column(
        UUID(as_uuid=True),
        ForeignKey("system_events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_event_id = Column(
        UUID(as_uuid=True),
        ForeignKey("system_events.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    target_memory_node_id = Column(
        UUID(as_uuid=True),
        ForeignKey("memory_nodes.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    relationship_type = Column(String(32), nullable=False, index=True)
    weight = Column(Float, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "(target_event_id IS NOT NULL) <> (target_memory_node_id IS NOT NULL)",
            name="ck_event_edges_single_target",
        ),
        Index("ix_event_edges_source_target", "source_event_id", "target_event_id"),
    )
