from sqlalchemy import Column, String, DateTime, Float, Boolean
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
