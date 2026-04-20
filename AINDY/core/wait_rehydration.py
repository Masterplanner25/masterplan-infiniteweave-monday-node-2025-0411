"""
WAIT State Rehydration — startup recovery for the SchedulerEngine registry.

The SchedulerEngine._waiting dict is in-memory only.  A server restart
drops all registered WAIT entries, so pending ExecutionUnits would remain
in ``status="waiting"`` forever — their resume events would arrive and
``notify_event()`` would find nothing to wake.

This module re-registers those EUs on startup by:

1. Querying ``execution_units WHERE status = 'waiting'``.
2. Reconstructing each EU's ``WaitCondition`` from the persisted JSONB column.
3. Calling ``SchedulerEngine.register_wait()`` with a callback that updates
   the EU status (``waiting → resumed → executing``) when the condition fires.

Idempotency
-----------
``register_wait()`` stores entries as ``_waiting[run_id] = {...}`` — dict
assignment under lock.  Calling this function more than once is safe: each
run produces identical entries, overwriting the previous ones cleanly.

Duplicate guard
---------------
Before registering, we check ``scheduler.waiting_for(eu_id)`` and skip EUs
already in the registry.  This prevents spurious log noise when the function
is called multiple times during startup.

Scope
-----
This rehydrates the EU-level callback only (status transitions).
Flow-level resume callbacks (``PersistentFlowRunner.resume()``) are
registered separately when the flow runner is re-entered.  The EU callback
is the minimum needed to prevent permanently lost WAIT state.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

# Module-level imports that are safe to resolve immediately (no circular deps).
# Keeping them here makes them patchable in tests via
# "core.wait_rehydration.<name>".
from AINDY.core.wait_condition import WaitCondition, WAIT_TYPE_TIME
from AINDY.kernel.scheduler_engine import get_scheduler_engine
from AINDY.db.database import utcnow

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Sentinel used as wait_for_event for time-based waits (no event name).
_TIME_SENTINEL = "__time_wait__"


def ensure_waiting_flow_run_row(
    db: "Session",
    *,
    run_id: str,
    event_type: str,
    correlation_id: str | None,
    timeout_at,
    eu_id: str | None,
    priority: str,
) -> None:
    """Best-effort seed of waiting_flow_runs for startup durability."""
    waited_since = utcnow()
    max_wait_seconds = None
    if timeout_at is not None:
        try:
            max_wait_seconds = max(
                0,
                int((timeout_at - waited_since).total_seconds()),
            )
        except Exception:
            max_wait_seconds = None
    try:
        import os

        from AINDY.db.models.waiting_flow_run import WaitingFlowRun

        existing = (
            db.query(WaitingFlowRun)
            .filter(WaitingFlowRun.run_id == str(run_id))
            .first()
        )
        if existing is None:
            db.add(
                WaitingFlowRun(
                    run_id=str(run_id),
                    event_type=event_type,
                    correlation_id=correlation_id,
                    waited_since=waited_since,
                    max_wait_seconds=max_wait_seconds,
                    timeout_at=timeout_at,
                    eu_id=eu_id,
                    priority=priority or "normal",
                    instance_id=os.getenv("HOSTNAME", "local"),
                )
            )
        else:
            existing.event_type = event_type
            existing.correlation_id = correlation_id
            existing.timeout_at = timeout_at
            existing.eu_id = eu_id
            existing.priority = priority or "normal"
            if existing.waited_since is None:
                existing.waited_since = waited_since
            existing.max_wait_seconds = max_wait_seconds
        db.flush()
    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass
        logger.warning(
            "[rehydrate] waiting_flow_runs seed failed for run=%s (non-fatal): %s",
            run_id,
            exc,
        )


def rehydrate_waiting_eus(db: "Session") -> int:
    """Re-register all waiting EUs with the SchedulerEngine.

    Args:
        db: An active SQLAlchemy session.  Closed by the caller — do NOT
            close it inside this function.

    Returns:
        Number of EUs successfully re-registered.
    """
    from AINDY.db.models.execution_unit import ExecutionUnit

    scheduler = get_scheduler_engine()

    # ── 1. Query all waiting EUs ──────────────────────────────────────────────
    try:
        waiting_eus = (
            db.query(ExecutionUnit)
            .filter(ExecutionUnit.status == "waiting")
            .all()
        )
    except Exception as exc:
        logger.warning("[rehydrate] Could not query waiting EUs (non-fatal): %s", exc)
        return 0

    if not waiting_eus:
        logger.info("[rehydrate] No waiting EUs found — nothing to rehydrate.")
        return 0

    logger.info("[rehydrate] Found %d waiting EU(s) — rehydrating...", len(waiting_eus))

    rehydrated = 0
    skipped = 0

    for eu in waiting_eus:
        eu_id = str(eu.id)

        # ── Duplicate guard: already in registry from this or a prior call ──
        if scheduler.waiting_for(eu_id) is not None:
            logger.debug(
                "[rehydrate] eu=%s already in scheduler registry — skipped", eu_id
            )
            skipped += 1
            continue

        # ── 2. Reconstruct WaitCondition from persisted JSONB ────────────────
        wc: WaitCondition | None = None
        if eu.wait_condition:
            try:
                wc = WaitCondition.from_dict(eu.wait_condition)
            except Exception as exc:
                logger.debug(
                    "[rehydrate] Cannot parse wait_condition for eu=%s: %s", eu_id, exc
                )

        if wc is None:
            # No persisted condition — cannot determine what to wait for.
            # The EU remains in DB status=waiting; a manual intervention or
            # admin endpoint will need to resolve it.
            logger.warning(
                "[rehydrate] eu=%s has status=waiting but no wait_condition — "
                "cannot rehydrate (manual intervention required)",
                eu_id,
            )
            skipped += 1
            continue

        # For event/external waits, event_name is required.
        wait_for_event = wc.event_name or ""
        if not wait_for_event and wc.type != WAIT_TYPE_TIME:
            logger.warning(
                "[rehydrate] eu=%s has wait_condition type=%s but no event_name — "
                "cannot rehydrate",
                eu_id, wc.type,
            )
            skipped += 1
            continue

        # Time-based waits have no event name; use sentinel so register_wait()
        # stores the entry and tick_time_waits() can find it by condition type.
        if wc.type == WAIT_TYPE_TIME and not wait_for_event:
            wait_for_event = _TIME_SENTINEL

        # ── 3. Build resume callback ─────────────────────────────────────────
        # Callback creates its own DB session — the startup `db` will be closed
        # by the caller long before any resume event fires.
        #
        # FlowRun ownership guard
        # -----------------------
        # When the EU belongs to a FlowRun (flow_run_id is set), the FlowRun
        # callback registered by rehydrate_waiting_flow_runs() is the
        # authoritative gatekeeper: it claims the FlowRun atomically, then
        # drives EU resume and flow execution in the correct order.
        #
        # This EU callback checks FlowRun status before transitioning the EU:
        # - FlowRun still "waiting"   → both callbacks may race; EU idempotency
        #                               guard in ExecutionUnitService prevents
        #                               double-transition.
        # - FlowRun already claimed   → another instance won; skip EU transition
        #                               to avoid bookkeeping on losing instance.
        # - No flow_run_id (standalone EU) → no check needed; proceed directly.
        def _make_resume_callback(eid: str, flow_run_id: str | None):
            def _callback():
                from AINDY.db.database import SessionLocal
                from AINDY.core.execution_unit_service import ExecutionUnitService

                _db = SessionLocal()
                try:
                    # ── FlowRun ownership guard ───────────────────────────────
                    if flow_run_id:
                        from AINDY.db.models.flow_run import FlowRun as _FlowRun

                        fr = (
                            _db.query(_FlowRun)
                            .filter(_FlowRun.id == flow_run_id)
                            .first()
                        )
                        if fr is not None and fr.status != "waiting":
                            logger.debug(
                                "[rehydrate] eu=%s flow_run=%s status=%r — "
                                "EU callback skipped (FlowRun callback is "
                                "authoritative gatekeeper for this instance)",
                                eid, flow_run_id, fr.status,
                            )
                            return

                    ExecutionUnitService(_db).resume_execution_unit(eid)
                except Exception as _exc:
                    logger.warning(
                        "[rehydrate] resume callback failed for eu=%s: %s", eid, _exc
                    )
                finally:
                    _db.close()

            return _callback

        # ── 4. Re-register with SchedulerEngine ──────────────────────────────
        tenant_id = (
            str(eu.tenant_id)
            if eu.tenant_id
            else (str(eu.user_id) if eu.user_id else "system")
        )
        priority = eu.priority or "normal"
        correlation_id = str(eu.correlation_id) if eu.correlation_id else None
        eu_type = eu.type or "flow"
        eu_flow_run_id: str | None = (
            str(eu.flow_run_id) if getattr(eu, "flow_run_id", None) else None
        )

        try:
            scheduler.register_wait(
                run_id=eu_id,
                wait_for_event=wait_for_event,
                tenant_id=tenant_id,
                eu_id=eu_id,
                resume_callback=_make_resume_callback(eu_id, eu_flow_run_id),
                priority=priority,
                correlation_id=correlation_id,
                trace_id=None,          # trace_id not persisted on EU; omit
                eu_type=eu_type,
                wait_condition=wc,
            )
            ensure_waiting_flow_run_row(
                db,
                run_id=eu_id,
                event_type=wait_for_event,
                correlation_id=correlation_id,
                timeout_at=None,
                eu_id=eu_id,
                priority=priority,
            )
            rehydrated += 1
            logger.info(
                "[rehydrate] registered eu=%s type=%s cond_type=%s wait_for=%s",
                eu_id, eu_type, wc.type, wc.event_name,
            )
        except Exception as exc:
            logger.warning(
                "[rehydrate] Failed to register eu=%s: %s", eu_id, exc
            )
            skipped += 1

    logger.info(
        "[rehydrate] WAIT rehydration complete — registered=%d skipped=%d total=%d",
        rehydrated, skipped, len(waiting_eus),
    )
    return rehydrated
