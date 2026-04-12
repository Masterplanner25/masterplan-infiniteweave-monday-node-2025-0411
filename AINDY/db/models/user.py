"""
db/models/user.py — Persisted User model for A.I.N.D.Y. authentication.

Phase 3 replacement for the in-memory _USERS dict in auth_router.py.
"""
import uuid
from sqlalchemy import Boolean, Column, DateTime, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from AINDY.db.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, index=True, nullable=False)
    username = Column(String, unique=True, index=True, nullable=True)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    tasks = relationship("Task", back_populates="user", cascade="all, delete-orphan")
    api_keys = relationship("PlatformAPIKey", back_populates="user", cascade="all, delete-orphan")
