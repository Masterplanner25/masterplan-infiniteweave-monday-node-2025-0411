from sqlalchemy import Column, DateTime, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid

from db.database import Base


class BackgroundTaskLease(Base):
    __tablename__ = "background_task_leases"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False, unique=True, index=True)
    owner_id = Column(String, nullable=False, index=True)
    acquired_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    heartbeat_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
