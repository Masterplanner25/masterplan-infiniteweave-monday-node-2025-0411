from sqlalchemy import Column, Integer, String, Float, JSON, DateTime
from datetime import datetime
from db.database import Base

class SystemHealthLog(Base):
    __tablename__ = "system_health_logs"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    status = Column(String(50))
    components = Column(JSON)          # { "database": "connected", ... }
    api_endpoints = Column(JSON)       # { "calculate_twr": {...}, ... }
    avg_latency_ms = Column(Float)     # average latency across endpoints
