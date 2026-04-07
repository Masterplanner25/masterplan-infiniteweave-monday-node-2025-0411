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
``resume_waiting(event_type)`` creates a new ScheduledItem and enqueues it
at normal priority so the resumed run can be picked up on the next
``schedule()`` cycle.

Usage
-----
    from kernel.scheduler_engine import get_scheduler_engine, ScheduledItem

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
import threading
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Optional

from kernel.resource_manager import get_resource_manager

logger = logging.getLogger(__name__)

# ── Priority levels ───────────────────────────────────────────────────────────

PRIORITY_HIGH = "high"
PRIORITY_NORMAL = "normal"
PRIORITY_LOW = "low"

PRIORITY_ORDER = (PRIORITY_HIGH, PRIORITY_NORMAL, PRIORITY_LOW)

# How many items to drain per schedule() call (prevents starvation of caller)
MAX_PER_SCHEDULE_CYCLE = 10


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
        eu_type:           ExecutionUnit type string (flow/agent/job/task/nodus).
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

    def __post_init__(self) -> None:
        if self.priority not in PRIORITY_ORDER:
            raise ValueError(
                f"Invalid priority {self.priority!r}; must be one of {PRIORITY_ORDER}"
            )


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
    ``resume_waiting(event_type)`` re-enqueues all runs waiting for that event.
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
        is enabled; lightweight types (task, job) run INLINE on this thread.

        Checks ResourceManager before each execution:
        - If ``can_execute`` returns False, the item is re-enqueued at its
          original priority (it will be tried again next cycle).

        Returns:
            Number of items actually dispatched (not re-enqueued) this cycle.
        """
        # Lazy import — avoids circular dependency (kernel → core) at module load.
        from core.execution_dispatcher import dispatch as _dispatch

        # Fire any time-based waits whose trigger_at has passed before
        # draining the queues, so they are available in this same cycle.
        self.tick_time_waits()

        rm = get_resource_manager()
        dispatched = 0

        for _ in range(MAX_PER_SCHEDULE_CYCLE):
            item = self.dequeue_next()
            if item is None:
                break

            ok, reason = rm.can_execute(item.tenant_id, item.execution_unit_id)
            if not ok:
                # Re-enqueue — resource unavailable; try next cycle
                with self._lock:
                    self._queues[item.priority].appendleft(item)
                    self._total_dispatched -= 1  # undo dequeue count
                logger.debug(
                    "[Scheduler] deferred eu=%s reason=%s", item.execution_unit_id, reason
                )
                break  # stop trying; resource constrained

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
                logger.error(
                    "[Scheduler] dispatch failed eu=%s: %s", item.execution_unit_id, exc
                )
                with self._lock:
                    self._total_dropped += 1

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

        When the condition is satisfied — by ``resume_waiting(event_type)`` for
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
        logger.debug(
            "[Scheduler] registered wait run=%s event=%s eu=%s type=%s trace=%s cond_type=%s",
            run_id, wait_for_event, eu_id, eu_type, trace_id,
            (wc_dict or {}).get("type"),
        )

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

        for run_id, entry in to_fire:
            item = ScheduledItem(
                execution_unit_id=entry["eu_id"],
                tenant_id=entry["tenant_id"],
                priority=entry["priority"],
                run_callback=entry["callback"],
                run_id=run_id,
                eu_type=entry.get("eu_type", "flow"),
            )
            self.enqueue(item)
            logger.info(
                "[Scheduler] time-wait fired run=%s eu=%s priority=%s",
                run_id, entry["eu_id"], entry["priority"],
            )

        return len(to_fire)

    def resume_waiting(self, event_type: str) -> int:
        """Re-enqueue all runs waiting for *event_type*.

        Called when an event fires (e.g. from event_service.emit_system_event).

        Args:
            event_type: The event type that just fired.

        Returns:
            Number of runs re-enqueued.
        """
        resumed = 0
        with self._lock:
            to_resume = [
                (run_id, entry)
                for run_id, entry in self._waiting.items()
                if entry["wait_for"] == event_type
            ]
            for run_id, entry in to_resume:
                del self._waiting[run_id]

        for run_id, entry in to_resume:
            item = ScheduledItem(
                execution_unit_id=entry["eu_id"],
                tenant_id=entry["tenant_id"],
                priority=entry["priority"],
                run_callback=entry["callback"],
                run_id=run_id,
                eu_type=entry.get("eu_type", "flow"),
            )
            self.enqueue(item)
            resumed += 1
            logger.info(
                "[Scheduler] resumed run=%s event=%s type=%s priority=%s",
                run_id, event_type, item.eu_type, entry["priority"],
            )

        return resumed

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
            for q in self._queues.values():
                q.clear()
            self._waiting.clear()
            self._rr_cursor = {p: None for p in PRIORITY_ORDER}
            self._seq = 0
            self._total_enqueued = 0
            self._total_dispatched = 0
            self._total_dropped = 0


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
