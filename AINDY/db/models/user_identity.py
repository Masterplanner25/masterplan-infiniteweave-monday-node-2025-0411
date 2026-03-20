"""
User Identity Model — v5 Phase 2

Tracks user preferences, behavior patterns, and evolution.
One record per user. Updated incrementally as A.I.N.D.Y.
observes patterns across all workflows.
"""
import uuid
from sqlalchemy import (
    Column,
    String,
    Text,
    Integer,
    DateTime,
    JSON,
    ForeignKey,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from db.database import Base

VALID_TONES = {"formal", "casual", "concise", "detailed", "technical"}
VALID_RISK_TOLERANCE = {"conservative", "moderate", "aggressive"}
VALID_SPEED_VS_QUALITY = {"speed", "balanced", "quality"}
VALID_LEARNING_STYLES = {"examples", "theory", "mixed"}
VALID_DETAIL_PREFERENCES = {"step_by_step", "high_level", "mixed"}


class UserIdentity(Base):
    __tablename__ = "user_identity"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_user_identity_user"),
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
        unique=True,
        index=True,
    )

    # Dimension 1: Communication
    tone = Column(String, nullable=True)
    communication_notes = Column(Text, nullable=True)

    # Dimension 2: Tools and languages
    preferred_languages = Column(JSON, default=list)
    preferred_tools = Column(JSON, default=list)
    avoided_tools = Column(JSON, default=list)

    # Dimension 3: Decision-making
    risk_tolerance = Column(String, nullable=True)
    speed_vs_quality = Column(String, nullable=True)
    decision_notes = Column(Text, nullable=True)

    # Dimension 4: Learning style
    learning_style = Column(String, nullable=True)
    detail_preference = Column(String, nullable=True)
    learning_notes = Column(Text, nullable=True)

    # Evolution
    observation_count = Column(Integer, default=0)
    last_updated = Column(DateTime(timezone=True), nullable=True)
    evolution_log = Column(JSON, default=list)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
