from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Integer, String

from db.database import Base


class MemoryMetric(Base):
    __tablename__ = "memory_metrics"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, nullable=False, index=True)
    task_type = Column(String, nullable=True, index=True)
    impact_score = Column(Float, nullable=False, default=0.0)
    memory_count = Column(Integer, nullable=False, default=0)
    avg_similarity = Column(Float, nullable=False, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
