# db/models/research_results.py

from sqlalchemy import Column, Integer, String, Text, DateTime, func
from sqlalchemy.dialects.postgresql import JSON
from db.database import Base

# ✅ SQLAlchemy Model
class ResearchResult(Base):
    __tablename__ = "research_results"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True)
    query = Column(String, nullable=False)
    summary = Column(Text, nullable=True)
    source = Column(String, nullable=True)
    data = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=func.now())
