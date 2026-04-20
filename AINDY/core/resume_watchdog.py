from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

_WATCHDOG_MIN_WAIT_MINUTES = 2
_EVENT_LOOKBACK_MINUTES = 60


def _normalize_utc(dt):
    if dt is None:
        return None
    if getattr(dt, "tzinfo", None) is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _try_reregister_callback(run_id: str, db) -> None:
    try:
        from AINDY.core.flow_run_rehydration import rehydrate_waiting_flow_runs

        rehydrate_waiting_flow_runs(db)
    except Exception as exc:
        logger.warning(
            "[resume_watchdog] Re-register callback failed for %s: %s",
            run_id,
            exc,
        )


def scan_and_resume_stranded_flows(db) -> int:
    """
    Scan WaitingFlowRun rows for stale waiting flows whose matching SystemEvent
    has already fired, then trigger a local-only notify_event() resume attempt.
    """
    from AINDY.db.models.flow_run import FlowRun
    from AINDY.db.models.system_event import SystemEvent
    from AINDY.db.models.waiting_flow_run import WaitingFlowRun
    from AINDY.kernel.scheduler_engine import get_scheduler_engine

    now = datetime.now(timezone.utc)
    stale_cutoff = now - timedelta(minutes=_WATCHDOG_MIN_WAIT_MINUTES)
    event_lookback = now - timedelta(minutes=_EVENT_LOOKBACK_MINUTES)
    resumed_count = 0

    try:
        waiting_rows = (
            db.query(WaitingFlowRun)
            .filter(WaitingFlowRun.waited_since <= stale_cutoff)
            .all()
        )
    except Exception as exc:
        logger.warning("[resume_watchdog] Could not query WaitingFlowRun: %s", exc)
        return 0

    scheduler = get_scheduler_engine()

    for row in waiting_rows:
        run_id = str(row.run_id)

        try:
            flow_run = db.query(FlowRun).filter(FlowRun.id == run_id).first()
        except Exception as exc:
            logger.warning("[resume_watchdog] FlowRun query failed for %s: %s", run_id, exc)
            continue

        if flow_run is None or flow_run.status != "waiting":
            continue

        wait_for_event = getattr(row, "event_type", None) or getattr(flow_run, "waiting_for", None)
        if not wait_for_event or wait_for_event == "__time_wait__":
            continue

        correlation_id = getattr(row, "correlation_id", None)
        wait_started = _normalize_utc(getattr(row, "waited_since", None)) or event_lookback

        try:
            event_query = (
                db.query(SystemEvent)
                .filter(
                    SystemEvent.type == wait_for_event,
                    SystemEvent.timestamp >= wait_started,
                    SystemEvent.timestamp >= event_lookback,
                )
            )
            if correlation_id:
                event_query = event_query.filter(SystemEvent.trace_id == correlation_id)
            matching_event = event_query.order_by(SystemEvent.timestamp.asc()).first()
        except Exception as exc:
            logger.warning("[resume_watchdog] SystemEvent query failed for %s: %s", run_id, exc)
            continue

        if matching_event is None:
            continue

        logger.warning(
            "[resume_watchdog] Flow %s has been waiting for %r since %s but event was emitted at %s - attempting resume.",
            run_id,
            wait_for_event,
            wait_started.isoformat(),
            _normalize_utc(getattr(matching_event, "timestamp", None)).isoformat()
            if getattr(matching_event, "timestamp", None) is not None
            else "unknown",
        )

        if scheduler.waiting_for(run_id) is None:
            _try_reregister_callback(run_id, db)

        try:
            resumed = scheduler.notify_event(
                wait_for_event,
                correlation_id=correlation_id,
                broadcast=False,
            )
            if resumed > 0:
                resumed_count += resumed
                try:
                    from AINDY.platform_layer.metrics import resume_watchdog_resumes_total

                    resume_watchdog_resumes_total.inc(resumed)
                except Exception:
                    pass
                logger.info(
                    "[resume_watchdog] notify_event resumed %d flow(s) for event %r (run_id=%s)",
                    resumed,
                    wait_for_event,
                    run_id,
                )
        except Exception as exc:
            logger.warning("[resume_watchdog] notify_event failed for %s: %s", run_id, exc)

    return resumed_count
