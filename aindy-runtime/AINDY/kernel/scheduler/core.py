from __future__ import annotations

import threading
from collections import deque
from typing import Callable

from AINDY.kernel.scheduler.common import (
    PRIORITY_NORMAL,
    PRIORITY_ORDER,
    ScheduledItem,
    logger,
)


class SchedulerCoreMixin:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._queues: dict[str, deque[ScheduledItem]] = {p: deque() for p in PRIORITY_ORDER}
        self._rr_cursor: dict[str, str | None] = {p: None for p in PRIORITY_ORDER}
        self._waiting: dict[str, dict] = {}
        self._seq = 0
        self._total_enqueued = 0
        self._total_dispatched = 0
        self._total_dropped = 0
        self._last_stale_wait_check_monotonic = 0.0
        self._rehydration_complete = threading.Event()
        self._pre_rehydration_buffer: list[tuple[str, str | None]] = []

    def get_metrics_snapshot(self) -> dict:
        with self._lock:
            return {
                "queue_depth": {p: len(self._queues[p]) for p in PRIORITY_ORDER},
                "waiting_count": len(self._waiting),
            }

    def mark_rehydration_complete(self) -> None:
        self._rehydration_complete.set()
        with self._lock:
            buffered = list(self._pre_rehydration_buffer)
            self._pre_rehydration_buffer.clear()

        for event_type, correlation_id in buffered:
            logger.info("[Scheduler] replaying buffered event post-rehydration: %s", event_type)
            try:
                self.notify_event(event_type, correlation_id=correlation_id, broadcast=False)
            except Exception:
                logger.warning(
                    "[Scheduler] buffered event replay failed event=%s corr=%s",
                    event_type,
                    correlation_id,
                    exc_info=True,
                )

    def is_rehydrated(self) -> bool:
        return self._rehydration_complete.is_set()

    def _enqueue_resume(
        self,
        run_id: str,
        callback: Callable[[], None],
        entry: dict,
    ) -> None:
        self.enqueue(
            ScheduledItem(
                execution_unit_id=str(entry.get("eu_id") or ""),
                tenant_id=str(entry.get("tenant_id") or "system"),
                priority=entry.get("priority") or PRIORITY_NORMAL,
                run_callback=callback,
                run_id=run_id,
                eu_type=entry.get("eu_type", "flow"),
            )
        )

    def _unregister_redis_wait(self, run_id: str) -> None:
        try:
            from AINDY.kernel.redis_wait_registry import RedisWaitRegistry
            from AINDY.kernel.event_bus import get_redis_client

            RedisWaitRegistry(get_redis_client()).unregister(str(run_id))
        except Exception:
            logger.debug("[Scheduler] Redis wait unregister skipped for run=%s", run_id, exc_info=True)

    def enqueue(self, item: ScheduledItem) -> None:
        with self._lock:
            self._seq += 1
            item.enqueued_at_seq = self._seq
            self._queues[item.priority].append(item)
            self._total_enqueued += 1
            logger.debug(
                "[Scheduler] enqueued eu=%s tenant=%s priority=%s seq=%d",
                item.execution_unit_id,
                item.tenant_id,
                item.priority,
                self._seq,
            )

    def dequeue_next(self) -> ScheduledItem | None:
        with self._lock:
            for priority in PRIORITY_ORDER:
                q = self._queues[priority]
                if not q:
                    continue
                last_tenant = self._rr_cursor[priority]
                if last_tenant is not None and len(q) > 1 and q[0].tenant_id == last_tenant:
                    q.rotate(-1)
                item = q.popleft()
                self._rr_cursor[priority] = item.tenant_id
                self._total_dispatched += 1
                return item
        return None

    def queue_depth(self) -> dict[str, int]:
        with self._lock:
            return {p: len(q) for p, q in self._queues.items()}

    def stats(self) -> dict:
        with self._lock:
            return {
                "queues": {p: len(q) for p, q in self._queues.items()},
                "waiting": len(self._waiting),
                "total_enqueued": self._total_enqueued,
                "total_dispatched": self._total_dispatched,
                "total_dropped": self._total_dropped,
            }

    def reset(self) -> None:
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
