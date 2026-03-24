from datetime import datetime

from sqlalchemy import Column, String, Float, DateTime
from db.database import Base


class LearningThresholdDB(Base):
    __tablename__ = "learning_thresholds"

    id = Column(String, primary_key=True)
    velocity_trend = Column(Float, nullable=False)
    narrative_trend = Column(Float, nullable=False)
    early_velocity_rate = Column(Float, nullable=False)
    early_narrative_ceiling = Column(Float, nullable=False)
    last_updated = Column(DateTime, nullable=False, default=datetime.utcnow)
