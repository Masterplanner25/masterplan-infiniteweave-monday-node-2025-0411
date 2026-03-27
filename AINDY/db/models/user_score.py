"""
UserScore + ScoreHistory — Infinity Algorithm scores.

UserScore: latest cached score per user (upserted on recalculation).
ScoreHistory: append-only time series of all score snapshots.

Master score = weighted average of 5 KPIs:
  execution_speed       × 0.25
  decision_efficiency   × 0.25
  ai_productivity_boost × 0.20
  focus_quality         × 0.15
  masterplan_progress   × 0.15

Each KPI is 0-100. Master score is 0-100.
"""
import uuid

from sqlalchemy import Column, String, Float, Integer, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from db.database import Base

# KPI weights — must sum to 1.0
KPI_WEIGHTS = {
    "execution_speed":       0.25,
    "decision_efficiency":   0.25,
    "ai_productivity_boost": 0.20,
    "focus_quality":         0.15,
    "masterplan_progress":   0.15,
}
assert abs(sum(KPI_WEIGHTS.values()) - 1.0) < 1e-9, \
    "KPI weights must sum to 1.0"


class UserScore(Base):
    __tablename__ = "user_scores"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, unique=True, index=True)

    master_score = Column(Float, default=0.0)
    execution_speed_score = Column(Float, default=0.0)
    decision_efficiency_score = Column(Float, default=0.0)
    ai_productivity_boost_score = Column(Float, default=0.0)
    focus_quality_score = Column(Float, default=0.0)
    masterplan_progress_score = Column(Float, default=0.0)

    score_version = Column(String, default="v1")
    data_points_used = Column(Integer, default=0)
    confidence = Column(String, nullable=True)
    trigger_event = Column(String, nullable=True)

    calculated_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())


class ScoreHistory(Base):
    __tablename__ = "score_history"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)

    master_score = Column(Float, nullable=False)
    execution_speed_score = Column(Float, nullable=False)
    decision_efficiency_score = Column(Float, nullable=False)
    ai_productivity_boost_score = Column(Float, nullable=False)
    focus_quality_score = Column(Float, nullable=False)
    masterplan_progress_score = Column(Float, nullable=False)

    trigger_event = Column(String, nullable=True)
    score_delta = Column(Float, nullable=True)

    calculated_at = Column(DateTime(timezone=True), server_default=func.now())
