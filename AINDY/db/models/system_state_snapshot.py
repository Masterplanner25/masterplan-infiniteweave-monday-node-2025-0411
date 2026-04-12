from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Integer, String
from sqlalchemy.dialects.postgresql import JSONB

from AINDY.db.database import Base


class SystemStateSnapshot(Base):
    __tablename__ = "system_state_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    active_runs = Column(Integer, nullable=False, default=0)
    failure_rate = Column(Float, nullable=False, default=0.0)
    avg_execution_time = Column(Float, nullable=False, default=0.0)
    recent_event_count = Column(Integer, nullable=False, default=0)
    system_load = Column(Float, nullable=False, default=0.0)
    dominant_event_types = Column(JSONB, nullable=False, default=list)
    health_status = Column(String(32), nullable=False, default="healthy", index=True)
    repeated_failures = Column(Integer, nullable=False, default=0)
    spike_detected = Column(Integer, nullable=False, default=0)
    unusual_patterns = Column(JSONB, nullable=False, default=list)
