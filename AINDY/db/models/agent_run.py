"""
Agent Run models — Sprint N+4 Agentics Phase 1+2 / Sprint N+6 Deterministic Agent / Sprint N+7 Observability

AgentRun: persists one objective→plan→approve→execute lifecycle.
AgentStep: each tool call within a run (append-only audit log).
AgentTrustSettings: per-user opt-in autonomy flags.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    ForeignKey,
    Boolean,
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from AINDY.db.database import Base


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    agent_type = Column(String(64), nullable=False, default="default", index=True)

    # N+6: links to the FlowRun that executed this agent run (nullable for
    # backward-compatibility with runs created before the deterministic adapter)
    flow_run_id = Column(String, nullable=True, index=False)

    # N+7: records the original run_id when this run was created via /replay
    # (nullable — only set on replayed runs; absent on originals)
    replayed_from_run_id = Column(String, nullable=True, index=False)

    # N+8: correlation token propagated through all child records (AgentStep, AgentEvent)
    # Format: run_<uuid4> — generated at create_run() time
    # Nullable: pre-N+8 runs have no correlation_id
    correlation_id = Column(String(72), nullable=True, index=True)
    trace_id = Column(String(128), nullable=True, index=True)

    # Objective and plan. ``goal`` is the legacy storage column name.
    goal = Column(Text, nullable=False)
    plan = Column(JSONB, nullable=True)          # Full GPT-4o plan JSON
    executive_summary = Column(Text, nullable=True)
    overall_risk = Column(String(16), nullable=True)  # low | medium | high

    # Execution state
    status = Column(String(32), nullable=False, default="pending_approval")
    # pending_approval | approved | executing | completed | failed | rejected

    steps_total = Column(Integer, default=0)
    steps_completed = Column(Integer, default=0)
    current_step = Column(Integer, default=0)

    # Outcome
    result = Column(JSONB, nullable=True)
    error_message = Column(Text, nullable=True)

    # Sprint N+10: per-run scoped authority token minted at approval time.
    execution_token = Column(String(128), nullable=True)
    capability_token = Column(JSONB, nullable=True)

    # Timestamps
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
    run_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    step_index = Column(Integer, nullable=False)

    tool_name = Column(String(64), nullable=False)
    tool_args = Column(JSONB, nullable=True)
    risk_level = Column(String(16), nullable=True)   # low | medium | high
    description = Column(Text, nullable=True)

    # Execution result
    status = Column(String(16), nullable=True)       # success | failed | skipped
    result = Column(JSONB, nullable=True)
    error_message = Column(Text, nullable=True)
    execution_ms = Column(Integer, nullable=True)

    executed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # N+8: correlation token from the parent AgentRun
    # Nullable: pre-N+8 runs have no correlation_id
    correlation_id = Column(String(72), nullable=True, index=True)


class AgentTrustSettings(Base):
    """Per-user opt-in autonomy flags.

    Deprecated fallback:
    auto_execute_low    — run low-risk plans without approval
    auto_execute_medium — run medium-risk plans without approval

    Preferred policy:
    allowed_auto_grant_tools — explicit list of low/medium tools that may be
    auto-granted on auto-approved runs. App-registered restricted tools are
    structurally excluded.

    High risk ALWAYS requires approval regardless of these flags.
    """
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
