from __future__ import annotations

from AINDY.kernel.scheduler.common import PRIORITY_NORMAL, _get_instance_id, _get_session_factory, logger


class SchedulerPersistenceMixin:
    def _persist_wait_backup(self, run_id: str) -> None:
        try:
            from AINDY.db.models.flow_run import FlowRun
            from AINDY.db.models.waiting_flow_run import WaitingFlowRun
        except Exception as exc:
            logger.warning("[Scheduler] waiting backup init failed for run=%s (non-fatal): %s", run_id, exc)
            return

        with self._lock:
            entry = dict(self._waiting.get(str(run_id)) or {})
        if not entry:
            return

        db = None
        try:
            db = _get_session_factory()()
            from AINDY.db.database import utcnow

            wait_condition = entry.get("wait_condition") or {}
            timeout_at = None
            waited_since = utcnow()
            max_wait_seconds = None
            raw_trigger = wait_condition.get("trigger_at")
            if raw_trigger is not None:
                try:
                    from datetime import datetime, timezone

                    timeout_at = raw_trigger if isinstance(raw_trigger, datetime) else datetime.fromisoformat(raw_trigger)
                    if timeout_at is not None and timeout_at.tzinfo is None:
                        timeout_at = timeout_at.replace(tzinfo=timezone.utc)
                except Exception:
                    timeout_at = None

            if timeout_at is None:
                flow_run = db.query(FlowRun).filter(FlowRun.id == str(run_id)).first()
                timeout_at = getattr(flow_run, "wait_deadline", None) if flow_run else None
            if timeout_at is not None:
                try:
                    max_wait_seconds = max(0, int((timeout_at - waited_since).total_seconds()))
                except Exception:
                    max_wait_seconds = None

            event_type = wait_condition.get("event_name") or entry.get("wait_for") or "__time_wait__"
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
            logger.warning("[Scheduler] waiting backup write failed for run=%s (non-fatal): %s", run_id, exc)
        finally:
            if db is not None:
                db.close()

    def _delete_wait_backup(self, run_id: str) -> None:
        try:
            from AINDY.db.models.waiting_flow_run import WaitingFlowRun
        except Exception as exc:
            logger.warning("[Scheduler] waiting backup delete init failed for run=%s (non-fatal): %s", run_id, exc)
            return

        db = None
        try:
            db = _get_session_factory()()
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
            logger.warning("[Scheduler] waiting backup delete failed for run=%s (non-fatal): %s", run_id, exc)
        finally:
            if db is not None:
                db.close()
