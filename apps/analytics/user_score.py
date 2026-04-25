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

from AINDY.db.database import Base

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

# Per-weight bounds. Prevents degenerate weights.
KPI_WEIGHT_MIN = 0.05
KPI_WEIGHT_MAX = 0.50
# Learning step: fraction of the weight to nudge per adaptation.
KPI_WEIGHT_LEARNING_RATE = 0.02
# Minimum evaluated adjustments before any adaptation runs.
KPI_WEIGHT_MIN_SAMPLES = 10


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
    lock_version = Column(Integer, nullable=False, default=1, server_default="1")

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


class UserKpiWeights(Base):
    """
    Per-user learned KPI weights.

    Starts at the global defaults, then adapts over time once enough
    evaluated loop adjustments exist for the user.
    """

    __tablename__ = "user_kpi_weights"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, unique=True, index=True)

    execution_speed_weight = Column(Float, nullable=False, default=0.25)
    decision_efficiency_weight = Column(Float, nullable=False, default=0.25)
    ai_productivity_boost_weight = Column(Float, nullable=False, default=0.20)
    focus_quality_weight = Column(Float, nullable=False, default=0.15)
    masterplan_progress_weight = Column(Float, nullable=False, default=0.15)

    adapted_count = Column(Integer, nullable=False, default=0)
    last_adapted_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())


class UserPolicyThresholds(Base):
    """
    Per-user adaptive Infinity loop thresholds and expected offsets.

    Low thresholds default to the historic hardcoded 40.0 behavior until
    enough history exists to personalize them for the user.
    """

    __tablename__ = "user_policy_thresholds"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, unique=True, index=True)

    execution_speed_low_threshold = Column(Float, nullable=False, default=40.0)
    decision_efficiency_low_threshold = Column(Float, nullable=False, default=40.0)
    ai_productivity_boost_low_threshold = Column(Float, nullable=False, default=40.0)
    focus_quality_low_threshold = Column(Float, nullable=False, default=40.0)
    masterplan_progress_low_threshold = Column(Float, nullable=False, default=40.0)

    offset_continue_highest_priority_task = Column(Float, nullable=False, default=3.0)
    offset_create_new_task = Column(Float, nullable=False, default=2.0)
    offset_reprioritize_tasks = Column(Float, nullable=False, default=1.5)
    offset_review_plan = Column(Float, nullable=False, default=1.0)

    adapted_count = Column(Integer, nullable=False, default=0)
    last_adapted_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())
