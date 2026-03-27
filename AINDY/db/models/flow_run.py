"""
FlowRun — persistent execution state.

Every workflow execution creates a FlowRun.
State is checkpointed to DB after each node.
WAIT states persist until the event arrives.
Failed runs can be inspected and retried.
"""
import uuid

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from db.database import Base


class FlowRun(Base):
    __tablename__ = "flow_runs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    flow_name = Column(String, nullable=False, index=True)
    workflow_type = Column(String, nullable=True)
    state = Column(JSON, nullable=False, default=dict)
    current_node = Column(String, nullable=True)
    status = Column(String, nullable=False, default="running")
    waiting_for = Column(String, nullable=True)
    trace_id = Column(String, nullable=True, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    automation_log_id = Column(
        String,
        ForeignKey("automation_logs.id"),
        nullable=True,
    )
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
    completed_at = Column(DateTime(timezone=True), nullable=True)


class FlowHistory(Base):
    __tablename__ = "flow_history"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    flow_run_id = Column(
        String,
        ForeignKey("flow_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    node_name = Column(String, nullable=False)
    status = Column(String, nullable=False)
    input_state = Column(JSON, nullable=True)
    output_patch = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    execution_time_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class EventOutcome(Base):
    __tablename__ = "event_outcomes"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    event_type = Column(String, nullable=False, index=True)
    flow_name = Column(String, nullable=False)
    workflow_type = Column(String, nullable=True)
    success = Column(Boolean, nullable=False)
    execution_time_ms = Column(Integer, nullable=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    event_metadata = Column("metadata", JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Strategy(Base):
    __tablename__ = "strategies"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    intent_type = Column(String, nullable=False, index=True)
    flow = Column(JSON, nullable=False)
    score = Column(Float, nullable=False, default=1.0)
    usage_count = Column(Integer, default=0)
    success_count = Column(Integer, default=0)
    failure_count = Column(Integer, default=0)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())
