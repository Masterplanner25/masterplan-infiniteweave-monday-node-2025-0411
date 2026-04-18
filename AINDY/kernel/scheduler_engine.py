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
import threading
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
            logger.info(
                "[Scheduler] event-resumed run=%s event=%s type=%s priority=%s",
                run_id, event_type, item.eu_type, entry["priority"],
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

        return len(to_resume)

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
