import os

from sqlalchemy import Column, DateTime, String

from AINDY.db.database import Base, utcnow


class WaitingFlowRun(Base):
    __tablename__ = "waiting_flow_runs"

    run_id = Column(String(64), primary_key=True)
    event_type = Column(String(128), nullable=False, index=True)
    correlation_id = Column(String(128), nullable=True, index=True)
    registered_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    timeout_at = Column(DateTime(timezone=True), nullable=True, index=True)
    eu_id = Column(String(64), nullable=True)
    priority = Column(String(16), nullable=False, default="normal")
    instance_id = Column(String(64), nullable=True, default=lambda: os.getenv("HOSTNAME", "local"))
