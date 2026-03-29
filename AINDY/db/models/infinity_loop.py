import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

from db.database import Base


class UserFeedback(Base):
    __tablename__ = "user_feedback"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    source_type = Column(String, nullable=False)
    source_id = Column(String, nullable=True)
    feedback_value = Column(Integer, nullable=False)
    feedback_text = Column(String, nullable=True)
    loop_adjustment_id = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class LoopAdjustment(Base):
    __tablename__ = "loop_adjustments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    trace_id = Column(String, nullable=True, index=True)
    trigger_event = Column(String, nullable=False)
    score_snapshot = Column(JSONB, nullable=True)
    decision_type = Column(String, nullable=False)
    expected_outcome = Column(String, nullable=True)
    expected_score = Column(Integer, nullable=True)
    actual_outcome = Column(String, nullable=True)
    actual_score = Column(Integer, nullable=True)
    prediction_accuracy = Column(Integer, nullable=True)
    deviation_score = Column(Integer, nullable=True)
    adjustment_payload = Column(JSONB, nullable=True)
    applied_at = Column(DateTime(timezone=True), nullable=True)
    evaluated_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
