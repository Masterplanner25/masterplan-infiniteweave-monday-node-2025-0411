"""
Runtime-owned agent persistence models.

These models back the agent execution lifecycle as runtime infrastructure even
though agent routes, syscalls, and flows remain app-owned.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from AINDY.db.database import Base


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    agent_type = Column(String(64), nullable=False, default="default", index=True)
    flow_run_id = Column(
        String,
        ForeignKey("flow_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=False,
    )
    replayed_from_run_id = Column(String, nullable=True, index=False)
    correlation_id = Column(String(72), nullable=True, index=True)
    trace_id = Column(String(128), nullable=True, index=True)

    goal = Column(Text, nullable=False)
    plan = Column(JSONB, nullable=True)
    executive_summary = Column(Text, nullable=True)
    overall_risk = Column(String(16), nullable=True)

    status = Column(String(32), nullable=False, default="pending_approval")
    steps_total = Column(Integer, default=0)
    steps_completed = Column(Integer, default=0)
    current_step = Column(Integer, default=0)

    result = Column(JSONB, nullable=True)
    error_message = Column(Text, nullable=True)

    execution_token = Column(String(128), nullable=True)
    capability_token = Column(JSONB, nullable=True)

    parent_run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agent_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    spawned_by_agent_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agent_registry.agent_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    coordination_role = Column(String(16), nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    approved_at = Column(DateTime(timezone=True), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_agent_runs_user_status", "user_id", "status"),
        Index("ix_agent_runs_created_at", "created_at"),
        Index("ix_agent_runs_parent_run_id", "parent_run_id"),
    )

    @property
    def objective(self):
        return self.goal

    @objective.setter
    def objective(self, value):
        self.goal = value


class AgentStep(Base):
    __tablename__ = "agent_steps"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agent_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    step_index = Column(Integer, nullable=False)

    tool_name = Column(String(64), nullable=False)
    tool_args = Column(JSONB, nullable=True)
    risk_level = Column(String(16), nullable=True)
    description = Column(Text, nullable=True)

    status = Column(String(16), nullable=True)
    result = Column(JSONB, nullable=True)
    error_message = Column(Text, nullable=True)
    execution_ms = Column(Integer, nullable=True)

    executed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    correlation_id = Column(String(72), nullable=True, index=True)


class AgentTrustSettings(Base):
    __tablename__ = "agent_trust_settings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, unique=True, index=True)

    auto_execute_low = Column(Boolean, default=False, nullable=False)
    auto_execute_medium = Column(Boolean, default=False, nullable=False)
    allowed_auto_grant_tools = Column(JSONB, nullable=True)

    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
