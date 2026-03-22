from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Integer, String
from sqlalchemy.dialects.postgresql import UUID

from db.database import Base


class RequestMetric(Base):
    __tablename__ = "request_metrics"

    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(String, nullable=True, index=True)
    user_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    method = Column(String, nullable=False)
    path = Column(String, nullable=False, index=True)
    status_code = Column(Integer, nullable=False)
    duration_ms = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
