from sqlalchemy import Column, DateTime, JSON, String, func
from sqlalchemy.dialects.postgresql import UUID

from AINDY.db.database import Base


class SearchHistory(Base):
    __tablename__ = "search_history"

    id = Column(String, primary_key=True, index=True)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    query = Column(String, nullable=False, index=True)
    result = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
