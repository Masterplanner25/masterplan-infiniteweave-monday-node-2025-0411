"""Dead-letter transitions for timed-out WAIT flows."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

DEAD_LETTER_STATUS = "dead_letter"


def move_to_dead_letter(
    db,
    flow_run_id: str,
    *,
    reason: str,
) -> bool:
    """
    Transition a FlowRun from status="waiting" to status="dead_letter".
    Returns True if the transition succeeded, False if the row was not in
    waiting status (already recovered by another instance).
    Thread-safe via optimistic update - only transitions if status="waiting".
    """
    from datetime import datetime, timezone

    from AINDY.db.models.flow_run import FlowRun

    now = datetime.now(timezone.utc)
    rows_updated = (
        db.query(FlowRun)
        .filter(
            FlowRun.id == flow_run_id,
            FlowRun.status == "waiting",
        )
        .update(
            {
                FlowRun.status: DEAD_LETTER_STATUS,
                FlowRun.dead_letter_reason: reason,
                FlowRun.dead_lettered_at: now,
                FlowRun.updated_at: now,
                FlowRun.waiting_for: None,
                FlowRun.wait_deadline: None,
                FlowRun.error_message: reason,
                FlowRun.completed_at: now,
            },
            synchronize_session=False,
        )
    )
    if rows_updated:
        db.commit()
        logger.warning(
            "[dead_letter] FlowRun %s moved to dead_letter: %s",
            flow_run_id,
            reason,
        )
        _emit_dead_letter_event(flow_run_id, reason)
        return True
    return False


def _emit_dead_letter_event(flow_run_id: str, reason: str) -> None:
    try:
        from AINDY.core.observability_events import emit_observability_event

        emit_observability_event(
            event_type="flow_run.dead_lettered",
            payload={
                "flow_run_id": flow_run_id,
                "reason": reason,
            },
        )
    except Exception as exc:
        logger.debug("[dead_letter] Observability event failed (non-fatal): %s", exc)

    try:
        from AINDY.platform_layer.metrics import flow_runs_dead_lettered_total

        flow_runs_dead_lettered_total.labels(reason=reason).inc()
    except Exception:
        pass


def list_dead_lettered_runs(
    db,
    *,
    limit: int = 50,
    user_id: str | None = None,
) -> list[dict]:
    """List recent dead-lettered FlowRuns, newest first."""
    from AINDY.db.models.flow_run import FlowRun

    query = db.query(FlowRun).filter(FlowRun.status == DEAD_LETTER_STATUS)
    if user_id:
        query = query.filter(FlowRun.user_id == user_id)
    rows = query.order_by(FlowRun.dead_lettered_at.desc()).limit(limit).all()
    return [_flow_run_to_dict(row) for row in rows]


def _flow_run_to_dict(run) -> dict:
    return {
        "id": str(run.id),
        "flow_name": run.flow_name,
        "workflow_type": run.workflow_type,
        "status": run.status,
        "dead_letter_reason": run.dead_letter_reason,
        "dead_lettered_at": (
            run.dead_lettered_at.isoformat() if run.dead_lettered_at else None
        ),
        "user_id": str(run.user_id) if run.user_id else None,
        "trace_id": run.trace_id,
        "waiting_for": run.waiting_for,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "updated_at": run.updated_at.isoformat() if run.updated_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }
