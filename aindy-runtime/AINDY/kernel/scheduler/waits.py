from __future__ import annotations

from AINDY.kernel.scheduler.common import PRIORITY_NORMAL, _MAX_PRE_REHYDRATION_BUFFER, logger
from AINDY.kernel.scheduler.cross_instance import _cross_instance_resume, _cross_instance_tick


class SchedulerWaitMixin:
    def register_wait(
        self,
        run_id: str,
        wait_for_event: str,
        tenant_id: str,
        eu_id: str,
        resume_callback,
        priority: str = PRIORITY_NORMAL,
        correlation_id: str | None = None,
        trace_id: str | None = None,
        eu_type: str = "flow",
        wait_condition=None,
    ) -> None:
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

            RedisWaitRegistry(get_redis_client()).register(
                str(run_id),
                ResumeSpec(
                    handler=RESUME_HANDLER_EU,
                    eu_id=str(eu_id),
                    tenant_id=str(tenant_id),
                    run_id=str(run_id),
                    eu_type=eu_type,
                ),
            )
        except Exception:
            logger.debug("[Scheduler] Redis wait registration skipped", exc_info=True)
        self._persist_wait_backup(str(run_id))
        logger.debug(
            "[Scheduler] registered wait run=%s event=%s eu=%s type=%s trace=%s cond_type=%s",
            run_id,
            wait_for_event,
            eu_id,
            eu_type,
            trace_id,
            (wc_dict or {}).get("type"),
        )

    def notify_event(
        self,
        event_type: str,
        *,
        correlation_id: str | None = None,
        broadcast: bool = True,
    ) -> int:
        import AINDY.kernel.scheduler_engine as compat

        if not self._rehydration_complete.is_set():
            with self._lock:
                if len(self._pre_rehydration_buffer) >= compat._MAX_PRE_REHYDRATION_BUFFER:
                    logger.error(
                        "[Scheduler] pre-rehydration buffer full (%d); event %r dropped",
                        compat._MAX_PRE_REHYDRATION_BUFFER,
                        event_type,
                    )
                    return 0
                self._pre_rehydration_buffer.append((event_type, correlation_id))
            logger.debug("[Scheduler] buffered event pre-rehydration: %s corr=%s", event_type, correlation_id)
            return 0

        to_resume: list[tuple[str, dict]] = []
        with self._lock:
            for run_id, entry in list(self._waiting.items()):
                wc = entry.get("wait_condition") or {}
                wc_type = wc.get("type")
                wc_event = wc.get("event_name")
                if wc_type == "time":
                    continue
                if wc_event:
                    if wc_type not in ("event", "external") or wc_event != event_type:
                        continue
                elif entry.get("wait_for") != event_type:
                    continue
                entry_corr = entry.get("correlation_id") or None
                emit_corr = correlation_id or None
                if entry_corr and emit_corr and entry_corr != emit_corr:
                    continue
                to_resume.append((run_id, entry))

            for run_id, _ in to_resume:
                del self._waiting[run_id]
                self._unregister_redis_wait(run_id)

        for run_id, entry in to_resume:
            self._enqueue_resume(run_id, entry["callback"], entry)
            logger.info(
                "[Scheduler] event-resumed run=%s event=%s type=%s priority=%s",
                run_id,
                event_type,
                entry.get("eu_type", "flow"),
                entry["priority"],
            )
            self._delete_wait_backup(run_id)

        cross_resumed = compat._cross_instance_resume(
            self,
            event_type,
            correlation_id,
            {run_id for run_id, _ in to_resume},
        )
        if broadcast:
            try:
                from AINDY.kernel.event_bus import get_event_bus

                get_event_bus().publish(event_type, correlation_id=correlation_id)
            except Exception as exc:
                logger.debug("[Scheduler] event bus publish failed (non-fatal): %s", exc)
        return len(to_resume) + cross_resumed

    def tick_time_waits(self) -> int:
        from datetime import datetime, timezone
        import AINDY.kernel.scheduler_engine as compat

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
                if isinstance(raw_trigger, str):
                    try:
                        trigger_dt = datetime.fromisoformat(raw_trigger)
                        if trigger_dt.tzinfo is None:
                            trigger_dt = trigger_dt.replace(tzinfo=timezone.utc)
                    except ValueError:
                        continue
                elif isinstance(raw_trigger, datetime):
                    trigger_dt = raw_trigger if raw_trigger.tzinfo else raw_trigger.replace(tzinfo=timezone.utc)
                else:
                    continue
                if trigger_dt <= now:
                    to_fire.append((run_id, entry))

            for run_id, _ in to_fire:
                del self._waiting[run_id]
                self._unregister_redis_wait(run_id)

        for run_id, entry in to_fire:
            self._enqueue_resume(run_id, entry["callback"], entry)
            logger.info("[Scheduler] time-wait fired run=%s eu=%s priority=%s", run_id, entry["eu_id"], entry["priority"])
            self._delete_wait_backup(run_id)

        return len(to_fire) + compat._cross_instance_tick(self)

    def scan_expired_waits(self) -> int:
        return self.tick_time_waits()

    def peek_matching_run_ids(self, event_type: str, *, correlation_id: str | None = None) -> list[str]:
        matched: list[str] = []
        with self._lock:
            for run_id, entry in self._waiting.items():
                wc = entry.get("wait_condition") or {}
                wc_type = wc.get("type")
                wc_event = wc.get("event_name")
                if wc_type == "time":
                    continue
                if wc_event:
                    if wc_type not in ("event", "external") or wc_event != event_type:
                        continue
                elif entry.get("wait_for") != event_type:
                    continue
                entry_corr = entry.get("correlation_id") or None
                emit_corr = correlation_id or None
                if entry_corr and emit_corr and entry_corr != emit_corr:
                    continue
                matched.append(run_id)
        return matched

    def waiting_for(self, run_id: str) -> str | None:
        with self._lock:
            entry = self._waiting.get(str(run_id))
            return entry["wait_for"] if entry else None
