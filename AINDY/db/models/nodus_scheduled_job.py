"""
db/models/nodus_scheduled_job.py — Persisted scheduled Nodus script executions.

Each row represents one cron-scheduled Nodus job registered via
POST /platform/nodus/schedule.  On server startup the nodus_schedule_service
reads all active rows and re-registers each one with APScheduler so schedules
survive restarts.

Design choices
==============
* ``script`` (Text) always holds the inline source — even when the job was
  created from a named upload, the content is copied at creation time so the
  job is self-contained and independent of the script registry.
* ``script_name`` is kept for informational/audit purposes only.
* Deletion is soft (``is_active=False``) so history is preserved and the last
  run metadata remains queryable.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID

from AINDY.db.database import Base


class NodusScheduledJob(Base):
    __tablename__ = "nodus_scheduled_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Owner — used for memory scoping and event attribution inside the script
    user_id = Column(UUID(as_uuid=True), nullable=True, index=True)

    # Human-readable label (optional — defaults to "nodus_job_{id}" at runtime)
    job_name = Column(String(256), nullable=True)

    # Script source — always populated at creation time (even for named scripts)
    script = Column(Text, nullable=False)

    # Name of the uploaded script this job was created from (informational only)
    script_name = Column(String(128), nullable=True)

    # Standard 5-field cron expression: "MIN HOUR DOM MON DOW"
    # Example: "0 10 * * 1-5"  — every weekday at 10:00 UTC
    cron_expression = Column(String(128), nullable=False)

    # Passed as nodus_input_payload to the script on each execution
    input_payload = Column(JSON, nullable=True)

    # "fail"  — script error ends the run immediately (default)
    # "retry" — flow engine retries the nodus.execute node up to max_retries times
    error_policy = Column(String(16), nullable=False, default="fail")
    max_retries = Column(Integer, nullable=False, default=3)

    # Lifecycle
    is_active = Column(Boolean, nullable=False, default=True, index=True)

    # Last execution metadata (updated after every run)
    last_run_at = Column(DateTime(timezone=True), nullable=True)
    last_run_status = Column(String(16), nullable=True)   # "success" | "failure" | "error"
    last_run_log_id = Column(String(256), nullable=True)   # AutomationLog.id

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
