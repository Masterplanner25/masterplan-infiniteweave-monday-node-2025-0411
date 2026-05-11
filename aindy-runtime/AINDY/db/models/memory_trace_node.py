from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from AINDY.db.database import Base


class MemoryTraceNode(Base):
    __tablename__ = "memory_trace_nodes"
    __table_args__ = (
        UniqueConstraint("trace_id", "position", name="uq_trace_position"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trace_id = Column(UUID(as_uuid=True), ForeignKey("memory_traces.id", ondelete="CASCADE"), nullable=False, index=True)
    node_id = Column(UUID(as_uuid=True), ForeignKey("memory_nodes.id", ondelete="CASCADE"), nullable=False, index=True)
    position = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
