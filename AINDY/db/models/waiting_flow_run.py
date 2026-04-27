import os

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.sql import func

from AINDY.db.database import Base, utcnow


class WaitingFlowRun(Base):
    __tablename__ = "waiting_flow_runs"
    __table_args__ = (
        Index("ix_waiting_flow_runs_correlation", "correlation_id"),
    )

    run_id = Column(
        String(64),
        ForeignKey("flow_runs.id", ondelete="CASCADE"),
        primary_key=True,
    )
    event_type = Column(String(128), nullable=False, index=True)
    correlation_id = Column(String(128), nullable=True)
    registered_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    waited_since = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        server_default=func.now(),
    )
    max_wait_seconds = Column(Integer, nullable=True, default=None)
    timeout_at = Column(DateTime(timezone=True), nullable=True, index=True)
    eu_id = Column(String(64), nullable=True)
    priority = Column(String(16), nullable=False, default="normal")
    instance_id = Column(String(64), nullable=True, default=lambda: os.getenv("HOSTNAME", "local"))
