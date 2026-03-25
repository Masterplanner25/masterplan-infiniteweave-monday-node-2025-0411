"""
watcher_signal.py — ORM model for Watcher signal events.

Table: watcher_signals
Append-only. One row per signal emitted by the A.I.N.D.Y. Watcher process.
"""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB

from db.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class WatcherSignal(Base):
    __tablename__ = "watcher_signals"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # User association (nullable — watcher uses API-key auth; populated when known)
    user_id = Column(String, nullable=True, index=True)

    # Signal identity
    signal_type = Column(String(64), nullable=False, index=True)
    session_id = Column(String(64), nullable=False, index=True)

    # Source info
    app_name = Column(String(255), nullable=False)
    window_title = Column(Text, nullable=True)
    activity_type = Column(String(32), nullable=False)

    # Timing
    signal_timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    received_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

    # Optional numeric fields (populated for session_ended)
    duration_seconds = Column(Float, nullable=True)
    focus_score = Column(Float, nullable=True)

    # Structured extras (distraction category, context switch metadata, etc.)
    signal_metadata = Column(JSONB, nullable=True)

    __table_args__ = (
        Index("ix_watcher_signals_session_type", "session_id", "signal_type"),
        Index("ix_watcher_signals_received_at", "received_at"),
    )
