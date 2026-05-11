"""Automation app ORM models."""

from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from AINDY.db.database import Base
from apps.automation.automation_log import AutomationLog
from apps.automation.bridge_user_event import BridgeUserEvent
from apps.automation.infinity_loop import LoopAdjustment, UserFeedback


class LearningRecordDB(Base):
    __tablename__ = "learning_records"

    id = Column(String, primary_key=True)
    drop_point_id = Column(String, index=True)

    prediction = Column(String)
    predicted_at = Column(DateTime)

    actual_outcome = Column(String, nullable=True)
    evaluated_at = Column(DateTime, nullable=True)

    velocity_at_prediction = Column(Float)
    narrative_at_prediction = Column(Float)

    was_correct = Column(Boolean, nullable=True)


class LearningThresholdDB(Base):
    __tablename__ = "learning_thresholds"

    id = Column(String, primary_key=True)
    velocity_trend = Column(Float, nullable=False)
    narrative_trend = Column(Float, nullable=False)
    early_velocity_rate = Column(Float, nullable=False)
    early_narrative_ceiling = Column(Float, nullable=False)
    last_updated = Column(DateTime, nullable=False, default=datetime.utcnow)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class WatcherSignal(Base):
    __tablename__ = "watcher_signals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    signal_type = Column(String(64), nullable=False, index=True)
    session_id = Column(String(64), nullable=False, index=True)
    app_name = Column(String(255), nullable=False)
    window_title = Column(Text, nullable=True)
    activity_type = Column(String(32), nullable=False)
    signal_timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    received_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    duration_seconds = Column(Float, nullable=True)
    focus_score = Column(Float, nullable=True)
    signal_metadata = Column(JSONB, nullable=True)

    __table_args__ = (
        Index("ix_watcher_signals_session_type", "session_id", "signal_type"),
        Index("ix_watcher_signals_received_at", "received_at"),
    )


__all__ = [
    "AutomationLog",
    "BridgeUserEvent",
    "LearningRecordDB",
    "LearningThresholdDB",
    "LoopAdjustment",
    "UserFeedback",
    "WatcherSignal",
]


def register_models() -> None:
    return None
