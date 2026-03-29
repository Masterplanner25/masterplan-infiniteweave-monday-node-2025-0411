import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, String
from sqlalchemy.dialects.postgresql import JSONB, UUID

from db.database import Base


class AgentRegistry(Base):
    __tablename__ = "agent_registry"

    agent_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    capabilities = Column(JSONB, nullable=False, default=list)
    current_state = Column(JSONB, nullable=False, default=dict)
    load = Column(Float, nullable=False, default=0.0, index=True)
    health_status = Column(String(32), nullable=False, default="healthy", index=True)
    last_seen = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
