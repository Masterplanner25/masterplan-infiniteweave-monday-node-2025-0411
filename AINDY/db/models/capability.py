"""
Capability models for agent execution policy.

Capability:
  Canonical capability catalogue with a risk level.

AgentCapabilityMapping:
  Maps a capability to either an agent_type or a specific AgentRun.
  At least one of agent_type / agent_run_id should be set by callers.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID

from db.database import Base


class Capability(Base):
    __tablename__ = "capabilities"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(64), nullable=False, unique=True, index=True)
    description = Column(Text, nullable=True)
    risk_level = Column(String(16), nullable=False, index=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class AgentCapabilityMapping(Base):
    __tablename__ = "agent_capability_mappings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    capability_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    agent_type = Column(String(64), nullable=True, index=True)
    agent_run_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        Index(
            "ix_agent_capability_mappings_agent_type_capability",
            "agent_type",
            "capability_id",
        ),
        Index(
            "ix_agent_capability_mappings_run_capability",
            "agent_run_id",
            "capability_id",
        ),
    )
