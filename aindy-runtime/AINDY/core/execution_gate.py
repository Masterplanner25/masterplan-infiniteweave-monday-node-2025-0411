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
        extra={"operation_name": operation_name, "task_name": task_name, "workflow_type": "memory_nodus_execute"},
    )
    # eu.extra["retry_policy"] is now populated.

    # After execution, normalise the result:
    envelope = nodus_result_to_envelope(nodus_result, eu_id=str(eu.id), trace_id=eu_id)
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# ── Cross-type WAIT signal ────────────────────────────────────────────────────


class ExecutionWaitSignal(Exception):
    """
    Raise from any handler to request an EU-level WAIT transition without
    going through the flow engine.

    The existing flow-engine WAIT mechanism (a flow node returns
    ``{"status": "WAIT", "wait_for": "event_type"}``) is preserved and
    continues to trigger the EU transition via dict-based detection in the
    pipeline.  This signal provides the same capability to agents, jobs,
    and bare operation handlers that do not run inside a ``FlowRun``.

    The pipeline catches this *before* ``HTTPException`` and ``Exception``
    so it is never misclassified as a failure.  The EU is transitioned to
    ``"waiting"`` and an ``execution.waiting`` SystemEvent is emitted.

    Usage
    -----
        from AINDY.core.execution_gate import ExecutionWaitSignal
        from AINDY.core.wait_condition import WaitCondition

        # Event-based (default):
        raise ExecutionWaitSignal(
            "payment.confirmed",
            resume_key="invoice_123",
            payload={"invoice_id": "inv_123"},
        )

        # Time-based (explicit WaitCondition):
        from datetime import datetime, timezone, timedelta
        raise ExecutionWaitSignal(
            "timer.expired",
            wait_condition=WaitCondition.for_time(
                datetime.now(timezone.utc) + timedelta(hours=1)
            ),
        )

        # External trigger:
        raise ExecutionWaitSignal(
            "webhook.received",
            wait_condition=WaitCondition.for_external("webhook.received"),
        )

    Parameters
    ----------
    wait_for:
        The event type that will resume this EU.  Also used as the default
        ``event_name`` when no explicit ``wait_condition`` is supplied.
    resume_key:
        Optional idempotency / targeting key so resume endpoints can locate
        this EU by key rather than by id.
    payload:
        Arbitrary extra context stored alongside the wait event.
    wait_condition:
        Structured ``WaitCondition`` instance.  When provided, takes
        precedence over deriving a condition from ``wait_for`` alone.
        Defaults to ``WaitCondition.for_event(wait_for)`` when absent.

    Note
    ----
    Do NOT use this to signal errors — raise ``HTTPException`` or a plain
    ``Exception`` instead.  WAIT is a non-terminal, resumable execution state.
    """

    def __init__(
        self,
        wait_for: str,
        *,
        resume_key: str | None = None,
        payload: dict[str, Any] | None = None,
        wait_condition: Optional[Any] = None,  # WaitCondition | None
    ) -> None:
        self.wait_for = wait_for        # event type the EU is waiting for
        self.resume_key = resume_key    # optional resume targeting / idempotency key
        self.payload = dict(payload or {})
        self.wait_condition = wait_condition  # WaitCondition | None
        super().__init__(f"execution.wait:{wait_for}")


# ── Retry-policy resolution ───────────────────────────────────────────────────

# Map eu_type to the execution_type expected by resolve_retry_policy().
# "job" covers both AutomationLog jobs and bare Nodus execution.
# "task" remains accepted as a legacy operation label and falls back to job policy.
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
    from AINDY.core.retry_policy import resolve_retry_policy

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
    from AINDY.core.execution_unit_service import ExecutionUnitService

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


# ── Gate + dispatch ───────────────────────────────────────────────────────────


def gate_and_dispatch(
    *,
    db: Session,
    eu_type: str,
    user_id: str,
    source_type: str,
    source_id: str,
    handler_fn: Callable[[], Any],
    trace_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
    extra: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    Combined gate + dispatch entry point.

    Sequence
    --------
    1. ``require_execution_unit()`` — ensure a DB-backed EU exists and is set
       to "executing" before any work starts.  Non-fatal on failure.
    2. ``dispatch(eu, handler_fn, context)`` — delegate to ExecutionDispatcher
       for the INLINE vs ASYNC decision.
    3. Return a canonical ExecutionEnvelope:
       - **INLINE**: handler completed synchronously; ``status`` reflects the
         result (SUCCESS / FAILURE).  ``output`` is the handler's return value.
       - **ASYNC**: handler was submitted to the shared ThreadPoolExecutor;
         returns immediately with ``status="QUEUED"`` so the caller can respond
         without blocking.  ``trace_id`` and ``eu_id`` are preserved so the
         client can poll for the result.

    Handler contract
    ----------------
    ``handler_fn`` must be a zero-argument callable whose return value becomes
    ``output`` in the INLINE envelope.  Build any closures you need before
    calling this function.  Suggested mapping by ``eu_type``:

        flow   → lambda: run_flow(...)
        agent  → lambda: execute_run(...)
        nodus  → lambda: run_nodus_script_via_flow(...)
        job    → lambda: _execute_job_inline(...)
        task   → lambda: operation_handler(...)  # legacy operation label

    Parameters
    ----------
    db:
        Active SQLAlchemy session for EU creation / status update.
    eu_type:
        One of "flow", "agent", "nodus", "job", or legacy "task".  Drives both the
        retry-policy resolution in ``require_execution_unit()`` and the
        INLINE/ASYNC decision in ``ExecutionDispatcher``.
    user_id:
        Owner of the execution; stored on the EU row.
    source_type / source_id:
        Idempotency key pair — same pair returns the existing EU if one
        already exists.
    handler_fn:
        Zero-argument callable.  Closed over all runtime arguments it needs.
    trace_id:
        Propagated into the returned envelope.  If None, falls back to
        ``source_id`` so the envelope always carries a traceable ID.
    correlation_id:
        Optional correlation id stored on the EU.  Defaults to ``source_id``.
    extra:
        Arbitrary JSONB metadata forwarded to ``require_execution_unit()``.
        Keys ``risk_level`` and ``workflow_type`` influence retry-policy
        resolution; ``async_hint`` overrides the dispatch-mode decision.
    """
    from AINDY.core.execution_dispatcher import ExecutionMode, dispatch

    start = time.monotonic()

    eu = require_execution_unit(
        db=db,
        eu_type=eu_type,
        user_id=user_id,
        source_type=source_type,
        source_id=source_id,
        correlation_id=correlation_id,
        extra=extra,
    )

    eu_id_str: Optional[str] = str(eu.id) if eu is not None else None
    effective_trace_id = trace_id or source_id

    context: dict[str, Any] = {
        "eu_id": eu_id_str,
        "trace_id": effective_trace_id,
    }

    result = dispatch(eu, handler_fn=handler_fn, context=context)

    if result.mode is ExecutionMode.ASYNC:
        # Work is running in the background — return a QUEUED envelope so the
        # caller can respond immediately.  trace_id and eu_id are preserved so
        # the client can use them to poll.
        return to_envelope(
            eu_id=eu_id_str,
            trace_id=effective_trace_id,
            status="QUEUED",
            output=None,
            error=None,
            duration_ms=None,
            attempt_count=None,
        )

    # INLINE — handler completed synchronously.
    duration_ms = round((time.monotonic() - start) * 1000, 2)
    handler_result = result.envelope  # raw return value of handler_fn()

    # If the handler already returned an envelope-shaped dict, pass it through
    # enriched with our eu_id / trace_id so callers always see those fields.
    if isinstance(handler_result, dict) and "status" in handler_result:
        handler_result.setdefault("eu_id", eu_id_str)
        handler_result.setdefault("trace_id", effective_trace_id)
        if handler_result.get("duration_ms") is None:
            handler_result["duration_ms"] = duration_ms
        return handler_result

    # Plain return value — wrap it in a SUCCESS envelope.
    return to_envelope(
        eu_id=eu_id_str,
        trace_id=effective_trace_id,
        status="SUCCESS",
        output=handler_result,
        error=None,
        duration_ms=duration_ms,
        attempt_count=1,
    )


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
