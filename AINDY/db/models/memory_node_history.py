"""
Memory Node History -- append-only change log.

Records the PREVIOUS state of a MemoryNode before an explicit update.
Never deleted. Never mutated.

Triggers: explicit calls to MemoryNodeDAO.update()
Does NOT trigger: initial creation, embedding updates,
                  resonance score calculations
"""
from sqlalchemy import Column, String, Text, DateTime, JSON, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from AINDY.db.database import Base
import uuid


class MemoryNodeHistory(Base):
    __tablename__ = "memory_node_history"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    node_id = Column(
        UUID(as_uuid=True),
        ForeignKey("memory_nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    changed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    changed_by = Column(String, nullable=True)

    # Previous values (what it was before the change)
    previous_content = Column(Text, nullable=True)
    previous_tags = Column(JSON, nullable=True)
    previous_node_type = Column(String, nullable=True)
    previous_source = Column(String, nullable=True)

    # Change metadata
    change_type = Column(String, nullable=False)
    change_summary = Column(Text, nullable=True)

    __table_args__ = (
        Index("ix_memory_node_history_node_changed", "node_id", "changed_at"),
    )
