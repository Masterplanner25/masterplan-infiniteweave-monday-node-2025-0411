"""
DistributedQueue — pluggable transport layer for async job execution.

Replaces the ThreadPoolExecutor submit path in ExecutionDispatcher when
``EXECUTION_MODE=distributed``.  The thread-pool backend remains available
via ``EXECUTION_MODE=thread`` (the default — no change to existing behaviour).

Backends
--------
RedisQueueBackend
    Preferred for multi-process / multi-host deployments.
    Requires ``REDIS_URL`` in the environment.
    Uses LPUSH / BRPOP — atomically guaranteed single-consumer per message.

InMemoryQueueBackend
    For tests and single-process dev without Redis.
    Thread-safe; NOT usable across OS processes.

Job lifecycle
-------------
  enqueue()         → job pushed to tail of queue
  enqueue_delayed() → job enters delayed sorted-set; moved to main queue after delay
  dequeue()         → exclusive blocking pop; job enters in-flight tracking
  ack()             → job succeeded; removed from in-flight
  fail()            → terminal failure; moved to Dead Letter Queue

In-flight / visibility timeout
------------------------------
When a job is dequeued, the backend records ``{payload, dequeued_at}`` in an
in-flight store.  If a worker crashes before calling ``ack()`` or ``fail()``,
the job stays in the in-flight store indefinitely.

``requeue_stale_jobs(timeout_seconds)`` scans the in-flight store and re-enqueues
any job whose ``dequeued_at`` is older than *timeout_seconds*.  Call it on worker
startup and periodically to recover from crashes.

Dead Letter Queue
-----------------
``fail()`` moves the job to a dead-letter store (``aindy:jobs:dead`` in Redis or
an in-process list in InMemoryQueueBackend).  Jobs in the DLQ are never
automatically retried; they must be inspected and replayed by an operator.

Delayed enqueue / retry backoff
--------------------------------
``enqueue_delayed(payload, delay_seconds)`` schedules a job for future execution:
  Redis   — ZADD to ``aindy:jobs:delayed`` with score = execute_at Unix timestamp.
            ``process_delayed_jobs()`` pops ready items and pushes to main queue.
  InMemory — ``threading.Timer`` fires the enqueue after the delay.

Metrics
-------
``get_metrics()`` returns a dict with:
  queue_depth, in_flight_count, failed_jobs, delayed_jobs

Idempotency key
---------------
``QueueJobPayload.idempotency_key`` — defaults to ``job_id`` if not supplied.
Passed through to the worker so handlers can use it for de-duplication logic.
The primary dedup mechanism is still the DB-side atomic claim in worker_loop.

Payload shape (QueueJobPayload)
-------------------------------
  job_id:           str  — AutomationLog.id; primary key for DB-side lifecycle
  task_name:        str  — registered handler key in _JOB_REGISTRY
  idempotency_key:  str  — dedup key; defaults to job_id
  context:          dict — {"trace_id", "eu_id", "user_id", "capabilities"}
  retry_metadata:   dict — {"attempt_count", "max_attempts", "is_retry"}
  enqueued_at:      str  — ISO 8601 UTC timestamp

The payload is intentionally lightweight: the worker re-fetches the full
AutomationLog from the database by ``job_id`` before executing, so large
``payload`` blobs never travel through the queue.
"""
from __future__ import annotations

import json
import logging
import os
import queue
import threading
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

QUEUE_NAME_DEFAULT = "aindy:jobs"


# ---------------------------------------------------------------------------
# Payload schema
# ---------------------------------------------------------------------------

@dataclass
class QueueJobPayload:
    """Serialisable representation of one distributed async job."""

    job_id: str
    """AutomationLog.id — used to look up the full record from the DB."""

    task_name: str
    """Registered handler key in _JOB_REGISTRY (e.g. ``"agent.create_run"``)."""

    idempotency_key: str = ""
    """
    Deduplication key.  Defaults to ``job_id`` if not explicitly set.
    Handlers may check this to guard against double-execution after a
    visibility-timeout re-enqueue; the primary guard is the DB-side atomic
    ``UPDATE WHERE status='pending'`` claim in worker_loop.
    """

    context: dict = field(default_factory=dict)
    """Execution context carried across the worker boundary:
    ``trace_id``, ``eu_id``, ``user_id``, ``capabilities``."""

    retry_metadata: dict = field(default_factory=dict)
    """``attempt_count``, ``max_attempts``, ``is_retry`` — carried across
    re-enqueues so the worker can restore the correct retry state."""

    enqueued_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    """Wall-clock timestamp at enqueue time (UTC ISO 8601)."""

    def __post_init__(self) -> None:
        # Default idempotency_key to job_id when not supplied (or when
        # deserialised from an older payload that lacked the field).
        if not self.idempotency_key:
            self.idempotency_key = self.job_id

    def to_json(self) -> str:
        """Serialise to a compact JSON string (wire format)."""
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, raw: str) -> "QueueJobPayload":
        """Deserialise from a JSON string. Unknown fields are silently dropped."""
        data = json.loads(raw)
        known = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in data.items() if k in known})


# ---------------------------------------------------------------------------
# Abstract backend interface
# ---------------------------------------------------------------------------

class DistributedQueueBackend(ABC):
    """
    Abstract queue transport.

    Abstract methods (must be implemented):
        enqueue, dequeue, ack, fail

    Concrete defaults (may be overridden):
        enqueue_delayed   — falls back to immediate enqueue
        process_delayed_jobs — no-op
        requeue_stale_jobs   — no-op
        get_metrics          — returns empty dict
    """

    @abstractmethod
    def enqueue(self, payload: QueueJobPayload) -> None:
        """Push a job to the tail of the queue."""

    @abstractmethod
    def dequeue(self, timeout: int = 5) -> Optional[QueueJobPayload]:
        """
        Block up to *timeout* seconds waiting for a job.

        Returns ``None`` when no job arrives within the timeout window.
        The returned job is automatically added to the in-flight store so
        ``requeue_stale_jobs`` can recover it if the worker crashes.
        """

    @abstractmethod
    def ack(self, job_id: str) -> None:
        """Mark a job as successfully completed; remove from in-flight."""

    @abstractmethod
    def fail(self, job_id: str, error: str = "") -> None:
        """Mark a job as terminally failed; move to Dead Letter Queue."""

    # ── Optional extensions ────────────────────────────────────────────────

    def enqueue_delayed(self, payload: QueueJobPayload, delay_seconds: float) -> None:
        """
        Schedule a job for future execution after *delay_seconds*.

        Default implementation ignores the delay and enqueues immediately.
        Override in backends that support deferred scheduling.
        """
        self.enqueue(payload)

    def process_delayed_jobs(self) -> int:
        """
        Move jobs whose delay has elapsed into the main queue.

        Returns the number of jobs promoted.  Default: no-op (0).
        """
        return 0

    def requeue_stale_jobs(self, timeout_seconds: int = 300) -> int:
        """
        Re-enqueue in-flight jobs older than *timeout_seconds*.

        Recovers jobs whose workers crashed before calling ack/fail.
        Returns the number of jobs re-enqueued.  Default: no-op (0).
        """
        return 0

    def get_metrics(self) -> dict:
        """
        Return a dict with queue health metrics.

        Keys: queue_depth, in_flight_count, failed_jobs, delayed_jobs.
        Default: all zeros.
        """
        return {
            "queue_depth": 0,
            "in_flight_count": 0,
            "failed_jobs": 0,
            "delayed_jobs": 0,
        }


# ---------------------------------------------------------------------------
# Redis backend
# ---------------------------------------------------------------------------

class RedisQueueBackend(DistributedQueueBackend):
    """
    Redis-backed FIFO queue using LPUSH / BRPOP.

    BRPOP is atomic — only one worker receives each message regardless of how
    many worker processes are running.

    Key layout
    ----------
    ``aindy:jobs``          — main job list (LPUSH left / BRPOP right)
    ``aindy:jobs:inflight`` — hash { job_id → inflight_entry_json }
                              entry = {"payload": raw_json, "dequeued_at": iso_str}
    ``aindy:jobs:delayed``  — sorted set; score = execute_at Unix timestamp
    ``aindy:jobs:dead``     — dead letter list; each element is a DLQ entry JSON
    """

    # Lua script: atomically pop all delayed jobs with score <= now and push
    # to main queue.  Processes up to 100 items per call.
    _PROCESS_DELAYED_LUA = """
local ready = redis.call('ZRANGEBYSCORE', KEYS[1], '-inf', ARGV[1], 'LIMIT', 0, 100)
for _, v in ipairs(ready) do
    redis.call('LPUSH', KEYS[2], v)
    redis.call('ZREM', KEYS[1], v)
end
return #ready
"""

    def __init__(self, url: str, queue_name: str = QUEUE_NAME_DEFAULT) -> None:
        try:
            import redis  # type: ignore[import]
        except ImportError as exc:
            raise ImportError(
                "redis package is required for RedisQueueBackend. "
                "Install with: pip install redis"
            ) from exc
        self._redis = redis.from_url(url, decode_responses=True, socket_timeout=10)
        self._queue_name = queue_name
        self._inflight_key = f"{queue_name}:inflight"
        self._delayed_key = f"{queue_name}:delayed"
        self._dlq_key = f"{queue_name}:dead"
        self._process_delayed = self._redis.register_script(self._PROCESS_DELAYED_LUA)

    # ── Core operations ────────────────────────────────────────────────────

    def enqueue(self, payload: QueueJobPayload) -> None:
        raw = payload.to_json()
        self._redis.lpush(self._queue_name, raw)
        operation_name = getattr(payload, "operation_name", None) or payload.task_name
        logger.debug(
            "[Queue:redis] enqueued job_id=%s operation=%s idempotency_key=%s",
            payload.job_id, operation_name, payload.idempotency_key,
        )

    def dequeue(self, timeout: int = 5) -> Optional[QueueJobPayload]:
        result = self._redis.brpop(self._queue_name, timeout=timeout)
        if result is None:
            return None
        _, raw = result
        try:
            job = QueueJobPayload.from_json(raw)
        except Exception as exc:
            logger.error("[Queue:redis] deserialise failed: %s — raw=%r", exc, raw[:200])
            return None
        # Record in in-flight with timestamp for visibility-timeout recovery.
        inflight_entry = json.dumps({
            "payload": raw,
            "dequeued_at": datetime.now(timezone.utc).isoformat(),
        })
        self._redis.hset(self._inflight_key, job.job_id, inflight_entry)
        return job

    def ack(self, job_id: str) -> None:
        """Remove from in-flight — job completed successfully."""
        self._redis.hdel(self._inflight_key, job_id)
        logger.debug("[Queue:redis] ack job_id=%s", job_id)

    def fail(self, job_id: str, error: str = "") -> None:
        """
        Remove from in-flight and append to Dead Letter Queue.

        The DLQ entry preserves the original payload so it can be inspected
        and replayed by an operator.
        """
        inflight_raw = self._redis.hget(self._inflight_key, job_id)
        self._redis.hdel(self._inflight_key, job_id)

        # Build DLQ record.
        try:
            payload_raw = json.loads(inflight_raw or "{}").get("payload", "")
        except Exception:
            payload_raw = ""
        dlq_entry = json.dumps({
            "job_id": job_id,
            "payload_raw": payload_raw,
            "error": error,
            "failed_at": datetime.now(timezone.utc).isoformat(),
        })
        self._redis.lpush(self._dlq_key, dlq_entry)
        logger.warning(
            "[Queue:redis] fail→DLQ job_id=%s error=%s", job_id, error
        )

    # ── Delayed enqueue ────────────────────────────────────────────────────

    def enqueue_delayed(self, payload: QueueJobPayload, delay_seconds: float) -> None:
        """
        Schedule *payload* to be promoted to the main queue after *delay_seconds*.

        Uses a Redis sorted set with score = Unix timestamp at which the job
        should execute.  ``process_delayed_jobs()`` must be called periodically
        to promote ready jobs.
        """
        raw = payload.to_json()
        execute_at = datetime.now(timezone.utc).timestamp() + delay_seconds
        self._redis.zadd(self._delayed_key, {raw: execute_at})
        logger.debug(
            "[Queue:redis] delayed enqueue job_id=%s delay=%.1fs",
            payload.job_id, delay_seconds,
        )

    def process_delayed_jobs(self) -> int:
        """
        Promote all delayed jobs whose execute_at ≤ now into the main queue.

        Uses a Lua script for atomicity — a job is either fully promoted or
        not at all, preventing double-promotion across concurrent workers.
        Returns the number of jobs promoted.
        """
        now_ts = datetime.now(timezone.utc).timestamp()
        count = self._process_delayed(
            keys=[self._delayed_key, self._queue_name],
            args=[str(now_ts)],
        )
        if count:
            logger.info("[Queue:redis] promoted %d delayed jobs", count)
        return int(count)

    # ── Visibility timeout recovery ────────────────────────────────────────

    def requeue_stale_jobs(self, timeout_seconds: int = 300) -> int:
        """
        Scan the in-flight hash and re-enqueue any job dequeued more than
        *timeout_seconds* ago.

        Safe to call from multiple workers concurrently: the first ``HDEL``
        wins; subsequent calls see an empty inflight entry and skip.

        Returns the number of jobs re-enqueued.
        """
        now = datetime.now(timezone.utc)
        entries = self._redis.hgetall(self._inflight_key)
        requeued = 0
        for job_id, entry_raw in entries.items():
            try:
                entry = json.loads(entry_raw)
                dequeued_at = datetime.fromisoformat(entry["dequeued_at"])
                age_seconds = (now - dequeued_at).total_seconds()
                if age_seconds <= timeout_seconds:
                    continue
                # Attempt to claim the re-enqueue: delete from inflight first.
                removed = self._redis.hdel(self._inflight_key, job_id)
                if not removed:
                    continue  # Another worker got there first.
                self._redis.lpush(self._queue_name, entry["payload"])
                requeued += 1
                logger.info(
                    "[Queue:redis] requeued stale job_id=%s age=%.0fs",
                    job_id, age_seconds,
                )
            except Exception as exc:
                logger.warning(
                    "[Queue:redis] stale check failed job_id=%s: %s", job_id, exc
                )
        return requeued

    # ── Metrics ───────────────────────────────────────────────────────────

    def get_metrics(self) -> dict:
        """
        Return a snapshot of queue health.

        Keys
        ----
        queue_depth    — pending jobs in main queue
        in_flight_count — jobs currently being processed
        failed_jobs    — jobs in the Dead Letter Queue
        delayed_jobs   — jobs waiting for their delay to elapse
        """
        return {
            "queue_depth": self._redis.llen(self._queue_name),
            "in_flight_count": self._redis.hlen(self._inflight_key),
            "failed_jobs": self._redis.llen(self._dlq_key),
            "delayed_jobs": self._redis.zcard(self._delayed_key),
        }


# ---------------------------------------------------------------------------
# In-memory backend (tests / single-process dev)
# ---------------------------------------------------------------------------

class InMemoryQueueBackend(DistributedQueueBackend):
    """
    Thread-safe in-process FIFO queue backed by ``queue.Queue``.

    Implements all reliability features of ``RedisQueueBackend``:
    - In-flight tracking with timestamps (visibility timeout recovery)
    - Dead Letter Queue (in-process list)
    - Delayed enqueue via ``threading.Timer``
    - Full ``get_metrics()``

    Suitable for unit tests and single-process development without Redis.
    NOT usable across OS processes — items live in this process's heap only.
    """

    def __init__(self) -> None:
        self._q: queue.Queue[QueueJobPayload] = queue.Queue()

        # In-flight: { job_id → (payload, dequeued_at_utc) }
        self._inflight: dict[str, tuple[QueueJobPayload, datetime]] = {}
        self._inflight_lock = threading.Lock()

        # Dead Letter Queue
        self._dlq: list[dict] = []
        self._dlq_lock = threading.Lock()

        # Active delayed timers (kept to prevent GC before firing)
        self._timers: list[threading.Timer] = []
        self._timers_lock = threading.Lock()

    def enqueue(self, payload: QueueJobPayload) -> None:
        self._q.put(payload)
        operation_name = getattr(payload, "operation_name", None) or payload.task_name
        logger.debug(
            "[Queue:mem] enqueued job_id=%s operation=%s", payload.job_id, operation_name
        )

    def dequeue(self, timeout: int = 5) -> Optional[QueueJobPayload]:
        try:
            job = self._q.get(timeout=timeout)
        except queue.Empty:
            return None
        with self._inflight_lock:
            self._inflight[job.job_id] = (job, datetime.now(timezone.utc))
        return job

    def ack(self, job_id: str) -> None:
        """Remove from in-flight; job succeeded."""
        with self._inflight_lock:
            self._inflight.pop(job_id, None)
        logger.debug("[Queue:mem] ack job_id=%s", job_id)

    def fail(self, job_id: str, error: str = "") -> None:
        """Remove from in-flight and move to Dead Letter Queue."""
        with self._inflight_lock:
            entry = self._inflight.pop(job_id, None)
        with self._dlq_lock:
            self._dlq.append({
                "job_id": job_id,
                "payload": entry[0] if entry else None,
                "error": error,
                "failed_at": datetime.now(timezone.utc).isoformat(),
            })
        logger.warning("[Queue:mem] fail→DLQ job_id=%s error=%s", job_id, error)

    # ── Delayed enqueue ────────────────────────────────────────────────────

    def enqueue_delayed(self, payload: QueueJobPayload, delay_seconds: float) -> None:
        """Schedule enqueue after *delay_seconds* using a daemon Timer."""
        def _fire() -> None:
            self._q.put(payload)
            logger.debug("[Queue:mem] delayed enqueue fired job_id=%s", payload.job_id)

        t = threading.Timer(delay_seconds, _fire)
        t.daemon = True
        t.start()
        with self._timers_lock:
            # Prune completed timers to avoid memory growth.
            self._timers = [x for x in self._timers if x.is_alive()]
            self._timers.append(t)
        logger.debug(
            "[Queue:mem] delayed enqueue job_id=%s delay=%.1fs",
            payload.job_id, delay_seconds,
        )

    # process_delayed_jobs is a no-op: Timer fires automatically.

    # ── Visibility timeout recovery ────────────────────────────────────────

    def requeue_stale_jobs(self, timeout_seconds: int = 300) -> int:
        """Re-enqueue in-flight jobs older than *timeout_seconds*."""
        now = datetime.now(timezone.utc)
        to_requeue: list[tuple[str, QueueJobPayload]] = []
        with self._inflight_lock:
            for job_id, (job, dequeued_at) in list(self._inflight.items()):
                age = (now - dequeued_at).total_seconds()
                if age > timeout_seconds:
                    to_requeue.append((job_id, job))
            for job_id, _ in to_requeue:
                del self._inflight[job_id]
        for _, job in to_requeue:
            self._q.put(job)
            logger.info("[Queue:mem] requeued stale job_id=%s", job.job_id)
        return len(to_requeue)

    # ── Metrics ───────────────────────────────────────────────────────────

    def get_metrics(self) -> dict:
        with self._inflight_lock:
            inflight = len(self._inflight)
        with self._dlq_lock:
            dlq = len(self._dlq)
        return {
            "queue_depth": self._q.qsize(),
            "in_flight_count": inflight,
            "failed_jobs": dlq,
            "delayed_jobs": 0,  # Timers are fire-and-forget; no persistent count.
        }

    # ── Test helpers ──────────────────────────────────────────────────────

    def qsize(self) -> int:
        """Number of items currently waiting (for test assertions)."""
        return self._q.qsize()

    def get_dead_letters(self) -> list[dict]:
        """Return a copy of the DLQ (for test assertions)."""
        with self._dlq_lock:
            return list(self._dlq)

    def get_inflight_ids(self) -> list[str]:
        """Return current in-flight job IDs (for test assertions)."""
        with self._inflight_lock:
            return list(self._inflight.keys())


# ---------------------------------------------------------------------------
# Singleton factory
# ---------------------------------------------------------------------------

_QUEUE_INSTANCE: Optional[DistributedQueueBackend] = None
_QUEUE_LOCK = threading.Lock()


def get_queue(*, force_memory: bool = False) -> DistributedQueueBackend:
    """
    Return the module-level singleton queue backend.

    Selection order
    ---------------
    1. ``force_memory=True``           → fresh ``InMemoryQueueBackend`` (tests).
    2. ``TESTING=1`` / ``TEST_MODE=1`` → ``InMemoryQueueBackend`` (cached).
    3. ``REDIS_URL`` is set            → ``RedisQueueBackend``.
    4. Fallback                        → ``InMemoryQueueBackend`` with a warning.

    Call ``reset_queue()`` between tests to get a clean instance.
    """
    global _QUEUE_INSTANCE

    if force_memory:
        return InMemoryQueueBackend()

    if _QUEUE_INSTANCE is not None:
        return _QUEUE_INSTANCE

    with _QUEUE_LOCK:
        if _QUEUE_INSTANCE is not None:
            return _QUEUE_INSTANCE

        if os.getenv("TESTING", "false").lower() in {"1", "true", "yes"}:
            _QUEUE_INSTANCE = InMemoryQueueBackend()
            return _QUEUE_INSTANCE

        if os.getenv("TEST_MODE", "false").lower() in {"1", "true", "yes"}:
            _QUEUE_INSTANCE = InMemoryQueueBackend()
            return _QUEUE_INSTANCE

        redis_url = os.getenv("REDIS_URL")
        queue_name = os.getenv("AINDY_QUEUE_NAME", QUEUE_NAME_DEFAULT)

        if redis_url:
            _QUEUE_INSTANCE = RedisQueueBackend(url=redis_url, queue_name=queue_name)
            logger.info(
                "[Queue] Redis backend — url=%s queue=%s", redis_url, queue_name
            )
        else:
            exec_mode = os.getenv("EXECUTION_MODE", "thread").lower()
            if exec_mode == "distributed":
                raise RuntimeError(
                    "EXECUTION_MODE=distributed requires REDIS_URL to be set. "
                    "Jobs would be silently lost on process restart with an "
                    "in-memory queue. Either set REDIS_URL or switch to "
                    "EXECUTION_MODE=thread for single-process execution."
                )
            logger.warning(
                "[Queue] REDIS_URL not set — using in-memory queue. "
                "Multi-process distributed execution requires Redis."
            )
            _QUEUE_INSTANCE = InMemoryQueueBackend()

        return _QUEUE_INSTANCE


def reset_queue() -> None:
    """
    Reset the singleton to None.

    Call this in test teardown (or after changing ``REDIS_URL``) to force
    re-initialisation on the next ``get_queue()`` call.
    """
    global _QUEUE_INSTANCE
    with _QUEUE_LOCK:
        _QUEUE_INSTANCE = None
