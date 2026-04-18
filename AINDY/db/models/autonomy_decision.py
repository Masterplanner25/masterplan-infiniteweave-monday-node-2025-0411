import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from AINDY.db.database import Base


class AutonomyDecision(Base):
    __tablename__ = "autonomy_decisions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    trigger_type = Column(String(32), nullable=False, index=True)
    trigger_source = Column(String(64), nullable=True, index=True)
    decision = Column(String(16), nullable=False, index=True)
    priority = Column(Float, nullable=False, default=0.0)
    reason = Column(Text, nullable=False)
    trace_id = Column(String(128), nullable=True, index=True)
    job_log_id = Column(String, nullable=True, index=True)
    trigger_payload = Column(JSONB, nullable=True)
    context_summary = Column(JSONB, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    __table_args__ = (
        Index("ix_autonomy_decisions_user_created_at", "user_id", "created_at"),
        Index("ix_autonomy_decisions_trace_created_at", "trace_id", "created_at"),
    )
