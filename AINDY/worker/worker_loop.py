"""
WorkerLoop — hardened distributed async job executor.

Runs as a separate OS process (python -m worker.worker_loop) or as a
supervised thread inside the main process.  Pulls jobs from the
DistributedQueue, restores trace context, enforces DB claim safety, and
delegates all execution logic to the same ``_execute_job`` path used by the
thread-pool backend — zero divergence in execution semantics.

Reliability features
---------------------
Visibility timeout recovery (Task 1)
    On startup and every WORKER_STALE_CHECK_INTERVAL_SECONDS (default 60),
    the worker calls ``queue.requeue_stale_jobs(WORKER_VISIBILITY_TIMEOUT_SECONDS)``
    to recover jobs whose workers crashed before calling ack/fail.

Idempotency key (Task 2)
    ``job.idempotency_key`` (defaults to ``job_id``) is threaded into the
    execution context so handlers can use it for application-level de-dup.
    The primary guard is the DB-side atomic claim below.

Dead Letter Queue (Task 3)
    Handled in the queue backend: ``fail()`` automatically moves the payload to
    ``aindy:jobs:dead``.  The worker calls ``q.fail()`` on terminal exceptions.

Retry backoff (Task 4)
    Applied in ``execution_dispatcher._enqueue_distributed`` on the re-enqueue
    path: when ``context["retry"] == True``, an exponential delay is computed
    and ``queue.enqueue_delayed()`` is called instead of ``queue.enqueue()``.

Concurrency guard (Task 5)
    ``WORKER_MAX_CONCURRENT_JOBS`` (default 0 = unlimited) limits how many
    jobs a single process executes simultaneously across all of its threads.
    A semaphore is acquired after dequeue but before the DB claim; if the
    process is at capacity the dequeued job is re-enqueued.

Key invariants preserved
------------------------
- ``trace_id`` and ``eu_id`` are restored from the queued context before every
  dispatch, ensuring end-to-end trace continuity across the process boundary.
- ``ExecutionUnit`` lifecycle (pending → executing → completed/failed) is
  driven by ``_execute_job_inline`` exactly as in the thread-pool path.
- ``RetryPolicy`` is honoured: ``_execute_job_inline`` re-enqueues through
  ``ExecutionDispatcher`` when ``attempt_count < max_attempts``.
- Scheduler WAIT/RESUME is unaffected: the SchedulerEngine callback runs
  inside the same ``_execute_job_inline`` path.
- Inline execution (EXECUTION_MODE=thread or TESTING) is completely
  unchanged — this module is never loaded in those paths.

Usage
-----
    # Single worker process:
    python -m worker.worker_loop

    # 4 parallel dequeue threads, max 8 concurrent jobs:
    WORKER_CONCURRENCY=4 WORKER_MAX_CONCURRENT_JOBS=8 python -m worker.worker_loop

    # Programmatic:
    from AINDY.worker.worker_loop import run_worker_loop
    run_worker_loop(concurrency=2)

Environment variables
---------------------
WORKER_CONCURRENCY               int  Number of parallel dequeue threads (default 1)
WORKER_MAX_CONCURRENT_JOBS       int  Max in-progress jobs per process (default 0 = unlimited)
WORKER_VISIBILITY_TIMEOUT_SECS   int  Seconds before an in-flight job is stale (default 300)
WORKER_STALE_CHECK_INTERVAL_SECS int  How often to scan for stale jobs (default 60)
"""
from __future__ import annotations

import logging
import os
import signal
import threading
import time
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from AINDY.core.distributed_queue import DistributedQueueBackend, QueueJobPayload

logger = logging.getLogger(__name__)

# Module-level stop event shared across all worker threads in this process.
_STOP = threading.Event()

# ---------------------------------------------------------------------------
# Concurrency guard (Task 5)
# ---------------------------------------------------------------------------

_CONCURRENCY_SEM: Optional[threading.Semaphore] = None
_CONCURRENCY_SEM_LOCK = threading.Lock()


def _get_semaphore() -> Optional[threading.Semaphore]:
    """
    Return the process-level concurrency semaphore, or None if unlimited.

    The semaphore is sized by ``WORKER_MAX_CONCURRENT_JOBS``.  A value of 0
    (the default) means unlimited — no semaphore is created.

    The singleton is built lazily on first call and reused for the lifetime
    of the process.  Call ``reset_worker_state()`` in tests to clear it.
    """
    global _CONCURRENCY_SEM
    max_jobs = int(os.getenv("WORKER_MAX_CONCURRENT_JOBS", "0"))
    if max_jobs <= 0:
        return None
    if _CONCURRENCY_SEM is None:
        with _CONCURRENCY_SEM_LOCK:
            if _CONCURRENCY_SEM is None:
                _CONCURRENCY_SEM = threading.Semaphore(max_jobs)
                logger.info("[Worker] concurrency guard set to %d", max_jobs)
    return _CONCURRENCY_SEM


def reset_worker_state() -> None:
    """
    Reset all module-level singletons.

    Call this in test teardown to get a clean worker state between tests.
    """
    global _CONCURRENCY_SEM
    _STOP.clear()
    with _CONCURRENCY_SEM_LOCK:
        _CONCURRENCY_SEM = None


# ---------------------------------------------------------------------------
# Signal handling
# ---------------------------------------------------------------------------

def _handle_signal(signum: int, _frame) -> None:  # type: ignore[type-arg]
    logger.info("[Worker] signal %s received — initiating graceful shutdown", signum)
    _STOP.set()


# ---------------------------------------------------------------------------
# Trace context restoration
# ---------------------------------------------------------------------------

def _restore_trace_context(context: dict) -> tuple:
    """
    Set all trace ContextVars from the queued job context.

    Returns a tuple of tokens that must be passed to ``_reset_trace_context``
    in a ``finally`` block to avoid leaking context into subsequent jobs.

    Sets both the ``utils.trace_context`` ContextVars (used by
    ``async_job_service``) and the ``kernel.syscall_dispatcher`` ContextVars
    (used by nested syscall chains) so the full trace is continuous.
    """
    from AINDY.utils.trace_context import set_trace_id

    trace_id: str = context.get("trace_id") or ""
    eu_id: str = context.get("eu_id") or ""

    tok_trace = set_trace_id(trace_id) if trace_id else None

    try:
        from AINDY.kernel.syscall_dispatcher import _EU_ID_CTX, _TRACE_ID_CTX
        tok_syscall_trace = _TRACE_ID_CTX.set(trace_id) if trace_id else None
        tok_eu = _EU_ID_CTX.set(eu_id) if eu_id else None
    except Exception:
        tok_syscall_trace = None
        tok_eu = None

    return tok_trace, tok_syscall_trace, tok_eu


def _reset_trace_context(tokens: tuple) -> None:
    """Reset all ContextVars using the tokens from ``_restore_trace_context``."""
    tok_trace, tok_syscall_trace, tok_eu = tokens

    try:
        from AINDY.utils.trace_context import reset_trace_id
        if tok_trace is not None:
            reset_trace_id(tok_trace)
    except Exception:
        pass

    try:
        from AINDY.kernel.syscall_dispatcher import _EU_ID_CTX, _TRACE_ID_CTX
        if tok_syscall_trace is not None:
            _TRACE_ID_CTX.reset(tok_syscall_trace)
        if tok_eu is not None:
            _EU_ID_CTX.reset(tok_eu)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# DB claim safety
# ---------------------------------------------------------------------------

def _try_claim_job(log_id: str) -> bool:
    """
    Atomically claim an AutomationLog by setting ``status → running`` only
    when the current status is ``pending``.

    Returns ``True`` if this worker successfully claimed the job, ``False`` if
    the job is missing, already claimed, or if the DB update fails.

    Primary guard against duplicate execution when a stale job is re-enqueued
    after a visibility timeout and a second worker picks it up while the
    original (slow) worker is still executing.
    """
    from datetime import datetime, timezone

    from AINDY.db.database import SessionLocal
    from AINDY.db.models.automation_log import AutomationLog

    db = SessionLocal()
    try:
        updated = (
            db.query(AutomationLog)
            .filter(
                AutomationLog.id == log_id,
                AutomationLog.status == "pending",
            )
            .update(
                {
                    AutomationLog.status: "running",
                    AutomationLog.started_at: datetime.now(timezone.utc),
                },
                synchronize_session=False,
            )
        )
        db.commit()
        return updated > 0
    except Exception as exc:
        logger.error("[Worker] DB claim failed log_id=%s: %s", log_id, exc)
        try:
            db.rollback()
        except Exception:
            pass
        return False
    finally:
        db.close()


def _fetch_job_data(log_id: str) -> Optional[tuple[str, dict]]:
    """
    Return ``(task_name, payload)`` from the AutomationLog.

    The full payload lives in the DB record — the queue payload deliberately
    omits it to avoid large blobs crossing the wire.  Returns ``None`` when
    the record is missing (job was cancelled or already completed).
    """
    from AINDY.db.database import SessionLocal
    from AINDY.db.models.automation_log import AutomationLog

    db = SessionLocal()
    try:
        log = (
            db.query(AutomationLog)
            .filter(AutomationLog.id == log_id)
            .first()
        )
        if log is None:
            return None
        return log.task_name, log.payload or {}
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Observability
# ---------------------------------------------------------------------------

def _emit_worker_event(
    event_type: str,
    *,
    trace_id: str,
    eu_id: str,
    job_id: str,
    task_name: str,
    extra: Optional[dict] = None,
) -> None:
    """Fire-and-forget system event.  Never raises; failures are debug-logged."""
    try:
        from AINDY.core.system_event_service import emit_system_event
        from AINDY.db.database import SessionLocal

        db = SessionLocal()
        try:
            emit_system_event(
                db=db,
                event_type=event_type,
                user_id=None,
                trace_id=trace_id or job_id,
                parent_event_id=None,
                source="distributed_worker",
                payload={
                    "job_id": job_id,
                    "task_name": task_name,
                    "eu_id": eu_id,
                    **(extra or {}),
                },
                required=False,
            )
            db.commit()
        finally:
            db.close()
    except Exception as exc:
        logger.debug("[Worker] event emit skipped event_type=%s: %s", event_type, exc)


# ---------------------------------------------------------------------------
# Core job processing
# ---------------------------------------------------------------------------

def process_one_job(
    queue_backend: Optional["DistributedQueueBackend"] = None,
) -> bool:
    """
    Dequeue and execute one job.

    Returns ``True``  when a job was processed (success or failure).
    Returns ``False`` when no job arrived within the dequeue timeout,
                      or when the process is at concurrency capacity.

    Processing order
    ----------------
    1. Dequeue (blocking, up to 5 s timeout).
    2. Acquire concurrency semaphore — re-enqueue and return False if at capacity.
    3. Restore trace ContextVars from job.context.
    4. Emit ``job_started`` event.
    5. Atomic DB claim — skip (ack + return) if already claimed.
    6. Fetch (task_name, payload) from AutomationLog.
    7. Execute via ``_execute_job`` (same path as thread-pool backend).
    8. Ack + emit ``job_completed``.
    9. On exception: emit ``job_failed``, call ``q.fail()``.
    10. Release semaphore and reset trace context.
    """
    from AINDY.core.distributed_queue import get_queue

    q = queue_backend or get_queue()
    job: Optional["QueueJobPayload"] = q.dequeue(timeout=5)
    if job is None:
        return False  # Normal idle timeout.

    # ── Task 5: Concurrency guard — before any DB or execution work ────────
    sem = _get_semaphore()
    if sem is not None:
        # Try to acquire a slot, polling so we can respect _STOP.
        acquired = False
        while not acquired:
            acquired = sem.acquire(blocking=True, timeout=1.0)
            if acquired:
                break
            if _STOP.is_set():
                # Shutting down — put job back and exit.
                q.enqueue(job)
                logger.debug(
                    "[Worker] shutdown while waiting for slot — requeued job_id=%s",
                    job.job_id,
                )
                return False
        # At this point we own a semaphore slot.

    trace_id = job.context.get("trace_id") or job.job_id
    eu_id = job.context.get("eu_id") or ""

    logger.info(
        "[Worker] job_started job_id=%s task=%s trace_id=%s idempotency_key=%s",
        job.job_id, job.task_name, trace_id, job.idempotency_key,
    )

    # ── Task 2: Thread idempotency_key into context for downstream handlers ─
    enriched_context = {**job.context, "idempotency_key": job.idempotency_key}

    # Restore trace context before any DB or handler calls.
    tokens = _restore_trace_context(enriched_context)

    try:
        _emit_worker_event(
            "job_started",
            trace_id=trace_id,
            eu_id=eu_id,
            job_id=job.job_id,
            task_name=job.task_name,
            extra={"idempotency_key": job.idempotency_key},
        )

        # DB claim safety — skip if already claimed by another worker.
        # This is the critical guard after a visibility-timeout re-enqueue.
        if not _try_claim_job(job.job_id):
            logger.warning(
                "[Worker] job_id=%s already claimed or missing — skipping",
                job.job_id,
            )
            q.ack(job.job_id)
            return True

        # Fetch payload from DB (omitted from the queue payload to keep it lean).
        job_data = _fetch_job_data(job.job_id)
        if job_data is None:
            logger.warning("[Worker] AutomationLog not found job_id=%s", job.job_id)
            q.ack(job.job_id)
            return True
        task_name, payload = job_data

        # Execute via the same path as the thread-pool backend.
        # _execute_job_inline drives: EU status, retry logic, events, DB commit.
        from AINDY.platform_layer.async_job_service import _execute_job

        _execute_job(job.job_id, task_name, payload)

        q.ack(job.job_id)
        logger.info(
            "[Worker] job_completed job_id=%s task=%s trace_id=%s",
            job.job_id, job.task_name, trace_id,
        )
        _emit_worker_event(
            "job_completed",
            trace_id=trace_id,
            eu_id=eu_id,
            job_id=job.job_id,
            task_name=job.task_name,
        )

    except Exception as exc:
        # _execute_job_inline handles retry internally; an exception escaping
        # here is unexpected (belt-and-suspenders).  Send to DLQ.
        logger.error(
            "[Worker] job_failed job_id=%s task=%s error=%s",
            job.job_id, job.task_name, exc,
            exc_info=True,
        )
        _emit_worker_event(
            "job_failed",
            trace_id=trace_id,
            eu_id=eu_id,
            job_id=job.job_id,
            task_name=job.task_name,
            extra={"error": str(exc)},
        )
        # Task 3: fail() moves the payload to the Dead Letter Queue.
        q.fail(job.job_id, str(exc))

    finally:
        # Always reset trace context and release concurrency slot.
        _reset_trace_context(tokens)
        if sem is not None:
            sem.release()

    return True


# ---------------------------------------------------------------------------
# Stale-job recovery background thread (Task 1)
# ---------------------------------------------------------------------------

def _run_stale_recovery(
    queue_backend: "DistributedQueueBackend",
    *,
    visibility_timeout: int,
    check_interval: int,
) -> None:
    """
    Background thread: periodically re-enqueue stale in-flight jobs.

    Runs until ``_STOP`` is set.  First invocation is immediate (startup
    recovery); subsequent invocations are spaced *check_interval* seconds apart.
    """
    # Immediate scan on startup.
    while not _STOP.is_set():
        try:
            count = queue_backend.requeue_stale_jobs(visibility_timeout)
            if count:
                logger.info("[Worker] stale recovery: re-enqueued %d jobs", count)
        except Exception as exc:
            logger.error("[Worker] stale recovery error: %s", exc)
        # Sleep in small increments so we respond to _STOP promptly.
        for _ in range(check_interval):
            if _STOP.is_set():
                return
            time.sleep(1)


# ---------------------------------------------------------------------------
# Worker loop
# ---------------------------------------------------------------------------

def _single_thread_loop(
    queue_backend: Optional["DistributedQueueBackend"],
) -> None:
    """Synchronous dequeue-execute loop. Runs until _STOP is set."""
    while not _STOP.is_set():
        try:
            process_one_job(queue_backend)
        except Exception as exc:
            # Unexpected loop-level error — log and keep running.
            logger.error("[Worker] loop error: %s", exc, exc_info=True)
            time.sleep(1)


def run_worker_loop(
    *,
    concurrency: int = 1,
    queue_backend: Optional["DistributedQueueBackend"] = None,
) -> None:
    """
    Start the worker loop and block until SIGTERM / SIGINT.

    Parameters
    ----------
    concurrency:
        Number of parallel dequeue threads within this process.
        Each thread runs its own ``process_one_job`` loop.
        Default 1 (sequential).
    queue_backend:
        Override the default ``get_queue()`` backend.  Primarily for tests.
    """
    # Reset stop event in case of restart / test re-use.
    _STOP.clear()

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    from AINDY.core.distributed_queue import get_queue
    q = queue_backend or get_queue()

    visibility_timeout = int(os.getenv("WORKER_VISIBILITY_TIMEOUT_SECS", "300"))
    check_interval = int(os.getenv("WORKER_STALE_CHECK_INTERVAL_SECS", "60"))

    logger.info(
        "[Worker] starting — concurrency=%d visibility_timeout=%ds check_interval=%ds",
        concurrency, visibility_timeout, check_interval,
    )

    # ── Task 1: Startup stale recovery + periodic background thread ────────
    stale_thread = threading.Thread(
        target=_run_stale_recovery,
        kwargs={
            "queue_backend": q,
            "visibility_timeout": visibility_timeout,
            "check_interval": check_interval,
        },
        name="aindy-stale-recovery",
        daemon=True,
    )
    stale_thread.start()

    # ── Dequeue worker threads ─────────────────────────────────────────────
    if concurrency <= 1:
        _single_thread_loop(q)
    else:
        threads: list[threading.Thread] = []
        for i in range(concurrency):
            t = threading.Thread(
                target=_single_thread_loop,
                args=(q,),
                name=f"aindy-worker-{i}",
                daemon=True,
            )
            t.start()
            threads.append(t)

        _STOP.wait()
        for t in threads:
            t.join(timeout=10)

    stale_thread.join(timeout=5)
    logger.info("[Worker] stopped")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stdout,
    )

    _concurrency = int(os.getenv("WORKER_CONCURRENCY", "1"))
    run_worker_loop(concurrency=_concurrency)
