"""
Scheduler Service â€” APScheduler + tenacity

Replaces daemon thread background job execution with supervised,
retryable, auditable job execution.

Architecture:
- BackgroundScheduler: runs jobs in background threads managed by
  APScheduler (not raw daemon threads)
- tenacity: automatic retry with exponential backoff
- JobLog: every execution is recorded (started_at, status, result)
- Replay: any failed job can be retried via the automation router API

Lifecycle:
- start() called in main.py lifespan on startup
- stop() called in main.py lifespan on shutdown
- Never call directly from routes; use scheduled job registration or run_job_now()
"""
import logging
from datetime import datetime, timezone
from typing import Callable, Optional

from AINDY.db.models.job_log import JobLog
from AINDY.platform_layer.registry import get_scheduled_jobs

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger
except ImportError:  # pragma: no cover - optional dependency
    class _FallbackJob:
        def __init__(self, *, func, trigger, id, name, replace_existing):
            self.func = func
            self.trigger = trigger
            self.id = id
            self.name = name
            self.replace_existing = replace_existing

    class BackgroundScheduler:  # type: ignore[no-redef]
        def __init__(self, job_defaults=None):
            self.job_defaults = job_defaults or {}
            self.running = False
            self._jobs = []

        def add_job(self, func, trigger=None, id=None, name=None, replace_existing=False, **kwargs):
            if replace_existing and id is not None:
                self._jobs = [job for job in self._jobs if job.id != id]
            self._jobs.append(
                _FallbackJob(
                    func=func,
                    trigger=trigger,
                    id=id,
                    name=name,
                    replace_existing=replace_existing,
                )
            )

        def get_jobs(self):
            return list(self._jobs)

        def start(self):
            self.running = True

        def shutdown(self, wait=True):
            self.running = False

    class CronTrigger:  # type: ignore[no-redef]
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class IntervalTrigger:  # type: ignore[no-redef]
        def __init__(self, **kwargs):
            self.kwargs = kwargs
try:
    from tenacity import (
        retry,
        stop_after_attempt,
        wait_exponential,
        before_sleep_log,
    )
except ImportError:  # pragma: no cover - optional dependency
    def retry(*args, **kwargs):
        def decorator(fn):
            return fn

        return decorator

    def stop_after_attempt(attempts):
        return attempts

    def wait_exponential(**kwargs):
        return kwargs

    def before_sleep_log(*args, **kwargs):
        return None

logger = logging.getLogger(__name__)

APScheduler_AVAILABLE = True
_STALE_WAIT_CLEANUP_COUNTER = 0

# Global scheduler instance â€” initialized once on startup
_scheduler: Optional[BackgroundScheduler] = None

# Job function registry for replay.
# Legacy task APIs still use these stored JobLog task_name values.
_TASK_REGISTRY: dict[str, Callable] = {}


# â”€â”€ Public lifecycle â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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
        logger.warning("Scheduler already running â€” start() called twice")
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
    logger.info("APScheduler started â€” daemon threads replaced")


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


# â”€â”€ System jobs â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _register_system_jobs(scheduler: BackgroundScheduler) -> None:
    """Register recurring platform jobs and app-registered scheduled jobs."""
    scheduler.add_job(
        _scheduler_heartbeat_tick,
        trigger=IntervalTrigger(seconds=1),
        id="scheduler_heartbeat_tick",
        name="Scheduler heartbeat tick",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )

    scheduler.add_job(
        _scrape_scheduler_metrics,
        trigger=IntervalTrigger(seconds=15),
        id="scrape_scheduler_metrics",
        name="Prometheus scheduler gauge scrape",
        replace_existing=True,
    )

    scheduler.add_job(
        _cleanup_stale_logs,
        trigger=IntervalTrigger(hours=1),
        id="cleanup_stale_logs",
        name="Cleanup stale automation logs",
        replace_existing=True,
    )

    scheduler.add_job(
        _process_deferred_async_jobs,
        trigger=IntervalTrigger(minutes=1),
        id="deferred_async_job_retry",
        name="Deferred async job retry",
        replace_existing=True,
    )

    scheduler.add_job(
        _check_queue_backend_health,
        trigger=IntervalTrigger(seconds=60),
        id="queue_backend_reconnect",
        name="Queue backend reconnect",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )

    scheduler.add_job(
        _expire_timed_out_waits,
        trigger=IntervalTrigger(minutes=5),
        id="expire_timed_out_waits",
        name="Expire timed-out flow waits",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )

    scheduler.add_job(
        _expire_timed_out_wait_flows,
        trigger=IntervalTrigger(seconds=60),
        id="expire_timed_out_wait_flows",
        name="Expire timed-out WaitingFlowRun waits",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )

    scheduler.add_job(
        _recover_stuck_flow_runs,
        trigger=IntervalTrigger(minutes=5),
        id="recover_stuck_flow_runs",
        name="Recover stuck flow runs",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )

    for job in get_scheduled_jobs():
        scheduler.add_job(
            job["handler"],
            trigger=_build_trigger(job.get("trigger", "interval"), job.get("trigger_kwargs") or {}),
            id=job["id"],
            name=job.get("name") or job["id"],
            replace_existing=bool(job.get("replace_existing", True)),
        )

    try:
        from AINDY.runtime.nodus_schedule_service import restore_nodus_scheduled_jobs
        restore_nodus_scheduled_jobs()
    except Exception as _nodus_restore_exc:
        logger.warning(
            "Nodus scheduled job restore failed (non-fatal): %s",
            _nodus_restore_exc,
        )


def _build_trigger(trigger_type: str, trigger_kwargs: dict) -> object:
    if trigger_type == "cron":
        return CronTrigger(**trigger_kwargs)
    if trigger_type == "interval":
        return IntervalTrigger(**trigger_kwargs)
    raise ValueError(f"Unsupported scheduled job trigger: {trigger_type}")


def _scrape_scheduler_metrics() -> None:
    """Update Prometheus scheduler gauges from the live SchedulerEngine snapshot."""
    try:
        from AINDY.kernel.scheduler_engine import get_scheduler_engine
        from AINDY.platform_layer.metrics import scheduler_queue_depth, scheduler_waiting_count
        snapshot = get_scheduler_engine().get_metrics_snapshot()
        for priority, depth in snapshot["queue_depth"].items():
            scheduler_queue_depth.labels(priority=priority).set(depth)
        scheduler_waiting_count.set(snapshot["waiting_count"])
    except Exception as exc:
        logger.warning("Scheduler metrics scrape failed (non-fatal): %s", exc)


def _should_run_stale_wait_cleanup() -> bool:
    global _STALE_WAIT_CLEANUP_COUNTER
    _STALE_WAIT_CLEANUP_COUNTER += 1
    if _STALE_WAIT_CLEANUP_COUNTER >= 60:
        _STALE_WAIT_CLEANUP_COUNTER = 0
        return True
    return False


def _scheduler_heartbeat_tick() -> None:
    """Drive scheduler dispatch and amortized stale-wait cleanup."""
    try:
        from AINDY.kernel.scheduler_engine import get_scheduler_engine

        engine = get_scheduler_engine()
        engine.schedule()
        if _should_run_stale_wait_cleanup():
            engine.cleanup_stale_waits()
    except Exception as exc:
        logger.warning("Scheduler heartbeat tick failed: %s", exc)


def _cleanup_stale_logs() -> None:
    """Clean up JobLog entries stuck in 'pending' for > 1 hour."""
    try:
        from AINDY.db.database import SessionLocal
        from datetime import timedelta

        db = SessionLocal()
        cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
        stale = (
            db.query(JobLog)
            .filter(
                JobLog.status == "pending",
                JobLog.created_at < cutoff,
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




# Job execution

def _process_deferred_async_jobs() -> None:
    try:
        from AINDY.platform_layer.async_job_service import process_deferred_jobs

        resumed = process_deferred_jobs()
        if resumed:
            logger.info("Deferred async jobs resumed: %d", resumed)
    except Exception as exc:
        logger.warning("Deferred async job processing failed: %s", exc)


def _check_queue_backend_health() -> None:
    try:
        from AINDY.core.distributed_queue import attempt_queue_backend_reconnect

        if attempt_queue_backend_reconnect():
            logger.info("Distributed queue backend recovered to Redis")
    except Exception as exc:
        logger.warning("Queue backend health check failed: %s", exc)


def _expire_timed_out_waits() -> None:
    try:
        from AINDY.platform_layer.recovery_jobs import run_expire_timed_out_waits_job

        run_expire_timed_out_waits_job()
    except Exception as exc:
        logger.warning("Timed-out WAIT recovery dispatch failed: %s", exc)


def _expire_timed_out_wait_flows() -> None:
    try:
        from AINDY.platform_layer.recovery_jobs import run_expire_timed_out_wait_flows_job

        run_expire_timed_out_wait_flows_job()
    except Exception as exc:
        logger.warning("Timed-out WaitingFlowRun recovery dispatch failed: %s", exc)


def _recover_stuck_flow_runs() -> None:
    try:
        from AINDY.platform_layer.recovery_jobs import run_recover_stuck_runs_job

        run_recover_stuck_runs_job()
    except Exception as exc:
        logger.warning("Periodic stuck-run recovery dispatch failed: %s", exc)


def run_task_now(
    task_fn: Callable,
    task_name: str,
    payload: dict = None,
    user_id: str = None,
    max_attempts: int = 3,
    source: str = "manual",
) -> str:
    """
    Run a job immediately in a supervised APScheduler thread.

    Creates an JobLog entry, schedules the job for immediate
    execution, and returns the log ID for tracking.

    Replaces:
        thread = threading.Thread(target=fn, daemon=True)
        thread.start()

    With:
        run_job_now(fn, "operation_name", payload)
    """
    from AINDY.db.database import SessionLocal

    db = SessionLocal()
    log = JobLog(
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
    Execute a job function with tenacity retry, updating the JobLog.

    This is the core replacement for daemon threads. Every execution is:
    - Logged (started_at, completed_at, attempt_count)
    - Retried on failure with exponential backoff (tenacity)
    - Auditable (status + error_message stored in JobLog)
    """
    from AINDY.db.database import SessionLocal

    db = SessionLocal()
    log = db.query(JobLog).filter(JobLog.id == log_id).first()

    if not log:
        logger.error("JobLog %s not found â€” cannot execute", log_id)
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
            "Job %s succeeded (log: %s, attempts: %d)",
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
            "Job %s failed after %d attempt(s): %s",
            log.task_name,
            log.attempt_count,
            exc,
        )
    finally:
        db.close()


def replay_task(log_id: str) -> bool:
    """
    Replay a failed job execution from its JobLog.

    Resets the log to pending and re-runs the original job function
    with the original payload. Only failed or retrying logs can be replayed.

    Returns True if replay was scheduled, False if log not found / not failed
    or job function not in registry.
    """
    from AINDY.db.database import SessionLocal

    db = SessionLocal()
    log = db.query(JobLog).filter(JobLog.id == log_id).first()

    if not log:
        db.close()
        return False

    if log.status not in ("failed", "retrying"):
        db.close()
        return False

    task_fn = _TASK_REGISTRY.get(log.task_name)
    if not task_fn:
        logger.warning(
            "Job function '%s' not in registry; cannot replay log %s",
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


# Job registry

def register_task(name: str):
    """
    Decorator to register a job function for supervised execution and replay.

    Usage:
        @register_job_function("my_background_job")
        def my_background_job(payload: dict):
            ...
            return {"status": "done"}
    """
    def wrapper(fn: Callable) -> Callable:
        _TASK_REGISTRY[name] = fn
        return fn

    return wrapper


register_task_function = register_task
register_job_function = register_task_function
run_job_now = run_task_now
replay_job = replay_task



