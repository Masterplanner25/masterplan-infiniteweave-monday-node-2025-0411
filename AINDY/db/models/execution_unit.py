"""
ExecutionUnit — unified execution abstraction for A.I.N.D.Y.

A single, queryable record for every execution event regardless of whether it
originated as a Task, AgentRun, FlowRun, or scheduled Job.

Design principles
-----------------
* Purely additive — no columns added to existing tables.
* Soft source link: source_type + source_id (string, no FK constraint) so the
  model works with both integer PKs (Task) and UUID PKs (AgentRun, FlowRun).
* parent_id enables nesting: e.g. the FlowRun EU spawned by an AgentRun EU has
  parent_id = agent_eu.id.
* memory_context_ids / output_memory_ids close the memory feedback loop —
  "what did this execution know going in, and what did it produce going out?"

Status machine
--------------
  pending → executing → waiting → completed
                                └→ failed
  (completed and failed are terminal — no outbound transitions)

Backward compatibility
----------------------
All existing records (Task, AgentRun, FlowRun) will have no corresponding EU
until an integration hook creates one.  The mappers in ExecutionUnitService
provide a view-only fallback that returns an EU-shaped dict from any existing
record without hitting the DB.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB, UUID

from db.database import Base


class ExecutionUnit(Base):
    __tablename__ = "execution_units"

    # ── Identity ───────────────────────────────────────────────────────────────
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # ── Type and status ────────────────────────────────────────────────────────
    type = Column(String(16), nullable=False, index=True)
    # "task" | "agent" | "flow" | "job"

    status = Column(String(16), nullable=False, default="pending", index=True)
    # "pending" | "executing" | "waiting" | "completed" | "failed"

    # ── Ownership ──────────────────────────────────────────────────────────────
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # ── Hierarchy ──────────────────────────────────────────────────────────────
    parent_id = Column(
        UUID(as_uuid=True),
        ForeignKey("execution_units.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # Set when this EU was spawned by another EU, e.g.:
    #   FlowRun EU started by AgentRun → parent_id = agent EU id

    # ── Source record link (soft, no FK — supports int PKs) ───────────────────
    source_type = Column(String(32), nullable=True)
    # "task" | "agent_run" | "flow_run" | "job"

    source_id = Column(String(128), nullable=True, index=True)
    # str(task.id) | str(agent_run.id) | str(flow_run.id)
    # String form chosen so integer-PK (Task) and UUID-PK (AgentRun) coexist.

    # ── Execution links ────────────────────────────────────────────────────────
    flow_run_id = Column(String(128), nullable=True, index=True)
    # The FlowRun that executed this unit (null until a flow is started for it).

    correlation_id = Column(String(72), nullable=True, index=True)
    # Shared token that groups related EUs in the same request/agent chain.
    # Matches AgentRun.correlation_id and AgentStep.correlation_id.

    # ── Memory ─────────────────────────────────────────────────────────────────
    memory_context_ids = Column(JSONB, nullable=True, default=list)
    # UUIDs (strings) of MemoryNodes recalled as context before execution.
    # Accumulated across all nodes in a flow run.

    output_memory_ids = Column(JSONB, nullable=True, default=list)
    # UUIDs (strings) of MemoryNodes produced as a result of this execution.

    # ── Extra ──────────────────────────────────────────────────────────────────
    extra = Column(JSONB, nullable=True)
    # Per-type metadata: workflow_type, goal_preview, task_name, etc.

    # ── Timestamps ─────────────────────────────────────────────────────────────
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
    completed_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        # Fast queries: all active executions for a user, by type
        Index("ix_eu_user_type_status", "user_id", "type", "status"),
        # Find EU from any originating record
        Index("ix_eu_source", "source_type", "source_id"),
        # Trace all EUs sharing a correlation chain
        Index("ix_eu_correlation", "correlation_id"),
    )
