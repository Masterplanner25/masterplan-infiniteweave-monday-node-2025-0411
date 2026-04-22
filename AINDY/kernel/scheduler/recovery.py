from __future__ import annotations

import time

from AINDY.kernel.scheduler.common import PRIORITY_NORMAL, _get_instance_id, _get_session_factory, logger


class SchedulerRecoveryMixin:
    def _check_stale_waits(self) -> int:
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
            db = _get_session_factory()()
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

        orphan_run_ids = {str(row.run_id) for row in orphan_rows if getattr(row, "run_id", None)}
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

        logger.info("[Scheduler] orphaned-wait recovery registered %d wait(s)", recovered)
        return recovered

    def cleanup_stale_waits(self) -> int:
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
                        db.query(FlowRun.id).filter(FlowRun.id.in_(run_ids), FlowRun.status == "waiting").all()
                    )
                }
                waiting_eu_ids = set()
                if eu_query_ids:
                    waiting_eu_ids = {
                        str(eu_id)
                        for (eu_id,) in (
                            db.query(ExecutionUnit.id)
                            .filter(ExecutionUnit.id.in_(eu_query_ids), ExecutionUnit.status == "waiting")
                            .all()
                        )
                    }
        except Exception:
            logger.warning("[Scheduler] cleanup_stale_waits DB query failed", exc_info=True)
            return 0

        stale = [run_id for run_id in run_ids if run_id not in (waiting_flow_ids | waiting_eu_ids)]
        for run_id in stale:
            with self._lock:
                self._waiting.pop(run_id, None)
            self._delete_wait_backup(run_id)
            logger.info("[Scheduler] evicted stale wait run_id=%s", run_id)
        return len(stale)
