"""Explicit service-layer sync from JobLog to AutomationLog."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_JOB_LOG_FIELDS = {
    "id",
    "source",
    "task_name",
    "payload",
    "status",
    "attempt_count",
    "max_attempts",
    "error_message",
    "user_id",
    "result",
    "trace_id",
    "started_at",
    "completed_at",
    "created_at",
    "scheduled_for",
}


def sync_job_log_to_automation_log(db, job_log_row) -> None:
    """Upsert AutomationLog from a JobLog instance. Never raises."""
    try:
        from apps.automation.automation_log import AutomationLog

        table = AutomationLog.__table__
        table_cols = {c.name for c in table.columns}

        raw_values: dict = {}
        for field in _JOB_LOG_FIELDS:
            if field == "task_name":
                val = getattr(job_log_row, "job_name", None) or getattr(job_log_row, "task_name", None)
            else:
                val = getattr(job_log_row, field, None)
            if val is not None or field in table_cols:
                raw_values[field] = val

        values = {k: v for k, v in raw_values.items() if k in table_cols}

        if not values.get("id"):
            return

        row_id = str(values["id"])
        existing = db.query(AutomationLog).filter(AutomationLog.id == row_id).first()
        if existing:
            for k, v in values.items():
                if k != "id":
                    setattr(existing, k, v)
            db.add(existing)
        else:
            values["id"] = row_id
            db.add(AutomationLog(**values))
        db.commit()
    except Exception as exc:
        logger.warning("[JobLogSync] Failed to sync job_log %s to automation_log: %s", getattr(job_log_row, "id", "?"), exc)
        try:
            db.rollback()
        except Exception:
            pass
