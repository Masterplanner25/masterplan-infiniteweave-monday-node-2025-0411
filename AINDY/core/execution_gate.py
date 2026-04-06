"""
ExecutionGate — thin unification layer across all execution paths.

Purpose
-------
Enforce two invariants without rewriting any runtime:

  1. Every execution path has a DB-backed ExecutionUnit BEFORE work begins.
     Previously, bare Nodus execution created the EU after-the-fact (or not at
     all).  ``require_execution_unit()`` is idempotent and must be called at
     the start of any execution entrypoint that isn't already routed through
     PersistentFlowRunner (which creates a FlowRun that maps to an EU).

  2. All runtimes return the same ExecutionEnvelope shape.
     The adapter functions below normalise each runtime's native result type
     into the canonical envelope without modifying the runtimes themselves.

  3. Every ExecutionUnit carries a ``retry_policy`` in its ``extra`` field.
     The policy is resolved from ``eu_type`` + caller-supplied context and
     stored as a plain dict under ``extra["retry_policy"]`` so any code that
     has access to the EU can read the intended retry semantics without
     importing RetryPolicy directly.

ExecutionEnvelope shape
-----------------------
    {
        "eu_id":          str | None   # ExecutionUnit.id or run_id
        "trace_id":       str | None
        "status":         str          # upper-case: SUCCESS, FAILURE, WAITING, …
        "output":         Any          # runtime-specific result payload
        "error":          str | None
        "duration_ms":    float | None
        "attempt_count":  int | None
    }

Old-model mapping
-----------------
    FlowRun          → flow_result_to_envelope()
    AgentRun         → agent_result_to_envelope()
    NodusExecutionResult → nodus_result_to_envelope()
    AutomationLog    → job_result_to_envelope()

Usage
-----
    # Ensure EU exists before entering the VM:
    eu = require_execution_unit(
        db=db, eu_type="job", user_id=user_id,
        source_type="memory_nodus_execute", source_id=eu_id,
        extra={"task_name": task_name, "workflow_type": "memory_nodus_execute"},
    )
    # eu.extra["retry_policy"] is now populated.

    # After execution, normalise the result:
    envelope = nodus_result_to_envelope(nodus_result, eu_id=str(eu.id), trace_id=eu_id)
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# ── Retry-policy resolution ───────────────────────────────────────────────────

# Map eu_type to the execution_type expected by resolve_retry_policy().
# "job" covers both AutomationLog jobs and bare Nodus execution.
_EU_TYPE_TO_EXEC_TYPE: dict[str, str] = {
    "flow": "flow",
    "agent": "agent",
    "job": "job",
    "nodus": "nodus",
}


def _resolve_policy_for_eu(eu_type: str, extra: dict[str, Any]) -> dict[str, Any]:
    """
    Derive a RetryPolicy for an ExecutionUnit and return it serialised as a
    plain dict (safe for JSONB storage).

    Resolution order:
      1. ``extra["risk_level"]``  — agent risk (low / medium / high)
      2. ``extra["workflow_type"]`` — checked for "nodus_*" to route to nodus
      3. ``eu_type`` mapped to execution_type via ``_EU_TYPE_TO_EXEC_TYPE``
    """
    from core.retry_policy import resolve_retry_policy

    exec_type = _EU_TYPE_TO_EXEC_TYPE.get((eu_type or "").lower(), "job")

    # Nodus scheduled jobs carry workflow_type="nodus_*"
    workflow_type = extra.get("workflow_type") or ""
    if workflow_type.startswith("nodus"):
        exec_type = "nodus"

    risk_level: Optional[str] = extra.get("risk_level")

    policy = resolve_retry_policy(execution_type=exec_type, risk_level=risk_level)
    return {
        "max_attempts": policy.max_attempts,
        "backoff_ms": policy.backoff_ms,
        "exponential_backoff": policy.exponential_backoff,
        "high_risk_immediate_fail": policy.high_risk_immediate_fail,
    }


# ── EU gate ───────────────────────────────────────────────────────────────────


def require_execution_unit(
    *,
    db: Session,
    eu_type: str,
    user_id: str,
    source_type: str,
    source_id: str,
    correlation_id: str | None = None,
    extra: dict[str, Any] | None = None,
):
    """
    Ensure a DB-backed ExecutionUnit exists for (source_type, source_id) before
    any execution work begins.

    - If an EU already exists, transitions it to "executing" and returns it.
    - If no EU exists, creates one with status="executing" and returns it.
    - Returns None on failure (non-fatal — callers must not block on this).

    This is idempotent: calling it twice for the same source is safe.

    RetryPolicy
    -----------
    A ``retry_policy`` dict is always embedded in ``eu.extra`` so any code
    that holds the EU can read the intended retry semantics without importing
    ``RetryPolicy`` directly.  The policy is resolved from ``eu_type`` plus
    any ``risk_level`` / ``workflow_type`` keys already present in ``extra``.
    Callers that need a non-default policy should set those keys in ``extra``
    before calling this function.
    """
    from core.execution_unit_service import ExecutionUnitService

    try:
        merged_extra: dict[str, Any] = dict(extra or {})
        merged_extra["retry_policy"] = _resolve_policy_for_eu(eu_type, merged_extra)

        eus = ExecutionUnitService(db)
        eu = eus.get_by_source(source_type, source_id)
        if eu is None:
            eu = eus.create(
                eu_type=eu_type,
                user_id=user_id,
                source_type=source_type,
                source_id=source_id,
                correlation_id=correlation_id or source_id,
                status="executing",
                extra=merged_extra,
            )
            logger.debug(
                "[ExecutionGate] EU created source=%s/%s eu_id=%s policy=%s",
                source_type,
                source_id,
                getattr(eu, "id", None),
                merged_extra["retry_policy"],
            )
        else:
            eus.update_status(eu.id, "executing")
            # Backfill retry_policy on existing EU if not yet stored.
            if eu.extra is None or "retry_policy" not in eu.extra:
                current_extra = dict(eu.extra or {})
                current_extra["retry_policy"] = merged_extra["retry_policy"]
                eu.extra = current_extra
                try:
                    db.flush()
                except Exception:
                    pass  # non-fatal; policy is still readable from merged_extra
            logger.debug(
                "[ExecutionGate] EU transitioned→executing source=%s/%s eu_id=%s policy=%s",
                source_type,
                source_id,
                eu.id,
                (eu.extra or {}).get("retry_policy"),
            )
        return eu
    except Exception as exc:
        logger.warning(
            "[ExecutionGate] require_execution_unit failed (non-fatal) source=%s/%s: %s",
            source_type,
            source_id,
            exc,
        )
        return None


# ── Canonical envelope ────────────────────────────────────────────────────────


def to_envelope(
    *,
    eu_id: str | None,
    trace_id: str | None,
    status: str,
    output: Any,
    error: str | None,
    duration_ms: float | None,
    attempt_count: int | None,
) -> dict[str, Any]:
    """
    Produce the canonical ExecutionEnvelope.

    All runtime-specific adapters below call this.  Callers that need to embed
    this in a larger response dict should use it as the value of an
    ``"execution_envelope"`` key so legacy shapes remain unchanged.
    """
    return {
        "eu_id": eu_id,
        "trace_id": str(trace_id) if trace_id else None,
        "status": status,
        "output": output,
        "error": error,
        "duration_ms": duration_ms,
        "attempt_count": attempt_count,
    }


# ── Adapters: old model → ExecutionEnvelope ───────────────────────────────────


def flow_result_to_envelope(
    flow_result: dict[str, Any],
    *,
    eu_id: str | None = None,
) -> dict[str, Any]:
    """
    Convert a PersistentFlowRunner result dict to the unified ExecutionEnvelope.

    FlowRun envelope shape (input):
        {status, data, result, events, trace_id, run_id, state, error}
    """
    raw_status = str(flow_result.get("status") or "UNKNOWN").upper()
    return to_envelope(
        eu_id=eu_id or flow_result.get("run_id"),
        trace_id=flow_result.get("trace_id"),
        status=raw_status,
        output=flow_result.get("data") or flow_result.get("result"),
        error=flow_result.get("error"),
        duration_ms=None,  # FlowRun does not expose wall-clock duration at envelope level
        attempt_count=None,
    )


def agent_result_to_envelope(run_dict: dict[str, Any]) -> dict[str, Any]:
    """
    Convert an AgentRun ``_run_to_dict`` result to the unified ExecutionEnvelope.

    AgentRun dict shape (input):
        {run_id, status, result, error_message, trace_id, ...}
    """
    raw_status = str(run_dict.get("status") or "UNKNOWN").upper()
    return to_envelope(
        eu_id=run_dict.get("run_id"),
        trace_id=run_dict.get("trace_id"),
        status=raw_status,
        output=run_dict.get("result"),
        error=run_dict.get("error_message"),
        duration_ms=_ms_between(run_dict.get("started_at"), run_dict.get("completed_at")),
        attempt_count=None,
    )


def nodus_result_to_envelope(
    nodus_result: Any,
    *,
    eu_id: str | None,
    trace_id: str | None,
    started_at_monotonic: float | None = None,
    attempt_count: int = 1,
) -> dict[str, Any]:
    """
    Convert a ``NodusExecutionResult`` dataclass to the unified ExecutionEnvelope.

    NodusExecutionResult fields used:
        status ("success" | "failure" | "waiting"), output_state, error
    """
    duration_ms = None
    if started_at_monotonic is not None:
        duration_ms = round((time.monotonic() - started_at_monotonic) * 1000, 2)

    raw_status = str(getattr(nodus_result, "status", None) or "UNKNOWN").upper()
    return to_envelope(
        eu_id=eu_id,
        trace_id=trace_id,
        status=raw_status,
        output=getattr(nodus_result, "output_state", None),
        error=getattr(nodus_result, "error", None),
        duration_ms=duration_ms,
        attempt_count=attempt_count,
    )


def job_result_to_envelope(log: Any, *, result: Any = None) -> dict[str, Any]:
    """
    Convert an ``AutomationLog`` ORM object to the unified ExecutionEnvelope.

    AutomationLog fields used:
        id, trace_id, status, error_message, result, started_at,
        completed_at, attempt_count
    """
    raw_status = str(getattr(log, "status", None) or "UNKNOWN").upper()
    return to_envelope(
        eu_id=str(log.id) if getattr(log, "id", None) else None,
        trace_id=getattr(log, "trace_id", None) or str(getattr(log, "id", None) or ""),
        status=raw_status,
        output=result if result is not None else getattr(log, "result", None),
        error=getattr(log, "error_message", None),
        duration_ms=_ms_between(
            getattr(log, "started_at", None),
            getattr(log, "completed_at", None),
        ),
        attempt_count=getattr(log, "attempt_count", None),
    )


# ── Private helpers ───────────────────────────────────────────────────────────


def _ms_between(
    started: str | datetime | None,
    completed: str | datetime | None,
) -> float | None:
    """Return wall-clock duration in ms between two ISO timestamps or datetimes."""
    if not started or not completed:
        return None
    try:
        def _parse(v: Any) -> datetime:
            if isinstance(v, datetime):
                return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
            from datetime import datetime as _dt
            parsed = _dt.fromisoformat(str(v).replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)

        return round((_parse(completed) - _parse(started)).total_seconds() * 1000, 2)
    except Exception:
        return None
