from datetime import datetime

from sqlalchemy import Column, String, Text, Float, Integer, DateTime
from db.database import Base


class StrategyDB(Base):
    __tablename__ = "strategies"
    __table_args__ = {"extend_existing": True}

    id = Column(String, primary_key=True)
    name = Column(String)

    pattern_description = Column(Text)
    conditions = Column(Text)

    success_rate = Column(Float)
    usage_count = Column(Integer)

    created_at = Column(DateTime, default=datetime.utcnow)
