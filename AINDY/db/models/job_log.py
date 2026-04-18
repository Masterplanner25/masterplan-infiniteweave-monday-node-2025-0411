import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID

from AINDY.db.database import Base


class JobLog(Base):
    __tablename__ = "job_logs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    source = Column(String, nullable=False)
    job_name = Column(String, nullable=True)
    payload = Column(JSON, nullable=True)
    status = Column(String, nullable=False, default="pending")
    attempt_count = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=3)
    error_message = Column(Text, nullable=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    result = Column(JSON, nullable=True)
    trace_id = Column(String, nullable=True, index=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    scheduled_for = Column(DateTime(timezone=True), nullable=True)

    @property
    def task_name(self) -> str | None:
        return self.job_name

    @task_name.setter
    def task_name(self, value: str | None) -> None:
        self.job_name = value
