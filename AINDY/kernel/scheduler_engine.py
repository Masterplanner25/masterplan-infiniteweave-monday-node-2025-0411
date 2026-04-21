"""
Scheduler Engine — A.I.N.D.Y. OS Execution Scheduler

Priority-based, tenant-fair execution scheduler for A.I.N.D.Y. ExecutionUnits.

Architecture
------------
Three priority queues (high → normal → low).  Within each queue, a
round-robin cursor ensures no single tenant monopolises the queue.

When the ResourceManager denies an execution (quota exceeded, concurrency
limit), PersistentFlowRunner enqueues the unit here instead of executing
immediately.  An APScheduler heartbeat calls ``schedule()`` periodically
to drain the queues.

WAIT/RESUME integration
-----------------------
When a FlowRun enters WAIT state, its run_id is stored via
``register_wait(run_id, wait_for_event)``.  When the event fires,
``notify_event(event_type)`` matches registered ``_waiting`` entries by
``wait_condition.event_name``, applies correlation-id filtering, and
re-enqueues matched runs at their registered priority.

Usage
-----
    from AINDY.kernel.scheduler_engine import get_scheduler_engine, ScheduledItem

    se = get_scheduler_engine()

    item = ScheduledItem(
        execution_unit_id="eu-abc",
        tenant_id="user-123",
        priority="normal",
        run_callback=lambda: runner.resume(run_id),
        run_id="run-uuid",
    )
    se.enqueue(item)
    se.schedule()  # process one batch

Priority constants
------------------
    PRIORITY_HIGH   = "high"
    PRIORITY_NORMAL = "normal"
    PRIORITY_LOW    = "low"
"""
from __future__ import annotations

import logging
import os
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Optional

from AINDY.kernel.resource_manager import get_resource_manager

logger = logging.getLogger(__name__)

# ── Priority levels ───────────────────────────────────────────────────────────

PRIORITY_HIGH = "high"
PRIORITY_NORMAL = "normal"
PRIORITY_LOW = "low"

PRIORITY_ORDER = (PRIORITY_HIGH, PRIORITY_NORMAL, PRIORITY_LOW)

# How many items to drain per schedule() call (prevents starvation of caller)
MAX_PER_SCHEDULE_CYCLE = 10


def _int_env(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, default))
    except (TypeError, ValueError):
        return default


_MAX_PRE_REHYDRATION_BUFFER = _int_env(
    "AINDY_SCHEDULER_PRE_REHYDRATION_BUFFER",
    1000,
)


def _get_session_factory():
    from AINDY.db.database import SessionLocal

    return SessionLocal


def _get_instance_id() -> str:
    return os.getenv("HOSTNAME", "local")


def _emit_dispatch_failure(item: "ScheduledItem", exc: Exception) -> None:
    """Log a structured dispatch failure for alerting. Non-fatal."""
    try:
        logger.critical(
            "[Scheduler] DISPATCH_FAILURE run_id=%s eu=%s tenant=%s type=%s retries=%d exc=%r",
            item.run_id,
            item.execution_unit_id,
            item.tenant_id,
            item.eu_type,
            item.retry_count,
            str(exc),
        )
    except Exception:
        pass


def _load_wait_entry_from_db(run_id: str):
    """Load WaitingFlowRun from DB. Returns None if not found."""
    try:
        from AINDY.db import SessionLocal
        from AINDY.db.models.waiting_flow_run import WaitingFlowRun

        with SessionLocal() as db:
            return (
                db.query(WaitingFlowRun)
                .filter(WaitingFlowRun.run_id == str(run_id))
                .first()
            )
    except Exception:
        logger.warning(
            "_load_wait_entry_from_db failed for run_id=%s",
            run_id,
            exc_info=True,
        )
        return None


def _cross_instance_resume(
    engine: "SchedulerEngine",
    event_type: str,
    correlation_id: str | None,
    skip_run_ids: set[str],
) -> int:
    """Resume flows registered on other instances via Redis wait specs."""
    try:
        from AINDY.kernel.redis_wait_registry import RedisWaitRegistry
        from AINDY.kernel.resume_spec import build_callback_from_spec
        from AINDY.kernel.event_bus import get_redis_client

        registry = RedisWaitRegistry(get_redis_client())
        if registry._redis is None:
            return 0

        resumed = 0
        all_specs = registry.get_all_specs()
        for run_id, spec in all_specs.items():
            if run_id in skip_run_ids:
                continue

            with engine._lock:
                if run_id in engine._waiting:
                    continue

            wait_entry = _load_wait_entry_from_db(run_id)
            if wait_entry is None:
                continue
            if getattr(wait_entry, "event_type", None) != event_type:
                continue

            wait_corr = getattr(wait_entry, "correlation_id", None)
            if correlation_id and wait_corr != correlation_id:
                continue

            try:
                callback = build_callback_from_spec(spec)
            except Exception:
                logger.warning(
                    "Failed to build callback for run_id=%s",
                    run_id,
                    exc_info=True,
                )
                continue

            if not registry.unregister_if_exists(run_id):
                continue

            engine._enqueue_resume(
                run_id,
                callback,
                {
                    "priority": getattr(wait_entry, "priority", PRIORITY_NORMAL) or PRIORITY_NORMAL,
                    "tenant_id": getattr(spec, "tenant_id", None) or "system",
                    "eu_id": getattr(wait_entry, "eu_id", None) or spec.eu_id,
                    "correlation_id": wait_corr,
                    "trace_id": None,
                    "eu_type": getattr(spec, "eu_type", None) or "flow",
                },
            )
            resumed += 1
            logger.info(
                "Cross-instance resume claimed run_id=%s on this instance",
                run_id,
            )

        return resumed
    except Exception:
        logger.warning(
            "_cross_instance_resume failed for event_type=%s",
            event_type,
            exc_info=True,
        )
        return 0


def _cross_instance_tick(engine: "SchedulerEngine") -> int:
    """Check Redis for due time-based waits registered on other instances."""
    try:
        from datetime import datetime, timezone

        from AINDY.kernel.redis_wait_registry import RedisWaitRegistry
        from AINDY.kernel.resume_spec import build_callback_from_spec
        from AINDY.kernel.event_bus import get_redis_client

        registry = RedisWaitRegistry(get_redis_client())
        if registry._redis is None:
            return 0

        now = datetime.now(timezone.utc)
        fired = 0
        all_specs = registry.get_all_specs()
        for run_id, spec in all_specs.items():
            with engine._lock:
                if run_id in engine._waiting:
                    continue

            wait_entry = _load_wait_entry_from_db(run_id)
            if wait_entry is None:
                continue

            timeout_at = getattr(wait_entry, "timeout_at", None)
            if timeout_at is None:
                continue
            if getattr(timeout_at, "tzinfo", None) is None:
                timeout_at = timeout_at.replace(tzinfo=timezone.utc)
            if timeout_at > now:
                continue

            if not registry.unregister_if_exists(run_id):
                continue

            try:
                callback = build_callback_from_spec(spec)
            except Exception:
                logger.warning(
                    "[Scheduler] tick: build_callback failed run_id=%s",
                    run_id,
                    exc_info=True,
                )
                continue

            engine._enqueue_resume(
                run_id,
                callback,
                {
                    "eu_id": getattr(wait_entry, "eu_id", None) or run_id,
                    "tenant_id": getattr(wait_entry, "tenant_id", None)
                    or getattr(spec, "tenant_id", None)
                    or "system",
                    "priority": getattr(wait_entry, "priority", None) or PRIORITY_NORMAL,
                    "eu_type": getattr(spec, "eu_type", None) or "flow",
                },
            )
            engine._delete_wait_backup(run_id)
            logger.info("[Scheduler] cross-instance time-wait fired run_id=%s", run_id)
            fired += 1

        return fired
    except Exception:
        logger.warning("[Scheduler] cross-instance tick failed", exc_info=True)
        return 0


# ── Resumed EU stub ───────────────────────────────────────────────────────────

@dataclass
class _ResumedEUStub:
    """
    Lightweight duck-typed proxy passed to ExecutionDispatcher.dispatch() when
    a scheduler item is being resumed.

    ``dispatch()`` only reads ``.type``, ``.priority``, ``.extra``, and ``.id``
    (the last is for logging only).  This stub satisfies all four without
    requiring a live DB query.
    """

    id: str           # eu_id — for dispatcher logging
    type: str         # eu_type — drives INLINE vs ASYNC decision in _decide_mode
    priority: str     # mirrors ScheduledItem.priority
    extra: dict = field(default_factory=dict)


# ── ScheduledItem ─────────────────────────────────────────────────────────────

@dataclass
class ScheduledItem:
    """A single execution unit waiting to be scheduled.

    Attributes:
        execution_unit_id: The ExecutionUnit ID (for resource tracking).
        tenant_id:         Owning tenant (for round-robin fairness).
        priority:          One of PRIORITY_HIGH / PRIORITY_NORMAL / PRIORITY_LOW.
        run_callback:      Zero-arg callable executed when this item is dequeued.
        run_id:            Optional FlowRun / AgentRun ID (for WAIT/RESUME).
        eu_type:           ExecutionUnit type string (flow/agent/job/nodus; task is a legacy operation label).
                           Used by schedule() to build _ResumedEUStub for dispatch().
        enqueued_at_seq:   Monotone sequence number assigned on enqueue (for FIFO
                           within same tenant+priority).
    """

    execution_unit_id: str
    tenant_id: str
    priority: str
    run_callback: Callable[[], None]
    run_id: Optional[str] = None
    eu_type: str = "flow"
    enqueued_at_seq: int = field(default=0, compare=False)
    retry_count: int = field(default=0, compare=False)
    max_retries: int = field(default=2, compare=False)

    def __post_init__(self) -> None:
        if self.priority not in PRIORITY_ORDER:
            raise ValueError(
                f"Invalid priority {self.priority!r}; must be one of {PRIORITY_ORDER}"
            )
        if self.max_retries == 2:
            self.max_retries = _int_env("AINDY_SCHEDULER_MAX_DISPATCH_RETRIES", 2)


# ── SchedulerEngine ───────────────────────────────────────────────────────────

class SchedulerEngine:
    """Priority-based, tenant-fair execution scheduler.

    Thread-safe.  All public methods acquire ``_lock`` before mutating state.

    Queue semantics
    ---------------
    * ``deque_next()`` always checks HIGH first, then NORMAL, then LOW.
    * Within each priority level, a round-robin cursor rotates across tenants
      so one active tenant cannot starve others.
    * ``schedule()`` drains up to ``MAX_PER_SCHEDULE_CYCLE`` items per call.

    WAIT/RESUME
    -----------
    ``register_wait(run_id, wait_for_event)`` records that a run is sleeping.
    ``notify_event(event_type)`` re-enqueues all runs waiting for that event.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # priority → deque[ScheduledItem]
        self._queues: dict[str, deque[ScheduledItem]] = {
            p: deque() for p in PRIORITY_ORDER
        }
        # round-robin cursor: priority → last-served tenant_id
        self._rr_cursor: dict[str, str | None] = {p: None for p in PRIORITY_ORDER}
        # WAIT registry: run_id → {wait_for, tenant_id, eu_id, callback}
        self._waiting: dict[str, dict] = {}
        # Monotone enqueue counter
        self._seq: int = 0
        # Stats
        self._total_enqueued: int = 0
        self._total_dispatched: int = 0
        self._total_dropped: int = 0
        self._last_stale_wait_check_monotonic: float = 0.0
        # Rehydration barrier: set after _waiting is fully restored at startup
        self._rehydration_complete = threading.Event()
        # Bounded startup buffer for events received before rehydration finishes.
        # Default 1000 keeps normal startup bursts safe without unbounded growth.
        self._pre_rehydration_buffer: list[tuple[str, str | None]] = []

    def get_metrics_snapshot(self) -> dict:
        """Return current queue depths and waiting count for Prometheus gauges."""
        with self._lock:
            return {
                "queue_depth": {p: len(self._queues[p]) for p in PRIORITY_ORDER},
                "waiting_count": len(self._waiting),
            }

    def mark_rehydration_complete(self) -> None:
        """Signal that WAIT rehydration has finished; unblocks buffered events."""
        self._rehydration_complete.set()
        with self._lock:
            buffered = list(self._pre_rehydration_buffer)
            self._pre_rehydration_buffer.clear()

        for event_type, correlation_id in buffered:
            logger.info(
                "[Scheduler] replaying buffered event post-rehydration: %s",
                event_type,
            )
            try:
                self.notify_event(
                    event_type,
                    correlation_id=correlation_id,
                    broadcast=False,
                )
            except Exception:
                logger.warning(
                    "[Scheduler] buffered event replay failed event=%s corr=%s",
                    event_type,
                    correlation_id,
                    exc_info=True,
                )

    def is_rehydrated(self) -> bool:
        """Return True if rehydration has completed."""
        return self._rehydration_complete.is_set()

    def _enqueue_resume(
        self,
        run_id: str,
        callback: Callable[[], None],
        entry: dict,
    ) -> None:
        item = ScheduledItem(
            execution_unit_id=str(entry.get("eu_id") or ""),
            tenant_id=str(entry.get("tenant_id") or "system"),
            priority=entry.get("priority") or PRIORITY_NORMAL,
            run_callback=callback,
            run_id=run_id,
            eu_type=entry.get("eu_type", "flow"),
        )
        self.enqueue(item)

    def _unregister_redis_wait(self, run_id: str) -> None:
        try:
            from AINDY.kernel.redis_wait_registry import RedisWaitRegistry
            from AINDY.kernel.event_bus import get_redis_client

            RedisWaitRegistry(get_redis_client()).unregister(str(run_id))
        except Exception:
            logger.debug(
                "[Scheduler] Redis wait unregister skipped for run=%s",
                run_id,
                exc_info=True,
            )

    def _check_stale_waits(self) -> int:
        """Throttle orphaned wait recovery to the watchdog interval."""
        try:
            from AINDY.config import settings
        except Exception:
            interval_seconds = 120.0
        else:
            interval_seconds = max(
                0.0,
                float(getattr(settings, "AINDY_WATCHDOG_INTERVAL_MINUTES", 2)) * 60.0,
            )

        now = time.monotonic()
        if interval_seconds > 0 and (now - self._last_stale_wait_check_monotonic) < interval_seconds:
            return 0

        self._last_stale_wait_check_monotonic = now

        db = None
        try:
            SessionLocal = _get_session_factory()
            db = SessionLocal()
            return self.recover_orphaned_waits(db)
        except Exception as exc:
            logger.debug("[Scheduler] orphaned-wait recovery skipped: %s", exc)
            return 0
        finally:
            if db is not None:
                try:
                    db.close()
                except Exception:
                    pass

    def recover_orphaned_waits(self, db) -> int:
        """Re-register WaitingFlowRun rows missing from this instance's _waiting registry."""
        try:
            from AINDY.core.flow_run_rehydration import rehydrate_waiting_flow_runs
            from AINDY.db.models.waiting_flow_run import WaitingFlowRun
        except Exception as exc:
            logger.warning("[Scheduler] orphaned-wait recovery init failed: %s", exc)
            return 0

        with self._lock:
            local_wait_ids = {str(run_id) for run_id in self._waiting.keys()}

        try:
            query = db.query(WaitingFlowRun)
            if local_wait_ids:
                query = query.filter(~WaitingFlowRun.run_id.in_(local_wait_ids))
            orphan_rows = query.all()
        except Exception as exc:
            logger.warning("[Scheduler] orphaned-wait recovery query failed: %s", exc)
            return 0

        orphan_run_ids = {
            str(row.run_id)
            for row in orphan_rows
            if getattr(row, "run_id", None)
        }
        if not orphan_run_ids:
            logger.info("[Scheduler] orphaned-wait recovery found 0 missing wait(s)")
            return 0

        try:
            recovered = rehydrate_waiting_flow_runs(db, run_ids=orphan_run_ids)
        except TypeError:
            recovered = rehydrate_waiting_flow_runs(db)
        except Exception as exc:
            logger.warning("[Scheduler] orphaned-wait recovery failed: %s", exc)
            return 0

        logger.info(
            "[Scheduler] orphaned-wait recovery registered %d wait(s)",
            recovered,
        )
        return recovered

    # ── Enqueue ───────────────────────────────────────────────────────────────

    def enqueue(self, item: ScheduledItem) -> None:
        """Add *item* to the appropriate priority queue.

        Args:
            item: The ScheduledItem to schedule.

        Raises:
            ValueError: If ``item.priority`` is invalid.
        """
        with self._lock:
            self._seq += 1
            item.enqueued_at_seq = self._seq
            self._queues[item.priority].append(item)
            self._total_enqueued += 1
            logger.debug(
                "[Scheduler] enqueued eu=%s tenant=%s priority=%s seq=%d",
                item.execution_unit_id, item.tenant_id, item.priority, self._seq,
            )

    # ── Dequeue ───────────────────────────────────────────────────────────────

    def dequeue_next(self) -> ScheduledItem | None:
        """Dequeue the next executable item respecting priority and fairness.

        Priority: HIGH > NORMAL > LOW.
        Within each priority: rotate across tenants (round-robin).

        Returns:
            The next ScheduledItem, or None if all queues are empty.
        """
        with self._lock:
            for priority in PRIORITY_ORDER:
                q = self._queues[priority]
                if not q:
                    continue

                # Round-robin: if the head item belongs to the same tenant
                # as the last served tenant at this priority, rotate once
                # to give other tenants a chance.
                last_tenant = self._rr_cursor[priority]
                if last_tenant is not None and len(q) > 1:
                    head = q[0]
                    if head.tenant_id == last_tenant:
                        # Rotate: move head to tail, try next tenant
                        q.rotate(-1)

                item = q.popleft()
                self._rr_cursor[priority] = item.tenant_id
                self._total_dispatched += 1
                return item

        return None

    # ── Schedule cycle ────────────────────────────────────────────────────────

    def schedule(self) -> int:
        """Drain up to MAX_PER_SCHEDULE_CYCLE items and execute their callbacks.

        Every resumed item is routed through ``ExecutionDispatcher.dispatch()``
        so the INLINE vs ASYNC decision is made by the dispatcher, not hardcoded
        here.  Heavy EU types (flow, agent, nodus) go ASYNC when async execution
        is enabled; lightweight types (job and legacy task labels) run INLINE on this thread.

        Checks ResourceManager before each execution:
        - If ``can_execute`` returns False, the item is re-enqueued at its
          original priority (it will be tried again next cycle).

        Returns:
            Number of items actually dispatched (not re-enqueued) this cycle.
        """
        # Lazy import — avoids circular dependency (kernel → core) at module load.
        from AINDY.core.execution_dispatcher import dispatch as _dispatch

        self._check_stale_waits()

        # Fire any time-based waits whose trigger_at has passed before
        # draining the queues, so they are available in this same cycle.
        self.tick_time_waits()

        rm = get_resource_manager()
        dispatched = 0
        saturated_tenants: set[str] = set()
        retry_items: list[ScheduledItem] = []
        processed = 0
        saturated_skips = 0

        while processed < MAX_PER_SCHEDULE_CYCLE:
            item = self.dequeue_next()
            if item is None:
                break

            if item.tenant_id in saturated_tenants:
                with self._lock:
                    self._queues[item.priority].appendleft(item)
                    self._total_dispatched -= 1
                    queue_size = sum(len(q) for q in self._queues.values())
                saturated_skips += 1
                if saturated_skips >= queue_size:
                    break
                continue

            saturated_skips = 0
            processed += 1
            ok, reason = rm.can_execute(item.tenant_id, item.execution_unit_id)
            if not ok:
                # Re-enqueue — resource unavailable; try next cycle
                with self._lock:
                    self._queues[item.priority].appendleft(item)
                    self._total_dispatched -= 1  # undo dequeue count
                saturated_tenants.add(item.tenant_id)
                logger.debug(
                    "[Scheduler] deferred eu=%s tenant=%s reason=%s",
                    item.execution_unit_id,
                    item.tenant_id,
                    reason,
                )
                continue

            # Build a lightweight stub so dispatch() can make the INLINE/ASYNC
            # decision without a live DB query.
            _stub = _ResumedEUStub(
                id=item.execution_unit_id,
                type=item.eu_type,
                priority=item.priority,
            )
            _context = {
                "eu_id": item.execution_unit_id,
                "run_id": item.run_id,
                "source": "scheduler.resume",
            }
            try:
                _dispatch(_stub, item.run_callback, _context)
                dispatched += 1
                logger.debug(
                    "[Scheduler] dispatched eu=%s type=%s priority=%s",
                    item.execution_unit_id, item.eu_type, item.priority,
                )
            except Exception as exc:
                if item.retry_count < item.max_retries:
                    item.retry_count += 1
                    logger.warning(
                        "[Scheduler] dispatch failed eu=%s (attempt %d/%d), re-enqueueing: %s",
                        item.execution_unit_id,
                        item.retry_count,
                        item.max_retries + 1,
                        exc,
                    )
                    item.priority = PRIORITY_LOW
                    retry_items.append(item)
                else:
                    logger.error(
                        "[Scheduler] dispatch PERMANENTLY failed eu=%s after %d attempts: %s",
                        item.execution_unit_id,
                        item.retry_count + 1,
                        exc,
                    )
                    with self._lock:
                        self._total_dropped += 1
                    _emit_dispatch_failure(item, exc)

        for item in retry_items:
            self.enqueue(item)

        return dispatched

    # ── WAIT / RESUME ─────────────────────────────────────────────────────────

    def register_wait(
        self,
        run_id: str,
        wait_for_event: str,
        tenant_id: str,
        eu_id: str,
        resume_callback: Callable[[], None],
        priority: str = PRIORITY_NORMAL,
        correlation_id: str | None = None,
        trace_id: str | None = None,
        eu_type: str = "flow",
        wait_condition=None,  # WaitCondition | None
    ) -> None:
        """Register a run that is waiting for a condition (event, time, external).

        When the condition is satisfied — by ``notify_event(event_type)`` for
        event/external conditions, or by ``tick_time_waits()`` for time-based
        conditions — this run is re-enqueued and routed through
        ExecutionDispatcher.

        This is the single authority for all WAIT registrations.

        Args:
            run_id:           Unique key (FlowRun ID for flows, eu_id for generic).
            wait_for_event:   Event name used for event/external matching.
            tenant_id:        Owning tenant.
            eu_id:            ExecutionUnit ID.
            resume_callback:  Zero-arg callable executed when resumed.
            priority:         Queue priority on resume (default NORMAL).
            correlation_id:   Propagated correlation chain ID (optional).
            trace_id:         Request trace ID for observability (optional).
            eu_type:          ExecutionUnit type — drives INLINE vs ASYNC.
            wait_condition:   ``WaitCondition`` instance (or None).  When
                              absent, defaults to an event-type condition
                              keyed on ``wait_for_event``.
        """
        # Serialise WaitCondition to a plain dict for in-memory storage.
        # Fall back to a minimal event-type condition if not supplied.
        if wait_condition is not None:
            try:
                wc_dict = wait_condition.to_dict()
            except AttributeError:
                wc_dict = dict(wait_condition) if isinstance(wait_condition, dict) else None
        else:
            wc_dict = {
                "type": "event",
                "event_name": wait_for_event,
                "trigger_at": None,
                "correlation_id": correlation_id,
            }

        with self._lock:
            self._waiting[str(run_id)] = {
                "wait_for": wait_for_event,
                "tenant_id": tenant_id,
                "eu_id": eu_id,
                "callback": resume_callback,
                "priority": priority,
                "correlation_id": correlation_id,
                "trace_id": trace_id,
                "eu_type": eu_type,
                "wait_condition": wc_dict,
            }
        try:
            from AINDY.kernel.resume_spec import RESUME_HANDLER_EU, ResumeSpec
            from AINDY.kernel.redis_wait_registry import RedisWaitRegistry
            from AINDY.kernel.event_bus import get_redis_client

            spec = ResumeSpec(
                handler=RESUME_HANDLER_EU,
                eu_id=str(eu_id),
                tenant_id=str(tenant_id),
                run_id=str(run_id),
                eu_type=eu_type,
            )
            RedisWaitRegistry(get_redis_client()).register(str(run_id), spec)
        except Exception:
            logger.debug("[Scheduler] Redis wait registration skipped", exc_info=True)
        self._persist_wait_backup(str(run_id))
        logger.debug(
            "[Scheduler] registered wait run=%s event=%s eu=%s type=%s trace=%s cond_type=%s",
            run_id, wait_for_event, eu_id, eu_type, trace_id,
            (wc_dict or {}).get("type"),
        )

    def notify_event(
        self,
        event_type: str,
        *,
        correlation_id: str | None = None,
        broadcast: bool = True,
    ) -> int:
        """Re-enqueue all waiting runs whose wait_condition matches *event_type*.

        Called by the event system after each successful emission so that
        event-triggered WAIT conditions are satisfied immediately — no polling.

        Matching rules
        --------------
        An entry is resumed when ALL of the following hold:

        1. **Event-name match** — one of:
           - ``wait_condition.type`` is ``"event"`` or ``"external"`` AND
             ``wait_condition.event_name`` equals ``event_type``  (structured).
           - OR ``entry["wait_for"]`` equals ``event_type``  (legacy fallback for
             entries registered before WaitCondition was available).

        2. **Correlation-id filter** (applied only when *both* sides are non-empty):
           ``entry["correlation_id"]`` must equal the emitted event's
           ``correlation_id``.  When either side is absent the filter is not
           applied — unbound waits resume on any matching event.

        Duplicate protection
        --------------------
        Matched entries are deleted under ``_lock`` before any enqueue so a
        run can never be resumed twice for the same event, even under concurrent
        ``notify_event`` calls.

        Distributed broadcast
        ---------------------
        When ``broadcast=True`` (default), the event is published to the
        Redis event bus after the local scan completes so that all other
        instances can wake flows registered in their own ``_waiting`` dicts.
        Set ``broadcast=False`` when called from the event-bus subscriber
        to prevent infinite re-publication.

        Args:
            event_type:     The event type that was just emitted.
            correlation_id: Optional correlation chain ID from the emitted event.
            broadcast:      Publish to distributed event bus (default True).
                            Pass False when invoked from the event-bus subscriber.

        Returns:
            Number of runs re-enqueued locally.
        """
        if not self._rehydration_complete.is_set():
            with self._lock:
                if len(self._pre_rehydration_buffer) >= _MAX_PRE_REHYDRATION_BUFFER:
                    logger.error(
                        "[Scheduler] pre-rehydration buffer full (%d); event %r dropped",
                        _MAX_PRE_REHYDRATION_BUFFER,
                        event_type,
                    )
                    return 0
                self._pre_rehydration_buffer.append((event_type, correlation_id))
            logger.debug(
                "[Scheduler] buffered event pre-rehydration: %s corr=%s",
                event_type,
                correlation_id,
            )
            return 0

        to_resume: list[tuple[str, dict]] = []

        with self._lock:
            for run_id, entry in list(self._waiting.items()):
                # ── Event-name matching ───────────────────────────────────
                wc = entry.get("wait_condition") or {}
                wc_type = wc.get("type")
                wc_event = wc.get("event_name")

                # Time-based waits are only fired by tick_time_waits(), never here.
                if wc_type == "time":
                    continue

                if wc_event:
                    # Structured WaitCondition — match on event_name
                    if wc_type not in ("event", "external"):
                        continue
                    if wc_event != event_type:
                        continue
                else:
                    # Legacy fallback — match directly on wait_for
                    if entry.get("wait_for") != event_type:
                        continue

                # ── Correlation-id filter ─────────────────────────────────
                entry_corr = entry.get("correlation_id") or None
                emit_corr = correlation_id or None
                if entry_corr and emit_corr and entry_corr != emit_corr:
                    # Both present and mismatched — skip (cross-tenant guard)
                    continue

                to_resume.append((run_id, entry))

            # Delete under the same lock — prevents duplicate resume
            for run_id, _ in to_resume:
                del self._waiting[run_id]
                self._unregister_redis_wait(run_id)

        for run_id, entry in to_resume:
            self._enqueue_resume(run_id, entry["callback"], entry)
            logger.info(
                "[Scheduler] event-resumed run=%s event=%s type=%s priority=%s",
                run_id, event_type, entry.get("eu_type", "flow"), entry["priority"],
            )
            self._delete_wait_backup(run_id)

        cross_resumed = _cross_instance_resume(
            self,
            event_type,
            correlation_id,
            skip_run_ids={run_id for run_id, _ in to_resume},
        )

        # ── Distributed broadcast ─────────────────────────────────────────────
        # Publish to the Redis event bus so all other instances can wake flows
        # registered in their own _waiting dicts.  broadcast=False when called
        # from the subscriber itself, preventing infinite re-publication.
        # Non-fatal: a failing publish never interrupts local scheduling.
        if broadcast:
            try:
                from AINDY.kernel.event_bus import get_event_bus  # noqa: PLC0415
                get_event_bus().publish(event_type, correlation_id=correlation_id)
            except Exception as _bus_exc:
                logger.debug(
                    "[Scheduler] event bus publish failed (non-fatal): %s", _bus_exc
                )

        return len(to_resume) + cross_resumed

    def tick_time_waits(self) -> int:
        """Re-enqueue all time-based waits whose ``trigger_at`` has passed.

        Called at the start of each ``schedule()`` cycle.  Scans ``_waiting``
        for entries whose ``wait_condition.type == "time"`` and whose
        ``trigger_at`` is at or before ``now(UTC)``.

        Returns:
            Number of runs re-enqueued.
        """
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        to_fire: list[tuple[str, dict]] = []

        with self._lock:
            for run_id, entry in list(self._waiting.items()):
                wc = entry.get("wait_condition") or {}
                if wc.get("type") != "time":
                    continue
                raw_trigger = wc.get("trigger_at")
                if raw_trigger is None:
                    continue
                # Parse ISO string if needed
                if isinstance(raw_trigger, str):
                    try:
                        trigger_dt = datetime.fromisoformat(raw_trigger)
                        if trigger_dt.tzinfo is None:
                            trigger_dt = trigger_dt.replace(tzinfo=timezone.utc)
                    except ValueError:
                        continue
                elif isinstance(raw_trigger, datetime):
                    trigger_dt = raw_trigger
                    if trigger_dt.tzinfo is None:
                        trigger_dt = trigger_dt.replace(tzinfo=timezone.utc)
                else:
                    continue

                if trigger_dt <= now:
                    to_fire.append((run_id, entry))

            for run_id, _ in to_fire:
                del self._waiting[run_id]
                self._unregister_redis_wait(run_id)

        for run_id, entry in to_fire:
            self._enqueue_resume(run_id, entry["callback"], entry)
            logger.info(
                "[Scheduler] time-wait fired run=%s eu=%s priority=%s",
                run_id, entry["eu_id"], entry["priority"],
            )
            self._delete_wait_backup(run_id)

        return len(to_fire) + _cross_instance_tick(self)

    def scan_expired_waits(self) -> int:
        """Compatibility alias for scanning ready time-based waits."""
        return self.tick_time_waits()

    def cleanup_stale_waits(self) -> int:
        """Remove waiting entries whose FlowRun/EU is no longer in waiting status."""
        with self._lock:
            run_ids = list(self._waiting.keys())

        if not run_ids:
            return 0

        try:
            import uuid

            from AINDY.db.database import SessionLocal
            from AINDY.db.models.execution_unit import ExecutionUnit
            from AINDY.db.models.flow_run import FlowRun

            eu_query_ids: list[uuid.UUID] = []
            for run_id in run_ids:
                try:
                    eu_query_ids.append(uuid.UUID(str(run_id)))
                except (TypeError, ValueError, AttributeError):
                    continue

            with SessionLocal() as db:
                waiting_flow_ids = {
                    str(flow_id)
                    for (flow_id,) in (
                        db.query(FlowRun.id)
                        .filter(
                            FlowRun.id.in_(run_ids),
                            FlowRun.status == "waiting",
                        )
                        .all()
                    )
                }
                waiting_eu_ids = set()
                if eu_query_ids:
                    waiting_eu_ids = {
                        str(eu_id)
                        for (eu_id,) in (
                            db.query(ExecutionUnit.id)
                            .filter(
                                ExecutionUnit.id.in_(eu_query_ids),
                                ExecutionUnit.status == "waiting",
                            )
                            .all()
                        )
                    }
        except Exception:
            logger.warning("[Scheduler] cleanup_stale_waits DB query failed", exc_info=True)
            return 0

        active_run_ids = waiting_flow_ids | waiting_eu_ids
        stale = [run_id for run_id in run_ids if run_id not in active_run_ids]

        for run_id in stale:
            with self._lock:
                self._waiting.pop(run_id, None)
            self._delete_wait_backup(run_id)
            logger.info("[Scheduler] evicted stale wait run_id=%s", run_id)

        return len(stale)

    def peek_matching_run_ids(
        self,
        event_type: str,
        *,
        correlation_id: str | None = None,
    ) -> list[str]:
        """Return the run_ids that *would* be resumed by notify_event().

        Read-only scan — no entries are deleted or enqueued.  Applies the
        exact same matching predicate as ``notify_event()`` so callers can
        pre-populate state (e.g. inject event payload into FlowRun.state)
        before the scheduler fires.

        Must be called *before* ``notify_event()`` for the same event, since
        ``notify_event()`` removes matched entries from ``_waiting``.

        Matching rules mirror ``notify_event()``:
        - ``wait_condition.type`` must NOT be ``"time"``
        - event name must match (structured or legacy fallback)
        - correlation_id filter applied when both sides are non-empty

        Args:
            event_type:     The event type about to be emitted.
            correlation_id: Optional correlation chain ID for scoping.

        Returns:
            List of run_id strings (FlowRun IDs and/or eu_ids) that match.
        """
        matched: list[str] = []
        with self._lock:
            for run_id, entry in self._waiting.items():
                wc = entry.get("wait_condition") or {}
                wc_type = wc.get("type")
                wc_event = wc.get("event_name")

                if wc_type == "time":
                    continue

                if wc_event:
                    if wc_type not in ("event", "external"):
                        continue
                    if wc_event != event_type:
                        continue
                else:
                    if entry.get("wait_for") != event_type:
                        continue

                entry_corr = entry.get("correlation_id") or None
                emit_corr = correlation_id or None
                if entry_corr and emit_corr and entry_corr != emit_corr:
                    continue

                matched.append(run_id)
        return matched

    def waiting_for(self, run_id: str) -> str | None:
        """Return the event type a run is waiting for, or None."""
        with self._lock:
            entry = self._waiting.get(str(run_id))
            return entry["wait_for"] if entry else None

    # ── Stats & introspection ─────────────────────────────────────────────────

    def queue_depth(self) -> dict[str, int]:
        """Return the number of items in each priority queue."""
        with self._lock:
            return {p: len(q) for p, q in self._queues.items()}

    def stats(self) -> dict:
        """Return scheduler statistics snapshot."""
        with self._lock:
            return {
                "queues": {p: len(q) for p, q in self._queues.items()},
                "waiting": len(self._waiting),
                "total_enqueued": self._total_enqueued,
                "total_dispatched": self._total_dispatched,
                "total_dropped": self._total_dropped,
            }

    def reset(self) -> None:
        """Clear ALL state.  For use in tests only."""
        with self._lock:
            cleared_run_ids = list(self._waiting.keys())
            for q in self._queues.values():
                q.clear()
            self._waiting.clear()
            self._rr_cursor = {p: None for p in PRIORITY_ORDER}
            self._seq = 0
            self._total_enqueued = 0
            self._total_dispatched = 0
            self._total_dropped = 0
            self._last_stale_wait_check_monotonic = 0.0
            self._pre_rehydration_buffer.clear()
            self._rehydration_complete.clear()
        for run_id in cleared_run_ids:
            self._unregister_redis_wait(run_id)

    def _persist_wait_backup(self, run_id: str) -> None:
        try:
            SessionLocal = _get_session_factory()
            from AINDY.db.models.flow_run import FlowRun
            from AINDY.db.models.waiting_flow_run import WaitingFlowRun
        except Exception as exc:
            logger.warning(
                "[Scheduler] waiting backup init failed for run=%s (non-fatal): %s",
                run_id,
                exc,
            )
            return

        with self._lock:
            entry = dict(self._waiting.get(str(run_id)) or {})

        if not entry:
            return

        db = None
        try:
            db = SessionLocal()
            from AINDY.db.database import utcnow
            wait_condition = entry.get("wait_condition") or {}
            timeout_at = None
            waited_since = utcnow()
            max_wait_seconds = None
            raw_trigger = wait_condition.get("trigger_at")
            if raw_trigger is not None:
                try:
                    from datetime import datetime, timezone

                    if isinstance(raw_trigger, datetime):
                        timeout_at = raw_trigger
                    elif isinstance(raw_trigger, str):
                        timeout_at = datetime.fromisoformat(raw_trigger)
                    if timeout_at is not None and timeout_at.tzinfo is None:
                        timeout_at = timeout_at.replace(tzinfo=timezone.utc)
                except Exception:
                    timeout_at = None

            if timeout_at is None:
                flow_run = (
                    db.query(FlowRun)
                    .filter(FlowRun.id == str(run_id))
                    .first()
                )
                timeout_at = getattr(flow_run, "wait_deadline", None) if flow_run else None
            if timeout_at is not None:
                try:
                    max_wait_seconds = max(
                        0,
                        int((timeout_at - waited_since).total_seconds()),
                    )
                except Exception:
                    max_wait_seconds = None

            event_type = (
                wait_condition.get("event_name")
                or entry.get("wait_for")
                or "__time_wait__"
            )
            db.merge(
                WaitingFlowRun(
                    run_id=str(run_id),
                    event_type=str(event_type),
                    correlation_id=entry.get("correlation_id"),
                    waited_since=waited_since,
                    max_wait_seconds=max_wait_seconds,
                    timeout_at=timeout_at,
                    eu_id=entry.get("eu_id"),
                    priority=entry.get("priority") or PRIORITY_NORMAL,
                    instance_id=_get_instance_id(),
                )
            )
            db.commit()
        except Exception as exc:
            if db is not None:
                try:
                    db.rollback()
                except Exception:
                    pass
            logger.warning(
                "[Scheduler] waiting backup write failed for run=%s (non-fatal): %s",
                run_id,
                exc,
            )
        finally:
            if db is not None:
                db.close()

    def _delete_wait_backup(self, run_id: str) -> None:
        try:
            SessionLocal = _get_session_factory()
            from AINDY.db.models.waiting_flow_run import WaitingFlowRun
        except Exception as exc:
            logger.warning(
                "[Scheduler] waiting backup delete init failed for run=%s (non-fatal): %s",
                run_id,
                exc,
            )
            return

        db = None
        try:
            db = SessionLocal()
            (
                db.query(WaitingFlowRun)
                .filter(WaitingFlowRun.run_id == str(run_id))
                .delete(synchronize_session=False)
            )
            db.commit()
        except Exception as exc:
            if db is not None:
                try:
                    db.rollback()
                except Exception:
                    pass
            logger.warning(
                "[Scheduler] waiting backup delete failed for run=%s (non-fatal): %s",
                run_id,
                exc,
            )
        finally:
            if db is not None:
                db.close()


# ── Module-level singleton ────────────────────────────────────────────────────

_SCHEDULER: SchedulerEngine | None = None
_SCHED_LOCK = threading.Lock()


def get_scheduler_engine() -> SchedulerEngine:
    """Return the module-level SchedulerEngine singleton.

    Thread-safe double-checked locking.  Use this in all production code.
    Tests should instantiate ``SchedulerEngine()`` directly for isolation.
    """
    global _SCHEDULER
    if _SCHEDULER is None:
        with _SCHED_LOCK:
            if _SCHEDULER is None:
                _SCHEDULER = SchedulerEngine()
    return _SCHEDULER
