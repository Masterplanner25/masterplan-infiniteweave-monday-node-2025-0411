"""
Scheduler Service — APScheduler + tenacity

Replaces daemon thread background task execution with supervised,
retryable, auditable job execution.

Architecture:
- BackgroundScheduler: runs jobs in background threads managed by
  APScheduler (not raw daemon threads)
- tenacity: automatic retry with exponential backoff
- AutomationLog: every execution is recorded (started_at, status, result)
- Replay: any failed job can be retried via the automation router API

Lifecycle:
- start() called in main.py lifespan on startup
- stop() called in main.py lifespan on shutdown
- Never call directly from routes — use schedule_task() or run_task_now()
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Callable, Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)

logger = logging.getLogger(__name__)

# Global scheduler instance — initialized once on startup
_scheduler: Optional[BackgroundScheduler] = None

# Task function registry for replay
# Register task functions here so replay_task() can look them up by name
_TASK_REGISTRY: dict[str, Callable] = {}


# ── Public lifecycle ────────────────────────────────────────────────────────

def get_scheduler() -> BackgroundScheduler:
    """Get the global scheduler instance."""
    global _scheduler
    if _scheduler is None:
        raise RuntimeError(
            "Scheduler not started. Call scheduler_service.start() first."
        )
    return _scheduler


def start() -> None:
    """
    Start the APScheduler background scheduler.
    Called from main.py lifespan on startup.
    Replaces threading.Thread(daemon=True) pattern.
    """
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        logger.warning("Scheduler already running — start() called twice")
        return

    _scheduler = BackgroundScheduler(
        job_defaults={
            "coalesce": True,        # Don't stack missed runs
            "max_instances": 1,      # One instance of each job at a time
            "misfire_grace_time": 60,  # 60s grace for missed scheduled runs
        }
    )

    _register_system_jobs(_scheduler)
    _scheduler.start()
    logger.info("APScheduler started — daemon threads replaced")


def stop() -> None:
    """
    Stop the scheduler gracefully.
    Called from main.py lifespan on shutdown.
    """
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=True)
        logger.info("APScheduler stopped")
    _scheduler = None


# ── System jobs ─────────────────────────────────────────────────────────────

def _register_system_jobs(scheduler: BackgroundScheduler) -> None:
    """
    Register recurring system jobs.
    Add new scheduled jobs here — they start automatically on scheduler start.
    """
    # Cleanup automation logs stuck in 'pending' for > 1 hour
    scheduler.add_job(
        _cleanup_stale_logs,
        trigger=IntervalTrigger(hours=1),
        id="cleanup_stale_logs",
        name="Cleanup stale automation logs",
        replace_existing=True,
    )

    # Task reminder check — replaces daemon _run_check_reminders thread
    scheduler.add_job(
        _check_reminders_job,
        trigger=IntervalTrigger(minutes=1),
        id="task_reminder_check",
        name="Task reminder check",
        replace_existing=True,
    )

    # Task recurrence check — replaces daemon _run_handle_recurrence thread
    scheduler.add_job(
        _check_task_recurrence,
        trigger=CronTrigger(hour="*/6"),
        id="task_recurrence_check",
        name="Task recurrence check",
        replace_existing=True,
    )

    # Daily ETA recalculation — recomputes velocity + projection for all anchored plans
    scheduler.add_job(
        _recalculate_all_etas_job,
        trigger=CronTrigger(hour=6),
        id="daily_eta_recalculation",
        name="Daily ETA projection recalculation",
        replace_existing=True,
    )

    # Daily Infinity score recalculation — 7am (after 6am ETA job)
    scheduler.add_job(
        _recalculate_all_scores,
        trigger=CronTrigger(hour=7),
        id="daily_infinity_score_recalculation",
        name="Daily Infinity score recalculation",
        replace_existing=True,
    )


def _recalculate_all_scores() -> None:
    """Daily job: recalculate Infinity scores for all users."""
    try:
        from db.database import SessionLocal
        from db.models.user import User
        from services.infinity_service import calculate_infinity_score

        db = SessionLocal()
        try:
            users = db.query(User).all()
            updated = 0
            for user in users:
                result = calculate_infinity_score(
                    user_id=str(user.id),
                    db=db,
                    trigger_event="scheduled",
                )
                if result:
                    updated += 1
            logger.info(
                "[Infinity Scheduler] Recalculated scores for %d/%d users",
                updated, len(users)
            )
        finally:
            db.close()
    except Exception as exc:
        logger.warning("[Infinity Scheduler] Daily score recalculation failed: %s", exc)


def _recalculate_all_etas_job() -> None:
    """Daily job: recalculate ETA projections for all anchored MasterPlans."""
    try:
        from db.database import SessionLocal
        from services.eta_service import recalculate_all_etas

        db = SessionLocal()
        try:
            updated = recalculate_all_etas(db)
            logger.info("[ETA Scheduler] Recalculated ETAs for %d plans", updated)
        finally:
            db.close()
    except Exception as exc:
        logger.error("[ETA Scheduler] Daily ETA recalculation failed: %s", exc)


def _cleanup_stale_logs() -> None:
    """Clean up AutomationLog entries stuck in 'pending' for > 1 hour."""
    try:
        from db.database import SessionLocal
        from db.models.automation_log import AutomationLog
        from datetime import timedelta

        db = SessionLocal()
        cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
        stale = (
            db.query(AutomationLog)
            .filter(
                AutomationLog.status == "pending",
                AutomationLog.created_at < cutoff,
            )
            .all()
        )
        for log in stale:
            log.status = "failed"
            log.error_message = "Stale: never started within 1 hour of creation"
        db.commit()
        db.close()
        if stale:
            logger.info("Cleaned up %d stale automation logs", len(stale))
    except Exception as exc:
        logger.warning("Stale log cleanup failed: %s", exc)


def _check_reminders_job() -> None:
    """Check for overdue task reminders — replaces daemon thread."""
    try:
        from services.task_services import check_reminders
        check_reminders()
    except Exception as exc:
        logger.warning("Task reminder check failed: %s", exc)


def _check_task_recurrence() -> None:
    """Trigger task recurrence check — replaces daemon thread."""
    try:
        from services.task_services import handle_recurrence
        handle_recurrence()
    except Exception as exc:
        logger.warning("Task recurrence check failed: %s", exc)


# ── Task execution ──────────────────────────────────────────────────────────

def run_task_now(
    task_fn: Callable,
    task_name: str,
    payload: dict = None,
    user_id: str = None,
    max_attempts: int = 3,
    source: str = "manual",
) -> str:
    """
    Run a task immediately in a supervised APScheduler thread.

    Creates an AutomationLog entry, schedules the job for immediate
    execution, and returns the log ID for tracking.

    Replaces:
        thread = threading.Thread(target=fn, daemon=True)
        thread.start()

    With:
        run_task_now(fn, "task_name", payload)
    """
    from db.database import SessionLocal
    from db.models.automation_log import AutomationLog

    db = SessionLocal()
    log = AutomationLog(
        source=source,
        task_name=task_name,
        payload=payload or {},
        status="pending",
        max_attempts=max_attempts,
        user_id=user_id,
    )
    db.add(log)
    db.commit()
    log_id = log.id
    db.close()

    scheduler = get_scheduler()
    scheduler.add_job(
        _supervised_execute,
        args=[log_id, task_fn, payload or {}],
        id=f"task_{log_id}",
        name=task_name,
        replace_existing=True,
    )

    return log_id


def _supervised_execute(log_id: str, task_fn: Callable, payload: dict) -> None:
    """
    Execute a task function with tenacity retry, updating the AutomationLog.

    This is the core replacement for daemon threads. Every execution is:
    - Logged (started_at, completed_at, attempt_count)
    - Retried on failure with exponential backoff (tenacity)
    - Auditable (status + error_message stored in AutomationLog)
    """
    from db.database import SessionLocal
    from db.models.automation_log import AutomationLog

    db = SessionLocal()
    log = db.query(AutomationLog).filter(AutomationLog.id == log_id).first()

    if not log:
        logger.error("AutomationLog %s not found — cannot execute", log_id)
        db.close()
        return

    log.status = "running"
    log.started_at = datetime.now(timezone.utc)
    db.commit()

    max_attempts = log.max_attempts

    @retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    def execute_with_retry():
        log.attempt_count += 1
        if log.attempt_count > 1:
            log.status = "retrying"
        db.commit()
        return task_fn(payload)

    try:
        result = execute_with_retry()
        log.status = "success"
        log.result = result if isinstance(result, dict) else {"result": str(result)}
        log.completed_at = datetime.now(timezone.utc)
        db.commit()
        logger.info(
            "Task %s succeeded (log: %s, attempts: %d)",
            log.task_name,
            log_id,
            log.attempt_count,
        )
    except Exception as exc:
        log.status = "failed"
        log.error_message = str(exc)
        log.completed_at = datetime.now(timezone.utc)
        db.commit()
        logger.error(
            "Task %s failed after %d attempt(s): %s",
            log.task_name,
            log.attempt_count,
            exc,
        )
    finally:
        db.close()


def replay_task(log_id: str) -> bool:
    """
    Replay a failed task execution from its AutomationLog.

    Resets the log to pending and re-runs the original task function
    with the original payload. Only failed or retrying logs can be replayed.

    Returns True if replay was scheduled, False if log not found / not failed
    or task function not in registry.
    """
    from db.database import SessionLocal
    from db.models.automation_log import AutomationLog

    db = SessionLocal()
    log = db.query(AutomationLog).filter(AutomationLog.id == log_id).first()

    if not log:
        db.close()
        return False

    if log.status not in ("failed", "retrying"):
        db.close()
        return False

    task_fn = _TASK_REGISTRY.get(log.task_name)
    if not task_fn:
        logger.warning(
            "Task function '%s' not in registry — cannot replay log %s",
            log.task_name,
            log_id,
        )
        db.close()
        return False

    # Reset for replay
    log.status = "pending"
    log.attempt_count = 0
    log.error_message = None
    log.started_at = None
    log.completed_at = None
    log_payload = log.payload
    log_task_name = log.task_name
    db.commit()
    db.close()

    scheduler = get_scheduler()
    scheduler.add_job(
        _supervised_execute,
        args=[log_id, task_fn, log_payload or {}],
        id=f"replay_{log_id}",
        name=f"replay:{log_task_name}",
        replace_existing=True,
    )

    return True


# ── Task registry ───────────────────────────────────────────────────────────

def register_task(name: str):
    """
    Decorator to register a task function for supervised execution and replay.

    Usage:
        @register_task("my_background_task")
        def my_background_task(payload: dict):
            ...
            return {"status": "done"}
    """
    def wrapper(fn: Callable) -> Callable:
        _TASK_REGISTRY[name] = fn
        return fn

    return wrapper
