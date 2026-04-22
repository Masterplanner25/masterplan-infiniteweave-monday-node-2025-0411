from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, String

from AINDY.db.database import Base


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
