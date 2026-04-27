"""Periodic stuck-run watchdog job for APScheduler leader instances."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def watchdog_scan() -> None:
    """
    Scan for stuck FlowRun and AgentRun rows and recover them.
    Designed to run as an APScheduler job on the leader instance.
    Safe to call concurrently: scan_and_recover_stuck_runs() opens its
    own DB session and is idempotent.
    """
    from AINDY.agents.stuck_run_service import scan_and_recover_stuck_runs
    from AINDY.config import settings
    from AINDY.core.observability_events import emit_recovery_failure
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
    except Exception as exc:
        emit_recovery_failure("watchdog_periodic", exc, db, logger=logger)
    finally:
        db.close()
