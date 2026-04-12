from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID

from AINDY.db.database import Base


class StrategyDB(Base):
    __tablename__ = "strategies"
    __table_args__ = {"extend_existing": True}

    id = Column(String, primary_key=True)

    # Legacy RippleTrace strategy fields
    name = Column(String, nullable=True)
    pattern_description = Column(Text, nullable=True)
    conditions = Column(Text, nullable=True)
    success_rate = Column(Float, nullable=True)

    # Flow Engine strategy-learning fields
    intent_type = Column(String, nullable=True)
    flow = Column(JSON, nullable=True)
    score = Column(Float, nullable=False, default=1.0)
    success_count = Column(Integer, nullable=False, default=0)
    failure_count = Column(Integer, nullable=False, default=0)
    user_id = Column(UUID(as_uuid=True), nullable=True)

    usage_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)
