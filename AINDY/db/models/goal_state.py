import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB, UUID

from db.database import Base


class GoalState(Base):
    __tablename__ = "goal_states"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    goal_id = Column(UUID(as_uuid=True), ForeignKey("goals.id"), nullable=False, unique=True, index=True)
    progress = Column(Float, nullable=False, default=0.0)
    last_update = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
    recent_actions = Column(JSONB, nullable=False, default=list)
    success_signal = Column(Float, nullable=False, default=0.0)
