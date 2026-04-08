"""
FlowRun WAIT-state rehydration — startup recovery for the SchedulerEngine.

PersistentFlowRunner instances are ephemeral: a server restart destroys
every in-memory runner.  Any FlowRun with status="waiting" becomes
permanently stuck — the resume event fires, SchedulerEngine finds no
callback registered for that run_id, and the run stays in WAIT forever.

This module reconstructs PersistentFlowRunner callbacks for every waiting
FlowRun and re-registers them with SchedulerEngine on startup, so the
resume path is intact when the event arrives.

Relationship to EU rehydration
-------------------------------
``core.wait_rehydration.rehydrate_waiting_eus`` handles ExecutionUnit-level
callbacks (EU status transitions: waiting → resumed → executing).  This
module handles FlowRun-level callbacks (flow runner resume: call
``PersistentFlowRunner.resume(run_id)``).  The two work in parallel: both
are called during the same startup phase, and each registers a distinct
callback type in the SchedulerEngine entry for the same run_id.

Idempotency
-----------
``scheduler.waiting_for(run_id)`` is checked before each registration.
Runs already in the registry (e.g. from EU rehydration, or from a second
call to this function) are skipped.  Safe to call multiple times.

Dual-callback coexistence
-------------------------
Each waiting flow run may have TWO scheduler entries after rehydration:

``_waiting[eu.id]``        — registered by ``rehydrate_waiting_eus`` with a
                             callback that transitions the EU through
                             ``waiting → resumed → executing`` (status
                             bookkeeping only).

``_waiting[flow_run.id]``  — registered here with a callback that creates a
                             fresh ``PersistentFlowRunner`` and calls
                             ``runner.resume(run_id)`` (actual flow execution).

Both entries wait on the same event name.  When the event fires,
``notify_event()`` delivers BOTH callbacks.  They act on different objects
(ExecutionUnit row vs FlowRun state machine) and are complementary — removing
either would leave the execution in a broken half-state.
``ExecutionUnitService.resume_execution_unit`` carries its own DB-level
idempotency guard (skips if EU is already ``resumed/executing/completed``),
so even if the FlowRun callback drives the EU to completion before the EU
callback fires, the EU callback becomes a safe no-op.

Scope
-----
Event-type waits are the canonical path (``waiting_for`` field).  Time-based
waits are also supported via ``state["trigger_at"]`` / ``state["wait_until"]``
for future time-based WAIT nodes.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

# Module-level imports keep these patchable in tests via
# "core.flow_run_rehydration.<name>".
from core.wait_condition import WaitCondition, _parse_utc_datetime
from kernel.scheduler_engine import get_scheduler_engine

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def derive_wait_condition_from_flow(flow_run) -> "WaitCondition | None":
    """Derive a scheduler-compatible WaitCondition from a FlowRun's persisted fields.

    Priority
    --------
    1. ``waiting_for`` (event name string) → ``WaitCondition.for_event``
       This covers all flow-engine WAIT registrations; it is the canonical field.
    2. ``state["trigger_at"]`` or ``state["wait_until"]`` → ``WaitCondition.for_time``
       Fallback for future time-based WAIT nodes that store a trigger datetime in state.
    3. Returns ``None`` if neither condition is detectable — the caller must skip the run.

    Args:
        flow_run: A ``FlowRun`` ORM instance (or any object with matching attributes).

    Returns:
        A ``WaitCondition``, or ``None`` if the condition cannot be determined.
    """
    run_id = str(getattr(flow_run, "id", "") or "")
    correlation_id = str(flow_run.trace_id or run_id) if run_id else None

    # ── 1. Event-based (canonical path) ──────────────────────────────────────
    waiting_for = getattr(flow_run, "waiting_for", None)
    if waiting_for:
        return WaitCondition.for_event(waiting_for, correlation_id=correlation_id)

    # ── 2. Time-based (state fallback) ───────────────────────────────────────
    state = getattr(flow_run, "state", None) or {}
    if isinstance(state, dict):
        raw_trigger = state.get("trigger_at") or state.get("wait_until")
        if raw_trigger:
            trigger_at = _parse_utc_datetime(raw_trigger)
            if trigger_at is not None:
                return WaitCondition.for_time(trigger_at, correlation_id=correlation_id)
            logger.warning(
                "[flow_rehydrate] run=%s has state trigger but value is unparseable: %r",
                run_id,
                raw_trigger,
            )

    return None


def rehydrate_waiting_flow_runs(db: "Session") -> int:
    """Re-register all waiting FlowRuns with the SchedulerEngine.

    Args:
        db: An active SQLAlchemy session.  Closed by the caller — do NOT
            close it inside this function.

    Returns:
        Number of FlowRuns successfully re-registered.
    """
    from db.models.flow_run import FlowRun
    from db.models.execution_unit import ExecutionUnit

    scheduler = get_scheduler_engine()

    # ── 1. Query all waiting FlowRuns ──────────────────────────────────────────
    try:
        waiting_runs = (
            db.query(FlowRun)
            .filter(FlowRun.status == "waiting")
            .all()
        )
    except Exception as exc:
        logger.warning(
            "[flow_rehydrate] Could not query waiting FlowRuns (non-fatal): %s", exc
        )
        return 0

    if not waiting_runs:
        logger.info("[flow_rehydrate] No waiting FlowRuns found — nothing to rehydrate.")
        return 0

    logger.info(
        "[flow_rehydrate] Found %d waiting FlowRun(s) — rehydrating...", len(waiting_runs)
    )

    # ── 2. Pre-load associated EUs for priority and eu_id context ──────────────
    # A single bulk query avoids N+1. EU context is optional — proceed without
    # it if the query fails or the EU has been removed.
    run_ids = [str(r.id) for r in waiting_runs]
    eu_by_run_id: dict[str, object] = {}  # str(flow_run_id) → ExecutionUnit
    try:
        eus = (
            db.query(ExecutionUnit)
            .filter(ExecutionUnit.flow_run_id.in_(run_ids))
            .all()
        )
        for eu in eus:
            if eu.flow_run_id and eu.flow_run_id not in eu_by_run_id:
                eu_by_run_id[eu.flow_run_id] = eu
    except Exception as exc:
        logger.debug(
            "[flow_rehydrate] EU pre-load skipped (continuing without EU context): %s", exc
        )

    rehydrated = 0
    skipped = 0

    for run in waiting_runs:
        run_id = str(run.id)

        # ── EU context (resolved early — needed by both guards below) ─────────
        # Best-effort: EU may not exist if it was cleaned up or never created.
        eu = eu_by_run_id.get(run_id)
        eu_id: str = str(eu.id) if eu else ""
        priority: str = (eu.priority if eu else None) or "normal"

        # ── Guard 1: FlowRun-level callback already registered ────────────────
        # Covers: second call to this function, or any other code path that
        # registered under flow_run.id before us.  Dict assignment in
        # register_wait() would overwrite silently — skip to avoid redundant
        # log noise and unnecessary callback recreation.
        if scheduler.waiting_for(run_id) is not None:
            logger.debug(
                "[flow_rehydrate] run=%s already has FlowRun-level callback "
                "in scheduler registry — skipped",
                run_id,
            )
            skipped += 1
            continue

        # ── Guard 2: EU-level callback already registered — PROCEED, log only ─
        # rehydrate_waiting_eus() registers _waiting[eu.id] with an EU status
        # callback.  This function registers _waiting[flow_run.id] with a
        # PersistentFlowRunner resume callback.  Both entries fire when the
        # event arrives; they are complementary, not conflicting:
        #   • EU callback  → waiting → resumed → executing  (bookkeeping)
        #   • FlowRun cb   → PersistentFlowRunner.resume()  (flow execution)
        # ExecutionUnitService.resume_execution_unit() carries its own
        # idempotency guard so a race where the FlowRun callback completes
        # the EU before the EU callback fires is safe.
        # We do NOT skip here — omitting the FlowRun callback would leave the
        # flow permanently stuck after restart.
        if eu_id and scheduler.waiting_for(eu_id) is not None:
            logger.debug(
                "[flow_rehydrate] run=%s eu=%s: EU-level callback already "
                "registered — adding FlowRun-level callback alongside it "
                "(dual-callback coexistence, both required)",
                run_id,
                eu_id,
            )

        # ── Derive wait condition (event or time-based) ───────────────────────
        wait_condition = derive_wait_condition_from_flow(run)
        if wait_condition is None:
            logger.warning(
                "[flow_rehydrate] run=%s has status=waiting but no resolvable wait "
                "condition — cannot rehydrate (manual intervention required)",
                run_id,
            )
            skipped += 1
            continue

        # ── Registration parameters ────────────────────────────────────────────
        tenant_id = str(run.user_id or "system")
        correlation_id = run.trace_id or run_id

        # ── Resume callback ────────────────────────────────────────────────────
        # The closure must capture all values needed at callback time.
        # The startup `db` will be closed long before any event fires — the
        # callback opens its own session via SessionLocal().
        #
        # Execution ordering guarantee
        # ----------------------------
        # 1. FlowRun atomic claim  (UPDATE WHERE status='waiting')
        # 2. EU status transition  (waiting → resumed → executing) — only if claim won
        # 3. Flow execution        (PersistentFlowRunner.resume)    — only if claim won
        #
        # The claim is the single gatekeeper.  If another instance wins the
        # claim (rowcount=0), both EU resume and flow execution are skipped
        # entirely — no bookkeeping side-effects on the losing instance.
        # PersistentFlowRunner.resume() also carries an internal claim guard
        # as a last-line safety net; when called from here, it naturally
        # bypasses that guard because status is already "executing".
        def _make_resume_callback(
            r_id: str,
            flow_name: str,
            user_id,
            workflow_type: str,
            eid: str,
        ):
            def _callback() -> None:
                from db.database import SessionLocal
                from runtime.flow_engine import FLOW_REGISTRY, PersistentFlowRunner

                flow = FLOW_REGISTRY.get(flow_name)
                if flow is None:
                    logger.warning(
                        "[flow_rehydrate] resume callback: flow=%r not in FLOW_REGISTRY "
                        "for run=%s — skipping resume",
                        flow_name,
                        r_id,
                    )
                    return

                _db = SessionLocal()
                try:
                    # ── Step 1: FlowRun atomic claim ──────────────────────────
                    # UPDATE WHERE status='waiting' ensures exactly one instance
                    # proceeds.  All others see rowcount=0 and exit immediately.
                    from db.models.flow_run import FlowRun as _FlowRun

                    claimed = (
                        _db.query(_FlowRun)
                        .filter(_FlowRun.id == r_id, _FlowRun.status == "waiting")
                        .update({"status": "executing"}, synchronize_session=False)
                    )
                    try:
                        _db.commit()
                    except Exception as _claim_exc:
                        logger.warning(
                            "[flow_rehydrate] claim commit failed for run=%s: %s",
                            r_id, _claim_exc,
                        )
                        try:
                            _db.rollback()
                        except Exception:
                            pass
                        return  # concurrency commit failure — skip safely

                    if claimed == 0:
                        logger.info(
                            "[flow_rehydrate] run=%s already claimed by another instance "
                            "— skipping EU resume and flow execution",
                            r_id,
                        )
                        return

                    # ── Step 2: EU status transition ──────────────────────────
                    # Only reached by the instance that won the claim.
                    # EU idempotency guard in ExecutionUnitService prevents any
                    # double-transition if this is somehow called twice.
                    if eid:
                        try:
                            from core.execution_unit_service import ExecutionUnitService
                            ExecutionUnitService(_db).resume_execution_unit(eid)
                        except Exception as _eu_exc:
                            logger.warning(
                                "[flow_rehydrate] EU resume failed for eu=%s run=%s "
                                "(non-fatal, flow execution proceeds): %s",
                                eid, r_id, _eu_exc,
                            )

                    # ── Step 3: Flow execution ────────────────────────────────
                    # FlowRun status is now "executing"; runner.resume()'s
                    # internal claim guard is bypassed (status != "waiting").
                    runner = PersistentFlowRunner(
                        flow=flow,
                        db=_db,
                        user_id=user_id,
                        workflow_type=workflow_type,
                    )
                    runner.resume(r_id)

                except Exception as _exc:
                    logger.warning(
                        "[flow_rehydrate] resume callback failed for run=%s: %s",
                        r_id,
                        _exc,
                    )
                finally:
                    _db.close()

            return _callback

        # ── Register with SchedulerEngine ──────────────────────────────────────
        # For time-based waits, wait_for_event is None; the scheduler uses
        # wait_condition.trigger_at instead.  For event-based waits it is the
        # event name string.
        wait_for_event = wait_condition.event_name  # None for time-based
        try:
            scheduler.register_wait(
                run_id=run_id,
                wait_for_event=wait_for_event,
                tenant_id=tenant_id,
                eu_id=eu_id,
                resume_callback=_make_resume_callback(
                    run_id,
                    run.flow_name,
                    run.user_id,
                    run.workflow_type or "flow",
                    eu_id,
                ),
                priority=priority,
                correlation_id=correlation_id,
                trace_id=run.trace_id,
                eu_type="flow",
                wait_condition=wait_condition,
            )
            rehydrated += 1
            logger.info(
                "[flow_rehydrate] registered run=%s flow=%r condition=%s/%r",
                run_id,
                run.flow_name,
                wait_condition.type,
                wait_condition.event_name or wait_condition.trigger_at,
            )
        except Exception as exc:
            logger.warning(
                "[flow_rehydrate] Failed to register run=%s: %s", run_id, exc
            )
            skipped += 1

    logger.info(
        "[flow_rehydrate] complete — registered=%d skipped=%d total=%d",
        rehydrated,
        skipped,
        len(waiting_runs),
    )
    return rehydrated
