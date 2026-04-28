"""Periodic stuck-run watchdog job for APScheduler leader instances."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from threading import Lock

from AINDY.config import settings

logger = logging.getLogger(__name__)

_LAST_SCAN_RESULT_LOCK = Lock()
_LAST_SCAN_RESULT: dict[str, object | None] = {
    "last_run_at": None,
    "recovered": 0,
    "dead_lettered": 0,
    "had_error": False,
    "error_message": None,
}


def _update_last_scan_result(
    *,
    recovered: int,
    dead_lettered: int,
    had_error: bool,
    error_message: str | None = None,
) -> None:
    with _LAST_SCAN_RESULT_LOCK:
        _LAST_SCAN_RESULT.update(
            {
                "last_run_at": datetime.now(timezone.utc).isoformat(),
                "recovered": int(recovered),
                "dead_lettered": int(dead_lettered),
                "had_error": bool(had_error),
                "error_message": error_message,
            }
        )


def get_last_scan_result() -> dict:
    """Return a copy of the last watchdog scan result. Thread-safe read."""
    with _LAST_SCAN_RESULT_LOCK:
        return dict(_LAST_SCAN_RESULT)


def watchdog_scan() -> None:
    """
    Scan for stuck FlowRun and AgentRun rows and recover them.
    Designed to run as an APScheduler job on the leader instance.
    Safe to call concurrently: scan_and_recover_stuck_runs() opens its
    own DB session and is idempotent.
    """
    from AINDY.agents.stuck_run_service import scan_and_recover_stuck_runs
    from AINDY.core.observability_events import emit_recovery_failure
    from AINDY.core.system_event_service import emit_system_event
    from AINDY.db.database import SessionLocal

    db = SessionLocal()
    try:
        result = scan_and_recover_stuck_runs(
            db,
            staleness_minutes=settings.STUCK_RUN_THRESHOLD_MINUTES,
            include_wait_timeouts=True,
            return_stats=True,
        )
        recovered = int(result.get("recovered", 0))
        dead_lettered = int(result.get("dead_lettered", 0))
        if recovered or dead_lettered:
            logger.info(
                "[watchdog] Periodic scan recovered %d stuck run(s) and dead-lettered %d wait flow(s)",
                recovered,
                dead_lettered,
            )
        if recovered:
            try:
                from AINDY.platform_layer.metrics import (
                    startup_recovery_runs_recovered_total,
                )

                startup_recovery_runs_recovered_total.labels(
                    recovery_type="watchdog_periodic"
                ).inc(recovered)
            except Exception:
                pass
        _update_last_scan_result(
            recovered=recovered,
            dead_lettered=dead_lettered,
            had_error=False,
            error_message=None,
        )
        try:
            emit_system_event(
                db=db,
                event_type="watchdog.scan.completed",
                source="stuck_run_watchdog",
                payload={
                    "recovered": recovered,
                    "dead_lettered": dead_lettered,
                    "threshold_minutes": settings.STUCK_RUN_THRESHOLD_MINUTES,
                    "watchdog_interval_minutes": settings.AINDY_WATCHDOG_INTERVAL_MINUTES,
                    "had_work": recovered > 0 or dead_lettered > 0,
                },
            )
        except Exception as exc:
            logger.warning(
                "[watchdog] Failed to emit watchdog.scan.completed event: %s",
                exc,
            )
    except Exception as exc:
        _update_last_scan_result(
            recovered=0,
            dead_lettered=0,
            had_error=True,
            error_message=str(exc),
        )
        emit_recovery_failure("watchdog_periodic", exc, db, logger=logger)
    finally:
        db.close()
