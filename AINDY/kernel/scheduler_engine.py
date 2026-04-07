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
        enqueued_at_seq:   Monotone sequence number assigned on enqueue (for FIFO
                           within same tenant+priority).
    """

    execution_unit_id: str
    tenant_id: str
    priority: str
    run_callback: Callable[[], None]
    run_id: Optional[str] = None
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

        Checks ResourceManager before each execution:
        - If ``can_execute`` returns False, the item is re-enqueued at its
          original priority (it will be tried again next cycle).

        Returns:
            Number of items actually dispatched (not re-enqueued) this cycle.
        """
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

            try:
                item.run_callback()
                dispatched += 1
            except Exception as exc:
                logger.error(
                    "[Scheduler] callback failed eu=%s: %s", item.execution_unit_id, exc
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
    ) -> None:
        """Register a run that is waiting for an event.

        When ``resume_waiting(wait_for_event)`` is called, this run will be
        re-enqueued with *priority*.

        This is the single authority for all WAIT registrations — flow nodes,
        resource-quota pauses, and generic ExecutionUnit WAITs (via pipeline)
        all go through this method.

        Args:
            run_id:           Unique key for this wait (FlowRun ID for flows,
                              eu_id for generic EU waits).
            wait_for_event:   Event type the run is waiting for.
            tenant_id:        Owning tenant.
            eu_id:            ExecutionUnit ID.
            resume_callback:  Zero-arg callable to execute when resumed.
            priority:         Queue priority on resume (default NORMAL).
            correlation_id:   Propagated correlation chain ID (optional).
            trace_id:         Request trace ID for observability (optional).
        """
        with self._lock:
            self._waiting[str(run_id)] = {
                "wait_for": wait_for_event,
                "tenant_id": tenant_id,
                "eu_id": eu_id,
                "callback": resume_callback,
                "priority": priority,
                "correlation_id": correlation_id,
                "trace_id": trace_id,
            }
        logger.debug(
            "[Scheduler] registered wait run=%s event=%s eu=%s trace=%s",
            run_id, wait_for_event, eu_id, trace_id,
        )

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
            )
            self.enqueue(item)
            resumed += 1
            logger.info(
                "[Scheduler] resumed run=%s event=%s priority=%s",
                run_id, event_type, entry["priority"],
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
