"""
nodus_schedule_service.py — Scheduled Nodus script execution.

Allows cron-scheduled execution of Nodus scripts via the APScheduler
background scheduler.  Every execution is audited via AutomationLog and
run through PersistentFlowRunner so the full Nodus runtime
(memory, event, WAIT/RESUME, retries) is available to scripts.

Leader election
===============
Each APScheduler callback starts by calling ``is_background_leader()``
from task_services.  On multi-worker deployments only the instance that
holds the background task DB lease actually executes the job; all other
instances return immediately.  This matches the existing pattern used by
all other scheduled system jobs.

Retry handling
==============
* ``error_policy="retry"`` → the ``nodus.execute`` flow node returns RETRY
  on script failure, and PersistentFlowRunner retries up to ``max_retries``
  times (exponential back-off managed by the flow engine).
* ``error_policy="fail"`` (default) → script errors are recorded as
  ``last_run_status="failure"`` and the run ends immediately.
* Outer (infrastructure) exceptions (DB down, VM crash) are caught, logged,
  and recorded in the AutomationLog; they never propagate to APScheduler.

Persistence
===========
``create_nodus_scheduled_job()`` registers the job with APScheduler *and*
writes a ``NodusScheduledJob`` row to DB.  On server restart,
``restore_nodus_scheduled_jobs()`` reads all active rows and re-registers
them — call this from ``scheduler_service._register_system_jobs()``.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# APScheduler job ID prefix — makes jobs easy to identify in scheduler listings
_JOB_ID_PREFIX = "nodus_scheduled_"


# ---------------------------------------------------------------------------
# Internal job runner (APScheduler callback)
# ---------------------------------------------------------------------------

def _run_scheduled_nodus_job(job_id: str) -> None:
    """
    APScheduler callback executed on each cron tick for a Nodus scheduled job.

    Responsibilities
    ----------------
    1. Bail out if this instance is not the background task leader.
    2. Load ``NodusScheduledJob`` from DB; bail out if inactive.
    3. Create an ``AutomationLog`` entry for this execution.
    4. Run the Nodus script via ``PersistentFlowRunner(NODUS_SCRIPT_FLOW)``.
    5. Update ``AutomationLog`` and ``NodusScheduledJob`` with the outcome.

    All errors are caught — this function never raises so APScheduler does not
    disable the job due to an unhandled exception.
    """
    # ── 1. Leader election ────────────────────────────────────────────────────
    try:
        from services.task_services import is_background_leader
        if not is_background_leader():
            logger.debug("[NodusSchedule] Not leader — skipping job %s", job_id)
            return
    except Exception as _le_exc:
        logger.warning("[NodusSchedule] Leader check failed — skipping: %s", _le_exc)
        return

    from db.database import SessionLocal
    from db.models.nodus_scheduled_job import NodusScheduledJob
    from db.models.automation_log import AutomationLog

    db = SessionLocal()
    log: Optional[AutomationLog] = None

    try:
        # ── 2. Load job row ───────────────────────────────────────────────────
        job = (
            db.query(NodusScheduledJob)
            .filter(NodusScheduledJob.id == job_id)
            .first()
        )
        if not job or not job.is_active:
            logger.info("[NodusSchedule] Job %s not found or inactive — skipping", job_id)
            return

        label = job.job_name or f"nodus_job_{job_id}"
        trace_id = str(uuid.uuid4())

        # ── 3. Create AutomationLog ───────────────────────────────────────────
        log = AutomationLog(
            source="nodus_schedule",
            task_name=label,
            payload={
                "job_id": str(job.id),
                "cron_expression": job.cron_expression,
                "error_policy": job.error_policy,
            },
            status="running",
            user_id=job.user_id,
            max_attempts=job.max_retries,
            trace_id=trace_id,
            started_at=datetime.now(timezone.utc),
        )
        db.add(log)
        db.commit()

        # ── 4. Execute via PersistentFlowRunner ───────────────────────────────
        from runtime.flow_engine import FLOW_REGISTRY, PersistentFlowRunner, register_flow
        from runtime.nodus_runtime_adapter import NODUS_SCRIPT_FLOW
        from utils.uuid_utils import normalize_uuid

        if "nodus_execute" not in FLOW_REGISTRY:
            register_flow("nodus_execute", NODUS_SCRIPT_FLOW)

        user_id_str = str(job.user_id) if job.user_id else ""
        runner = PersistentFlowRunner(
            flow=FLOW_REGISTRY["nodus_execute"],
            db=db,
            user_id=normalize_uuid(user_id_str) if user_id_str else None,
            workflow_type="nodus_schedule",
        )

        result = runner.start(
            initial_state={
                "nodus_script": job.script,
                "nodus_input_payload": dict(job.input_payload or {}),
                "nodus_error_policy": job.error_policy,
                "trace_id": trace_id,
            },
            flow_name="nodus_execute",
        )

        # ── 5. Record outcome ─────────────────────────────────────────────────
        flow_succeeded = result.get("status") == "SUCCESS"
        final_state = result.get("state") or {}
        nodus_ok = final_state.get("nodus_status") != "failure"

        run_status = "success" if (flow_succeeded and nodus_ok) else "failure"

        log.status = "success" if run_status == "success" else "failed"
        log.result = {
            "flow_status": result.get("status"),
            "nodus_status": final_state.get("nodus_status"),
            "run_id": result.get("run_id"),
            "events_emitted": len(final_state.get("nodus_events") or []),
            "memory_writes": len(final_state.get("nodus_memory_writes") or []),
            "error": final_state.get("nodus_error") or result.get("error"),
        }
        log.completed_at = datetime.now(timezone.utc)

        job.last_run_at = log.completed_at
        job.last_run_status = run_status
        job.last_run_log_id = log.id
        db.commit()

        logger.info(
            "[NodusSchedule] Job %r (%s) completed — status=%s run_id=%s",
            label,
            job_id,
            run_status,
            result.get("run_id"),
        )

    except Exception as exc:
        logger.error("[NodusSchedule] Job %s raised: %s", job_id, exc)
        try:
            if log is not None:
                log.status = "failed"
                log.error_message = str(exc)
                log.completed_at = datetime.now(timezone.utc)
            # Also update job.last_run_status if we got that far
            if "job" in dir() and job is not None:
                job.last_run_at = datetime.now(timezone.utc)
                job.last_run_status = "error"
                if log is not None:
                    job.last_run_log_id = log.id
            db.commit()
        except Exception as _inner:
            logger.error("[NodusSchedule] Failed to persist error state: %s", _inner)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Service functions
# ---------------------------------------------------------------------------

def create_nodus_scheduled_job(
    *,
    db: Session,
    script: str,
    cron_expression: str,
    user_id: str,
    job_name: Optional[str] = None,
    script_name: Optional[str] = None,
    input_payload: Optional[dict] = None,
    error_policy: str = "fail",
    max_retries: int = 3,
) -> dict:
    """
    Persist a new ``NodusScheduledJob`` and register it with APScheduler.

    Parameters
    ----------
    db:
        Active SQLAlchemy session (committed before APScheduler registration).
    script:
        Resolved Nodus source code (caller is responsible for resolving
        ``script_name`` → content before calling this function).
    cron_expression:
        Standard 5-field cron string.  Validated via
        ``CronTrigger.from_crontab()`` before DB write.
    user_id:
        Job owner — used for memory scoping inside the script.
    job_name:
        Human-readable label (optional).
    script_name:
        Name of the uploaded script this job was created from (informational).
    input_payload:
        Initial ``nodus_input_payload`` dict passed to every execution.
    error_policy:
        ``"fail"`` (default) or ``"retry"``.
    max_retries:
        Maximum flow-engine retries when ``error_policy="retry"``.

    Returns
    -------
    dict
        Serialised job metadata (id, job_name, cron_expression, next_run_at, …).

    Raises
    ------
    ValueError
        When ``cron_expression`` is invalid, APScheduler is not available,
        or the scheduler has not been started yet.
    """
    # Validate cron expression before touching DB
    _trigger = _parse_cron(cron_expression)

    from db.models.nodus_scheduled_job import NodusScheduledJob
    from utils.uuid_utils import normalize_uuid

    uid = normalize_uuid(user_id) if user_id else None

    job_row = NodusScheduledJob(
        user_id=uid,
        job_name=job_name,
        script=script,
        script_name=script_name,
        cron_expression=cron_expression,
        input_payload=input_payload or {},
        error_policy=error_policy,
        max_retries=max_retries,
        is_active=True,
    )
    db.add(job_row)
    db.commit()
    db.refresh(job_row)

    job_id_str = str(job_row.id)

    # Register with APScheduler
    _register_with_scheduler(job_row, _trigger)

    logger.info(
        "[NodusSchedule] Created job %r id=%s cron=%r",
        job_name or job_id_str,
        job_id_str,
        cron_expression,
    )

    return _serialize_job(job_row, next_run_at=_next_run(_trigger))


def list_nodus_scheduled_jobs(*, db: Session, user_id: str) -> list[dict]:
    """
    Return all active scheduled Nodus jobs owned by ``user_id``.
    """
    from db.models.nodus_scheduled_job import NodusScheduledJob
    from utils.uuid_utils import normalize_uuid

    uid = normalize_uuid(user_id)
    rows = (
        db.query(NodusScheduledJob)
        .filter(
            NodusScheduledJob.user_id == uid,
            NodusScheduledJob.is_active.is_(True),
        )
        .order_by(NodusScheduledJob.created_at.desc())
        .all()
    )
    return [_serialize_job(r) for r in rows]


def delete_nodus_scheduled_job(
    *,
    db: Session,
    job_id: str,
    user_id: str,
) -> bool:
    """
    Soft-delete a scheduled job: set ``is_active=False`` and remove from
    APScheduler.

    Returns True on success, False if the job was not found or not owned by
    ``user_id``.
    """
    from db.models.nodus_scheduled_job import NodusScheduledJob
    from utils.uuid_utils import normalize_uuid

    uid = normalize_uuid(user_id)

    try:
        job_uuid = uuid.UUID(job_id)
    except (ValueError, AttributeError):
        return False

    row = (
        db.query(NodusScheduledJob)
        .filter(
            NodusScheduledJob.id == job_uuid,
            NodusScheduledJob.user_id == uid,
            NodusScheduledJob.is_active.is_(True),
        )
        .first()
    )
    if not row:
        return False

    row.is_active = False
    db.commit()

    # Remove from APScheduler (best-effort — may already be gone)
    _remove_from_scheduler(job_id)

    logger.info("[NodusSchedule] Deleted job %s", job_id)
    return True


def restore_nodus_scheduled_jobs() -> int:
    """
    Re-register all active ``NodusScheduledJob`` rows with APScheduler.

    Called from ``scheduler_service._register_system_jobs()`` on startup so
    schedules survive process restarts.

    Returns the number of jobs successfully restored.
    """
    from db.database import SessionLocal
    from db.models.nodus_scheduled_job import NodusScheduledJob

    db = SessionLocal()
    restored = 0
    try:
        rows = (
            db.query(NodusScheduledJob)
            .filter(NodusScheduledJob.is_active.is_(True))
            .all()
        )
        for row in rows:
            try:
                trigger = _parse_cron(row.cron_expression)
                _register_with_scheduler(row, trigger)
                restored += 1
            except Exception as exc:
                logger.warning(
                    "[NodusSchedule] Could not restore job %s (%r): %s",
                    row.id,
                    row.job_name,
                    exc,
                )
    except Exception as exc:
        logger.warning("[NodusSchedule] Restore scan failed: %s", exc)
    finally:
        db.close()

    if restored:
        logger.info("[NodusSchedule] Restored %d scheduled Nodus jobs", restored)
    return restored


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _parse_cron(cron_expression: str):
    """
    Parse and validate a 5-field cron expression using APScheduler's
    ``CronTrigger.from_crontab()``.

    Raises ValueError (with a descriptive message) if APScheduler is not
    available or the expression is invalid.
    """
    try:
        from apscheduler.triggers.cron import CronTrigger
    except ImportError as exc:
        raise ValueError("APScheduler is not installed — cannot schedule Nodus jobs") from exc

    try:
        return CronTrigger.from_crontab(cron_expression)
    except Exception as exc:
        raise ValueError(
            f"Invalid cron expression {cron_expression!r}: {exc}"
        ) from exc


def _next_run(trigger) -> Optional[str]:
    """Return the ISO 8601 next fire time for a trigger, or None."""
    try:
        from datetime import timezone as _tz
        next_dt = trigger.get_next_fire_time(None, datetime.now(_tz.utc))
        return next_dt.isoformat() if next_dt else None
    except Exception:
        return None


def _register_with_scheduler(job_row: Any, trigger: Any) -> None:
    """Add/replace the job in the live APScheduler instance."""
    from services.scheduler_service import get_scheduler

    scheduler = get_scheduler()
    job_id_str = str(job_row.id)
    label = job_row.job_name or f"nodus_job_{job_id_str}"

    scheduler.add_job(
        _run_scheduled_nodus_job,
        args=[job_id_str],
        trigger=trigger,
        id=f"{_JOB_ID_PREFIX}{job_id_str}",
        name=f"Nodus: {label}",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=60,
    )


def _remove_from_scheduler(job_id: str) -> None:
    """Remove a job from APScheduler (best-effort — never raises)."""
    try:
        from services.scheduler_service import get_scheduler
        scheduler = get_scheduler()
        aps_id = f"{_JOB_ID_PREFIX}{job_id}"
        try:
            scheduler.remove_job(aps_id)
        except Exception:
            pass  # Job may already be gone
    except Exception:
        pass


def _serialize_job(row: Any, next_run_at: Optional[str] = None) -> dict:
    """Convert a ``NodusScheduledJob`` ORM row to a plain dict."""
    return {
        "id": str(row.id),
        "job_name": row.job_name,
        "script_name": row.script_name,
        "cron_expression": row.cron_expression,
        "error_policy": row.error_policy,
        "max_retries": row.max_retries,
        "is_active": row.is_active,
        "last_run_at": row.last_run_at.isoformat() if row.last_run_at else None,
        "last_run_status": row.last_run_status,
        "last_run_log_id": row.last_run_log_id,
        "next_run_at": next_run_at,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
