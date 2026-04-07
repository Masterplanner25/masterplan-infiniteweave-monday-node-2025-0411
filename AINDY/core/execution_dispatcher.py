"""
ExecutionDispatcher — unified INLINE vs ASYNC dispatch decision.

Purpose
-------
Centralise the single question every execution entry point must answer:
"Should I run this handler on the request thread (INLINE) or hand it off to
the shared ThreadPoolExecutor (ASYNC)?"

Nothing in this module modifies execution logic, FlowRunner, or
async_job_service internals.  It only decides *where* work runs and returns
a ``DispatchResult`` that callers can inspect.

Dispatch modes
--------------
INLINE
    handler_fn() is called directly on the caller's thread.
    Returns a completed ``DispatchResult`` with a populated ``envelope``.
    Suitable for lightweight, low-latency operations (e.g. task status
    mutations, watcher signal writes) that must not be queued.

ASYNC
    handler_fn() is submitted to the shared ThreadPoolExecutor owned by
    ``platform_layer.async_job_service``.  Returns a ``DispatchResult``
    with a ``future`` the caller can optionally poll; ``envelope`` is None
    until the future resolves.
    Required for flow, agent, and Nodus execution — work that is too heavy
    or too long-running to block a request thread.

Decision logic (``_decide_mode``)
----------------------------------
The mode is derived from ``ExecutionUnit.type`` and ``ExecutionUnit.extra``:

    eu.type == "flow"   → ASYNC
    eu.type == "agent"  → ASYNC
    eu.type == "nodus"  → ASYNC
    eu.type == "job"    → ASYNC  (async_job_service already manages these)
    eu.type == "task"   → INLINE (fast domain mutation)
    anything else       → INLINE (safe default for unknown types)

Overrides (checked first):
    eu.extra["async_hint"] == True   → ASYNC regardless of type
    eu.extra["async_hint"] == False  → INLINE regardless of type
    eu.extra["priority"] == "high"   → promote to ASYNC even if type = task

Usage
-----
    from core.execution_dispatcher import dispatch, ExecutionMode

    result = dispatch(eu, handler_fn=my_handler, context={"db": db})
    if result.mode is ExecutionMode.INLINE:
        return result.envelope          # dict — ready immediately
    else:
        # ASYNC: return a queued reference; the future runs in background
        return {"queued": True, "eu_id": str(eu.id)}
"""
from __future__ import annotations

import logging
import os
from concurrent.futures import Future
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


# ── Env-flag gate ─────────────────────────────────────────────────────────────

def async_heavy_execution_enabled() -> bool:
    """
    Single authoritative check for whether async heavy execution is on.

    Previously defined in ``platform_layer.async_job_service``; moved here so
    the dispatcher is the ONE place that makes the INLINE vs ASYNC decision.
    ``async_job_service`` re-exports this symbol for backward compatibility.

    Rules (evaluated in order):
      - ``TESTING=1``  / ``TEST_MODE=1``          → always False
      - ``AINDY_ASYNC_HEAVY_EXECUTION=1``          → True
      - default                                    → False (safe inline)
    """
    if os.getenv("TESTING", "false").lower() in {"1", "true", "yes"}:
        return False
    if os.getenv("TEST_MODE", "false").lower() in {"1", "true", "yes"}:
        return False
    return os.getenv("AINDY_ASYNC_HEAVY_EXECUTION", "false").lower() in {"1", "true", "yes"}

# Execution types that always go to the thread pool (when async is enabled).
_ASYNC_EU_TYPES: frozenset[str] = frozenset({"flow", "agent", "nodus", "job"})


class _JobDispatchStub:
    """
    Minimal EU stub for the async-job system's internal thread-pool submissions.

    Sets ``async_hint=True`` to bypass the global ``async_heavy_execution_enabled()``
    gate.  The job system already performs its own test-mode inline fallback before
    reaching any ``dispatch()`` call, so ASYNC is always correct at that point.
    """
    type = "job"
    priority = "normal"
    id = None
    extra: dict[str, Any] = {"async_hint": True}


#: Singleton stub — import this directly; do not instantiate.
JOB_DISPATCH_STUB = _JobDispatchStub()


class ExecutionMode(Enum):
    INLINE = "inline"
    ASYNC = "async"


@dataclass
class DispatchResult:
    mode: ExecutionMode
    # Populated for INLINE; None for ASYNC until future resolves.
    envelope: Optional[dict[str, Any]] = None
    # Populated for ASYNC; None for INLINE.
    future: Optional[Future[Any]] = None
    # Extra metadata the caller may want (eu_id, trace_id, …).
    meta: dict[str, Any] = field(default_factory=dict)


# ── Mode decision ─────────────────────────────────────────────────────────────

def _decide_mode(execution_unit: Any) -> ExecutionMode:
    """
    Derive the execution mode from an ExecutionUnit ORM object.

    Decision order
    --------------
    1. ``async_hint=True``  in eu.extra  → **ASYNC** unconditionally.
       Used by ``JOB_DISPATCH_STUB`` to bypass the env flag when the job
       system has already performed its own test-mode inline gate.
    2. ``async_heavy_execution_enabled()`` returns False → **INLINE**.
       This is the single env-flag gate; previously scattered across every
       route that imported ``async_heavy_execution_enabled`` from
       ``async_job_service``.
    3. ``async_hint=False`` in eu.extra  → **INLINE** explicitly.
    4. ``eu.priority == "high"``          → **ASYNC** (never block a thread).
    5. ``eu.type in _ASYNC_EU_TYPES``     → **ASYNC**.
    6. Everything else                    → **INLINE** (safe default).

    ``execution_unit`` is typed as ``Any`` to avoid a hard import of the ORM
    model, keeping this module import-safe even in test contexts where the DB
    layer is not initialised.
    """
    extra: dict[str, Any] = {}
    try:
        raw = execution_unit.extra
        if isinstance(raw, dict):
            extra = raw
    except AttributeError:
        pass

    async_hint = extra.get("async_hint")

    # Rule 1: async_hint=True bypasses the global env flag.
    # The job system sets this after its own test-mode gate has already fired.
    if async_hint is True:
        return ExecutionMode.ASYNC

    # Rule 2: global env flag — ONE place this is checked.
    if not async_heavy_execution_enabled():
        return ExecutionMode.INLINE

    # Rule 3: explicit inline request.
    if async_hint is False:
        return ExecutionMode.INLINE

    eu_type: str = ""
    try:
        eu_type = (execution_unit.type or "").lower()
    except AttributeError:
        pass

    # Rule 4: high-priority work should never block a request thread.
    priority: str = ""
    try:
        priority = (execution_unit.priority or "").lower()
    except AttributeError:
        pass
    if priority == "high":
        return ExecutionMode.ASYNC

    # Rule 5: known heavy eu_types.
    if eu_type in _ASYNC_EU_TYPES:
        return ExecutionMode.ASYNC

    # Rule 6: task and unknown types → inline (safe, fast).
    return ExecutionMode.INLINE


# ── Domain-job façade stubs ───────────────────────────────────────────────────

class _DomainJobStub:
    """
    Lightweight EU metadata carrier for domain-initiated job dispatches.

    Not persisted to the database — it is a typed context object that makes
    dispatch_job / dispatch_autonomous_job readable and consistent with the
    rest of the dispatcher API.  The actual DB-backed ExecutionUnit is created
    inside ``submit_async_job()`` via ``ExecutionUnitService.create()``.
    """

    type = "job"
    priority = "normal"
    id = None

    def __init__(self, *, task_name: str, source: str) -> None:
        self.extra: dict[str, Any] = {
            "task_name": task_name,
            "source": source,
        }


# ── Dispatcher ────────────────────────────────────────────────────────────────

def dispatch(
    execution_unit: Any,
    handler_fn: Callable[..., Any],
    context: Optional[dict[str, Any]] = None,
) -> DispatchResult:
    """
    Dispatch ``handler_fn`` according to the mode derived from
    ``execution_unit``.

    Parameters
    ----------
    execution_unit:
        An ORM ExecutionUnit (or any object with ``.type``, ``.priority``,
        and ``.extra`` attributes).  Read-only — never mutated here.
    handler_fn:
        Zero-argument callable that performs the actual work.  Build any
        closures you need before calling ``dispatch()``.
    context:
        Optional metadata dict stored in ``DispatchResult.meta`` (e.g.
        ``{"eu_id": ..., "trace_id": ...}``).  Not passed to handler_fn.

    Returns
    -------
    DispatchResult
        ``mode`` is always set.
        ``envelope`` is populated for INLINE after handler_fn() completes.
        ``future`` is populated for ASYNC; ``envelope`` is None.
    """
    meta: dict[str, Any] = context or {}
    mode = _decide_mode(execution_unit)

    if mode is ExecutionMode.INLINE:
        logger.debug(
            "[Dispatcher] INLINE execution eu_type=%s eu_id=%s",
            getattr(execution_unit, "type", "?"),
            getattr(execution_unit, "id", "?"),
        )
        try:
            envelope = handler_fn()
        except Exception:
            logger.exception(
                "[Dispatcher] INLINE handler raised eu_id=%s",
                getattr(execution_unit, "id", "?"),
            )
            raise
        return DispatchResult(mode=mode, envelope=envelope, meta=meta)

    # ASYNC — delegate to the shared thread pool.
    from platform_layer.async_job_service import _get_executor

    logger.debug(
        "[Dispatcher] ASYNC submission eu_type=%s eu_id=%s",
        getattr(execution_unit, "type", "?"),
        getattr(execution_unit, "id", "?"),
    )
    future: Future[Any] = _get_executor().submit(handler_fn)
    return DispatchResult(mode=mode, future=future, meta=meta)


# ── Domain-job public API ─────────────────────────────────────────────────────

def dispatch_job(
    *,
    task_name: str,
    payload: dict[str, Any],
    user_id: Any,
    source: str,
    max_attempts: int = 1,
    execute_inline_in_test_mode: bool = True,
) -> DispatchResult:
    """
    Public dispatcher entry point for fire-and-forget job work.

    Domain code must call this instead of ``submit_async_job()`` directly.
    ``async_job_service`` is treated as an internal execution backend:
    it handles AutomationLog persistence, DB-backed ExecutionUnit creation,
    test-mode inline fallback, and the final thread-pool submission via
    ``dispatch(JOB_DISPATCH_STUB, ...)``.

    Returns
    -------
    DispatchResult
        ``mode`` is always ASYNC (job-type work is never inline at the
        domain layer).  The AutomationLog id is in ``result.meta["log_id"]``.
    """
    from platform_layer.async_job_service import submit_async_job as _submit

    stub = _DomainJobStub(task_name=task_name, source=source)
    logger.debug(
        "[Dispatcher] dispatch_job task=%s source=%s",
        task_name,
        source,
    )
    log_id: str = _submit(
        task_name=task_name,
        payload=payload,
        user_id=user_id,
        source=source,
        max_attempts=max_attempts,
        execute_inline_in_test_mode=execute_inline_in_test_mode,
    )
    return DispatchResult(
        mode=ExecutionMode.ASYNC,
        meta={
            "log_id": log_id,
            "task_name": task_name,
            "source": source,
            "eu_type": stub.type,
        },
    )


def dispatch_autonomous_job(
    *,
    task_name: str,
    payload: dict[str, Any],
    user_id: Any,
    source: str,
    trigger_type: str,
    trigger_context: Optional[dict[str, Any]] = None,
    max_attempts: int = 1,
) -> DispatchResult:
    """
    Public dispatcher entry point for autonomy-gated job work.

    Evaluates the live autonomy trigger (ignore / defer / execute) and
    delegates to ``async_job_service`` for persistence and thread submission.
    Domain code must call this instead of ``submit_autonomous_async_job()``
    directly.

    Returns
    -------
    DispatchResult
        The full autonomous response dict (same shape as the old
        ``submit_autonomous_async_job`` return value) is in ``result.envelope``.
        ``result.meta["status"]`` is one of ``"QUEUED"``, ``"DEFERRED"``,
        ``"IGNORED"``.
        ``mode`` is ``INLINE`` for IGNORED decisions (no thread submitted),
        ``ASYNC`` for QUEUED / DEFERRED.
    """
    from platform_layer.async_job_service import submit_autonomous_async_job as _submit_auto

    stub = _DomainJobStub(task_name=task_name, source=source)
    logger.debug(
        "[Dispatcher] dispatch_autonomous_job task=%s source=%s trigger=%s",
        task_name,
        source,
        trigger_type,
    )
    response: dict[str, Any] = _submit_auto(
        task_name=task_name,
        payload=payload,
        user_id=user_id,
        source=source,
        trigger_type=trigger_type,
        trigger_context=trigger_context,
        max_attempts=max_attempts,
    )
    status = str(response.get("status") or "QUEUED").upper()
    # IGNORED means autonomy evaluation chose not to execute — no thread submitted.
    mode = ExecutionMode.INLINE if status == "IGNORED" else ExecutionMode.ASYNC
    return DispatchResult(
        mode=mode,
        envelope=response,
        meta={
            "task_name": task_name,
            "source": source,
            "eu_type": stub.type,
            "status": status,
        },
    )
