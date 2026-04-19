"""
StuckRunService — Sprint N+7 Agent Observability Phase 1

Detects and recovers FlowRun rows that are stranded in status="running"
after a process crash or unclean shutdown.

scan_and_recover_stuck_runs()
  └─ Query FlowRun.status="running" older than threshold
       ├─ workflow_type="agent_execution"
       │    Mark FlowRun + linked AgentRun as failed
       │    Populate AgentRun.result from completed AgentStep rows
       └─ all other types
            Mark FlowRun as failed (log only — no linked model to update)

The function never raises — startup must not be blocked by recovery errors.
Each stuck run is wrapped in its own try/except so one bad row cannot abort
the rest of the scan.

Env variable
============
AINDY_STUCK_RUN_THRESHOLD_MINUTES  (default: 10)
  Runs whose FlowRun.updated_at is older than this many minutes are
  considered stuck.  Exposed as a function parameter so tests can
  override it without patching env.
"""
import logging
import os
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)
from AINDY.core.execution_signal_helper import record_agent_event
from AINDY.core.observability_events import emit_observability_event

_RECOVERY_ERROR_MSG = "Stuck run recovery: process terminated before completion"


def _recovery_error_detail(*, detected_at: datetime) -> dict[str, str]:
    return {
        "reason": "stuck_run_recovered",
        "detected_at": detected_at.isoformat(),
    }


def _default_threshold_minutes() -> int:
    try:
        return int(os.getenv("AINDY_STUCK_RUN_THRESHOLD_MINUTES", "10"))
    except (ValueError, TypeError):
        return 10


# ── Agent-execution recovery ──────────────────────────────────────────────────

def _recover_agent_run(flow_run, db: Session) -> None:
    """
    Recover one agent_execution FlowRun.

    Finds the linked AgentRun by flow_run_id, loads all completed
    AgentStep audit rows, then marks both FlowRun and AgentRun as failed.
    """
    from AINDY.db.models.agent_run import AgentRun, AgentStep

    recovered_at = datetime.now(timezone.utc)
    # Mark the FlowRun terminal
    flow_run.status = "failed"
    flow_run.waiting_for = None
    flow_run.wait_deadline = None
    flow_run.error_message = _RECOVERY_ERROR_MSG
    flow_run.error_detail = _recovery_error_detail(detected_at=recovered_at)
    flow_run.completed_at = recovered_at

    # Find the linked AgentRun
    agent_run = (
        db.query(AgentRun)
        .filter(AgentRun.flow_run_id == str(flow_run.id))
        .first()
    )
    if not agent_run:
        logger.warning(
            "[StuckRunService] No AgentRun linked to FlowRun %s — FlowRun marked failed only",
            flow_run.id,
        )
        return

    if agent_run.status != "executing":
        # Already finalised by another path; nothing to do
        return

    # Reconstruct result from whatever AgentStep rows were committed
    completed_steps = (
        db.query(AgentStep)
        .filter(AgentStep.run_id == agent_run.id)
        .order_by(AgentStep.step_index.asc())
        .all()
    )
    step_results = [
        {
            "step_index": s.step_index,
            "tool": s.tool_name,
            "status": s.status,
            "result": s.result,
            "error": s.error_message,
        }
        for s in completed_steps
    ]

    agent_run.status = "failed"
    agent_run.completed_at = recovered_at
    agent_run.error_message = _RECOVERY_ERROR_MSG
    agent_run.result = {"steps": step_results}

    logger.warning(
        "[StuckRunService] Recovered AgentRun %s (flow_run=%s, %d steps committed)",
        agent_run.id,
        flow_run.id,
        len(step_results),
    )


# ── Generic recovery ──────────────────────────────────────────────────────────

def _recover_generic_run(flow_run, db: Session) -> None:
    """Mark a non-agent FlowRun as failed — log only, no linked model."""
    recovered_at = datetime.now(timezone.utc)
    flow_run.status = "failed"
    flow_run.waiting_for = None
    flow_run.wait_deadline = None
    flow_run.error_message = _RECOVERY_ERROR_MSG
    flow_run.error_detail = _recovery_error_detail(detected_at=recovered_at)
    flow_run.completed_at = recovered_at
    logger.warning(
        "[StuckRunService] Recovered generic FlowRun %s (type=%s)",
        flow_run.id,
        flow_run.workflow_type,
    )


# ── Public entry point ────────────────────────────────────────────────────────

def recover_stuck_agent_run(
    run_id: str,
    user_id: str,
    db: Session,
    force: bool = False,
) -> dict:
    """
    Manually recover a single stuck AgentRun.

    Returns a result dict:
      {"ok": True,  "run": <run_dict>}
      {"ok": False, "error_code": "not_found"}
      {"ok": False, "error_code": "forbidden"}
      {"ok": False, "error_code": "wrong_status",
                    "detail": "Run is not in executing state"}
      {"ok": False, "error_code": "too_recent",
                    "detail": "Run started less than N minutes ago (use ?force=true to override)"}

    Callers map error_code to the appropriate HTTP status:
      not_found   → 404
      forbidden   → 403
      wrong_status / too_recent → 409
    """
    from AINDY.db.models.agent_run import AgentRun, AgentStep
    from AINDY.db.models.flow_run import FlowRun
    from AINDY.agents.agent_runtime import _run_to_dict

    threshold_minutes = _default_threshold_minutes()

    try:
        run = db.query(AgentRun).filter(AgentRun.id == run_id).first()
        if not run:
            return {"ok": False, "error_code": "not_found"}

        if run.user_id != user_id:
            return {"ok": False, "error_code": "forbidden"}

        if run.status != "executing":
            return {
                "ok": False,
                "error_code": "wrong_status",
                "detail": "Run is not in executing state",
            }

        if not force and run.started_at:
            age = datetime.now(timezone.utc) - run.started_at
            if age < timedelta(minutes=threshold_minutes):
                remaining = threshold_minutes - int(age.total_seconds() / 60)
                return {
                    "ok": False,
                    "error_code": "too_recent",
                    "detail": (
                        f"Run started less than {threshold_minutes} minutes ago "
                        f"(use ?force=true to override)"
                    ),
                }

        # Mark linked FlowRun failed if present
        if run.flow_run_id:
            flow_run = (
                db.query(FlowRun)
                .filter(FlowRun.id == run.flow_run_id)
                .first()
            )
            if flow_run and flow_run.status == "running":
                recovered_at = datetime.now(timezone.utc)
                flow_run.status = "failed"
                flow_run.waiting_for = None
                flow_run.wait_deadline = None
                flow_run.error_message = _RECOVERY_ERROR_MSG
                flow_run.error_detail = _recovery_error_detail(detected_at=recovered_at)
                flow_run.completed_at = recovered_at

        # Reconstruct result from committed AgentStep rows
        completed_steps = (
            db.query(AgentStep)
            .filter(AgentStep.run_id == run.id)
            .order_by(AgentStep.step_index.asc())
            .all()
        )
        step_results = [
            {
                "step_index": s.step_index,
                "tool": s.tool_name,
                "status": s.status,
                "result": s.result,
                "error": s.error_message,
            }
            for s in completed_steps
        ]

        run.status = "failed"
        run.completed_at = datetime.now(timezone.utc)
        run.error_message = _RECOVERY_ERROR_MSG
        run.result = {"steps": step_results}
        db.commit()

        logger.warning(
            "[StuckRunService] Manual recovery: AgentRun %s marked failed (%d steps)",
            run_id,
            len(step_results),
        )

        # Emit RECOVERED lifecycle event
        record_agent_event(
            run_id=str(run.id),
            user_id=run.user_id,
            event_type="RECOVERED",
            db=db,
            correlation_id=getattr(run, "correlation_id", None),
            payload={"recovered_at": run.completed_at.isoformat() if run.completed_at else None},
        )

        return {"ok": True, "run": _run_to_dict(run)}

    except Exception as exc:
        logger.error(
            "[StuckRunService] recover_stuck_agent_run failed for %s: %s", run_id, exc
        )
        try:
            db.rollback()
        except Exception as rollback_exc:
            emit_observability_event(
                logger,
                event="stuck_agent_recovery_rollback_failed",
                run_id=run_id,
                error=str(rollback_exc),
            )
        return {"ok": False, "error_code": "internal_error", "detail": str(exc)}


def scan_and_recover_stuck_runs(
    db: Session,
    staleness_minutes: int | None = None,
) -> int:
    """
    Scan for stuck FlowRun rows and mark them failed.

    A run is considered stuck when:
      - status == "running"
      - updated_at < now() - staleness_minutes

    Returns the number of runs recovered.
    Never raises — all exceptions are caught internally.
    """
    if staleness_minutes is None:
        staleness_minutes = _default_threshold_minutes()

    recovered = 0

    try:
        from AINDY.db.models.flow_run import FlowRun

        threshold_dt = datetime.now(timezone.utc) - timedelta(minutes=staleness_minutes)

        stuck_runs = (
            db.query(FlowRun)
            .filter(
                FlowRun.status == "running",
                FlowRun.updated_at < threshold_dt,
            )
            .all()
        )

        if not stuck_runs:
            logger.info(
                "[StuckRunService] Startup scan: no stuck runs (threshold=%dm)",
                staleness_minutes,
            )
            return 0

        logger.warning(
            "[StuckRunService] Startup scan: found %d stuck run(s) (threshold=%dm)",
            len(stuck_runs),
            staleness_minutes,
        )

        for flow_run in stuck_runs:
            try:
                if flow_run.workflow_type == "agent_execution":
                    _recover_agent_run(flow_run, db)
                else:
                    _recover_generic_run(flow_run, db)

                db.commit()
                recovered += 1

            except Exception as exc:
                logger.error(
                    "[StuckRunService] Failed to recover FlowRun %s: %s",
                    flow_run.id,
                    exc,
                )
                try:
                    db.rollback()
                except Exception as rollback_exc:
                    emit_observability_event(
                        logger,
                        event="stuck_run_scan_rollback_failed",
                        flow_run_id=str(flow_run.id),
                        error=str(rollback_exc),
                    )

    except Exception as exc:
        logger.error(
            "[StuckRunService] Startup scan aborted with unexpected error: %s", exc
        )

    return recovered

