from __future__ import annotations

from AINDY.kernel.scheduler.common import (
    MAX_PER_SCHEDULE_CYCLE,
    PRIORITY_LOW,
    ScheduledItem,
    _ResumedEUStub,
    _emit_dispatch_failure,
    logger,
)


class SchedulerDispatchMixin:
    def schedule(self) -> int:
        import AINDY.kernel.scheduler_engine as compat
        from AINDY.core.execution_dispatcher import dispatch as _dispatch

        self._check_stale_waits()
        self.tick_time_waits()

        rm = compat.get_resource_manager()
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
                with self._lock:
                    self._queues[item.priority].appendleft(item)
                    self._total_dispatched -= 1
                saturated_tenants.add(item.tenant_id)
                logger.debug("[Scheduler] deferred eu=%s tenant=%s reason=%s", item.execution_unit_id, item.tenant_id, reason)
                continue

            stub = _ResumedEUStub(id=item.execution_unit_id, type=item.eu_type, priority=item.priority)
            context = {"eu_id": item.execution_unit_id, "run_id": item.run_id, "source": "scheduler.resume"}
            try:
                _dispatch(stub, item.run_callback, context)
                dispatched += 1
                logger.debug("[Scheduler] dispatched eu=%s type=%s priority=%s", item.execution_unit_id, item.eu_type, item.priority)
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
