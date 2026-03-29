"""
AutomationLog — supervised task execution record.

Every background task, scheduled job, and webhook execution creates an
AutomationLog entry. This replaces silent daemon thread fire-and-forget
with auditable, retryable, supervised execution.

Status flow:
  pending → running → success
                    → failed (retryable: → retrying)
                    → failed (max attempts reached)
"""
import uuid
from sqlalchemy import Column, String, Integer, Text, DateTime, JSON, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from db.database import Base


class AutomationLog(Base):
    __tablename__ = "automation_logs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    source = Column(String, nullable=False)
    # e.g. "task_completion", "scheduled_job", "webhook", "background_task"
    task_name = Column(String, nullable=True)
    payload = Column(JSON, nullable=True)
    status = Column(String, nullable=False, default="pending")
    # Values: "pending" | "running" | "success" | "failed" | "retrying"
    attempt_count = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=3)
    error_message = Column(Text, nullable=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    result = Column(JSON, nullable=True)
    trace_id = Column(String, nullable=True, index=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    scheduled_for = Column(DateTime(timezone=True), nullable=True)
    # For scheduled jobs: when it was supposed to run
