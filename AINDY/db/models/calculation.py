from sqlalchemy import Column, Integer, String, Float, DateTime
from sqlalchemy.sql import func
from db.database import Base


class CalculationResult(Base):
    """SQLAlchemy model for storing calculated metric results."""

    __tablename__ = "calculation_results"

    id = Column(Integer, primary_key=True, index=True)
    metric_name = Column(String, index=True)
    result_value = Column(Float)
    user_id = Column(String, nullable=True, index=True)
    created_at = Column(DateTime, default=func.now())

    
