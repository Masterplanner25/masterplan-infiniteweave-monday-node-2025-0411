"""
NodusRuntimeAdapter — Execution contract between Nodus VM and A.I.N.D.Y. runtime.

Defines the structured execution contract so any AINDY service can hand a Nodus
script to the VM and get back a typed result without knowing VM internals:

  NodusExecutionContext   what A.I.N.D.Y. injects into the VM before execution
  NodusExecutionResult    what the VM returns to A.I.N.D.Y. after execution
  NodusRuntimeAdapter     bridges the two; wires callbacks; runs scripts / files

Also registers the "nodus.execute" flow node so any flow graph can execute Nodus
scripts as first-class nodes — input from state, output patched back into state.

Contract guarantees
===================
1. Context is fully injected BEFORE the first VM instruction executes.
2. Every Nodus emit() call is captured in NodusExecutionResult.emitted_events
   and also forwarded to the caller-supplied event_sink (or the default
   queue_system_event path when no sink is provided).
3. Every Nodus remember() call is captured in NodusExecutionResult.memory_writes.
4. NodusExecutionResult.output_state reflects all set_state() mutations made
   inside the script.
5. Exceptions never propagate — errors are returned as status="failure".
6. Retry policy is honoured: set state["nodus_error_policy"] = "retry" to let
   the flow engine retry on script failure; default is "fail" (immediate FAILURE).

Relationship to existing nodus services
========================================
  nodus_execution_service.py   low-level task runner (route handler helper)
  nodus_adapter.py             deterministic agent flow via PersistentFlowRunner
  nodus_runtime_adapter.py     THIS FILE — generic VM ↔ runtime contract layer
"""
from __future__ import annotations

import ctypes
import logging
import os
import sys
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Literal, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class NodusTimeoutError(Exception):
    """Raised asynchronously in the Nodus VM worker thread when max_execution_ms is exceeded."""


def _register_function_if_possible(runtime: Any, name: str, fn: Callable, *, arity: Any) -> None:
    """
    Register a host function unless the VM already provides the same built-in.

    The live Nodus runtime rejects overriding some built-ins (for example
    ``recall``), while the mocked runtime used in tests accepts all calls.
    """
    try:
        runtime.register_function(name, fn, arity=arity)
    except Exception as exc:
        if "Cannot override built-in function" not in str(exc):
            raise
        logger.info("[NodusRuntimeAdapter] Using existing VM built-in for %s", name)


# ── Execution Contract Dataclasses ────────────────────────────────────────────

@dataclass
class NodusExecutionContext:
    """
    Everything the A.I.N.D.Y. runtime injects into the Nodus VM before execution.

    Fields
    ------
    user_id             Owner of this execution — used for memory scoping and
                        event attribution.
    execution_unit_id   Correlates back to the ExecutionUnit row in the DB and
                        appears in every emitted event payload.
    memory_context      Pre-loaded memory nodes keyed by memory_id, e.g.
                        {"<uuid>": {"id": ..., "content": ..., "tags": [...]}}.
                        Exposed inside the script as the global ``memory_context``.
    input_payload       Arbitrary caller-provided input data.  Exposed as the
                        global ``input_payload``.
    state               Mutable execution state.  Scripts may call set_state(k, v)
                        to write values that surface in NodusExecutionResult.output_state
                        after the run.  A read-only snapshot is also exposed as
                        the global ``state`` for convenience.
    event_sink          Optional callable(event_type: str, payload: dict) that
                        receives every Nodus emit() call.  When None the adapter
                        falls back to queue_system_event() so events land on the
                        A.I.N.D.Y. SystemEvent bus automatically.
    """
    user_id: str
    execution_unit_id: str
    memory_context: dict[str, Any] = field(default_factory=dict)
    input_payload: dict[str, Any] = field(default_factory=dict)
    state: dict[str, Any] = field(default_factory=dict)
    event_sink: Optional[Callable[[str, dict], None]] = None
    max_execution_ms: Optional[int] = None


@dataclass
class NodusExecutionResult:
    """
    Structured result returned by NodusRuntimeAdapter after VM execution.

    Fields
    ------
    output_state      Context.state after execution, including any values written
                      by set_state() calls inside the script.
    emitted_events    Ordered list of events fired by emit() during execution.
                      Each entry: {event_type, payload, execution_unit_id, user_id}.
    memory_writes     Ordered list of memory nodes written by remember() calls.
                      Each entry: {execution_unit_id, user_id, args, result}.
    status            "success" | "failure"
    error             Human-readable error message when status == "failure".
    raw_result        Raw dict returned by NodusRuntime.run_source() — useful
                      for debugging (stdout, stderr, stack traces).
    """
    output_state: dict[str, Any]
    emitted_events: list[dict[str, Any]]
    memory_writes: list[dict[str, Any]]
    status: Literal["success", "failure", "waiting"]
    error: Optional[str] = None
    raw_result: Optional[dict[str, Any]] = None


# ── Adapter ───────────────────────────────────────────────────────────────────

class NodusRuntimeAdapter:
    """
    Bridges the Nodus VM to A.I.N.D.Y. services.

    The adapter is stateless per execution — instantiate once with a DB session
    and call run_script() / run_file() as many times as needed within that
    session's lifetime.

    Callback wiring (injected before execution)
    -------------------------------------------
    Memory read  : recall, recall_tool, recall_from, recall_all, suggest
    Memory write : remember (captured → memory_writes), record_outcome, share
    Event emit   : emit (captured → emitted_events + routed to event_sink)
    State        : set_state(k, v) / get_state(k, default)

    Global variables available to scripts
    --------------------------------------
    memory_context      dict  — pre-loaded memory nodes
    input_payload       dict  — caller-provided inputs
    state               dict  — read-only snapshot of context.state at start
    execution_unit_id   str
    user_id             str

    Usage
    -----
        adapter = NodusRuntimeAdapter(db=db)
        ctx = NodusExecutionContext(
            user_id=user_id,
            execution_unit_id=eu_id,
            memory_context=recalled_nodes,
            input_payload={"goal": "..."},
        )
        result = adapter.run_script(script_source, ctx)
        if result.status == "success":
            process(result.output_state, result.emitted_events)
    """

    def __init__(self, db: Session) -> None:
        self._db = db

    # ── Public API ────────────────────────────────────────────────────────────

    def run_script(
        self,
        script: str,
        context: NodusExecutionContext,
        max_execution_ms: int = 30_000,
    ) -> NodusExecutionResult:
        """Execute a Nodus script string with the given execution context."""
        filename = f"<nodus:eu:{context.execution_unit_id}>"
        effective_ms = context.max_execution_ms if context.max_execution_ms is not None else max_execution_ms
        return self._execute(script, filename, context, max_execution_ms=effective_ms)

    def run_file(
        self,
        path: str,
        context: NodusExecutionContext,
        max_execution_ms: int = 30_000,
    ) -> NodusExecutionResult:
        """
        Load and execute a .nodus script file with the given execution context.

        The file is read on the Python side (before the VM starts) so the
        Nodus sandbox's filesystem restriction never applies to the loader itself.
        """
        try:
            with open(path, "r", encoding="utf-8") as fh:
                script = fh.read()
        except OSError as exc:
            logger.error("[NodusRuntimeAdapter] Cannot read %s: %s", path, exc)
            return NodusExecutionResult(
                output_state=dict(context.state),
                emitted_events=[],
                memory_writes=[],
                status="failure",
                error=f"Cannot read script file '{path}': {exc}",
            )
        effective_ms = context.max_execution_ms if context.max_execution_ms is not None else max_execution_ms
        return self._execute(script, path, context, max_execution_ms=effective_ms)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _execute(
        self,
        script: str,
        filename: str,
        context: NodusExecutionContext,
        max_execution_ms: int = 30_000,
    ) -> NodusExecutionResult:
        """
        Core execution path shared by run_script() and run_file().

        Steps
        -----
        1. Boot the Nodus VM (import guard — returns failure if not installed).
        2. Create a NodusMemoryBridge scoped to this execution unit.
        3. Register all A.I.N.D.Y. service callbacks as Nodus builtins.
        4. Build initial_globals from context fields (injected BEFORE execution).
        5. Run the script; collect events and memory writes as side-effects.
        6. Return a NodusExecutionResult regardless of success or failure.
        """
        collected_events: list[dict[str, Any]] = []
        collected_memory_writes: list[dict[str, Any]] = []
        collected_traces: list[dict[str, Any]] = []

        try:
            # ── Boot Nodus VM ─────────────────────────────────────────────────
            nodus_path = os.environ.get(
                "NODUS_SOURCE_PATH",
                r"C:\dev\Coding Language\src",
            )
            if nodus_path not in sys.path:
                sys.path.insert(0, nodus_path)

            from nodus.runtime.embedding import NodusRuntime  # type: ignore[import]
            from memory.nodus_memory_bridge import create_nodus_bridge
            from runtime.nodus_builtins import NodusMemoryBuiltins, NodusEventBuiltins, NodusWaitSignal

            bridge = create_nodus_bridge(
                db=self._db,
                user_id=context.user_id,
                session_tags=["nodus_runtime_adapter", context.execution_unit_id],
            )

            # Namespaced memory builtin — scripts call memory.recall / write / search
            memory_builtins = NodusMemoryBuiltins(db=self._db, user_id=context.user_id)

            # Namespaced event builtin — scripts call event.emit / event.wait
            event_builtins = NodusEventBuiltins(
                db=self._db,
                user_id=context.user_id,
                execution_unit_id=context.execution_unit_id,
                trace_id=context.execution_unit_id,
                event_sink=context.event_sink,
                context_state=context.state,
            )

            runtime = NodusRuntime()

            # ── Per-execution trace counter ───────────────────────────────────
            _seq = [0]  # mutable list so closures can increment without nonlocal

            def _make_traced(fn_name: str, fn: Callable) -> Callable:
                """Wrap a host function to record a NodusTraceEvent per call."""
                def _traced(*args: Any, **kwargs: Any) -> Any:
                    _seq[0] += 1
                    seq = _seq[0]
                    t_start = datetime.now(timezone.utc)
                    _status = "ok"
                    _err: Optional[str] = None
                    _result: Any = None
                    try:
                        _result = fn(*args, **kwargs)
                        return _result
                    except Exception as _exc:
                        _status = "error"
                        _err = str(_exc)
                        raise
                    finally:
                        t_end = datetime.now(timezone.utc)
                        collected_traces.append({
                            "execution_unit_id": context.execution_unit_id,
                            "trace_id": context.execution_unit_id,
                            "sequence": seq,
                            "fn_name": fn_name,
                            "args_summary": _sanitize_args(args),
                            "result_summary": _sanitize_result(_result),
                            "duration_ms": int((t_end - t_start).total_seconds() * 1000),
                            "status": _status,
                            "error": _err,
                            "user_id": context.user_id,
                            "timestamp": t_start,
                        })
                return _traced

            # ── Register A.I.N.D.Y. callbacks as Nodus builtins ───────────────

            # Memory read operations (read_memory capability)
            _register_function_if_possible(runtime, "recall", _make_traced("recall", bridge.recall), arity=(0, 1, 2, 3, 4))
            _register_function_if_possible(runtime, "recall_tool", _make_traced("recall_tool", bridge.recall_tool), arity=(0, 1, 2, 3))
            _register_function_if_possible(runtime, "recall_from", _make_traced("recall_from", bridge.recall_from), arity=(1, 2, 3, 4))
            _register_function_if_possible(runtime, "recall_all", _make_traced("recall_all", bridge.recall_all_agents), arity=(0, 1, 2, 3))
            _register_function_if_possible(runtime, "suggest", _make_traced("suggest", bridge.get_suggestions), arity=(0, 1, 2, 3))

            # Memory write operations — wrap to capture writes before forwarding
            def _remember_with_capture(*args: Any, **kwargs: Any) -> Any:
                result = bridge.remember(*args, **kwargs)
                collected_memory_writes.append({
                    "execution_unit_id": context.execution_unit_id,
                    "user_id": context.user_id,
                    "args": list(args),
                    "result": result,
                })
                return result

            _register_function_if_possible(runtime, "remember", _make_traced("remember", _remember_with_capture), arity=(1, 2, 3, 4, 5))
            _register_function_if_possible(runtime, "record_outcome", _make_traced("record_outcome", bridge.record_outcome), arity=2)
            _register_function_if_possible(runtime, "share", _make_traced("share", bridge.share), arity=1)

            # Event emission — capture + route to event_sink / default queue
            def _emit_with_capture(
                event_type: str,
                payload: Optional[dict[str, Any]] = None,
            ) -> None:
                routed_payload = payload or {}
                event_record = {
                    "event_type": event_type,
                    "payload": routed_payload,
                    "execution_unit_id": context.execution_unit_id,
                    "user_id": context.user_id,
                }
                collected_events.append(event_record)

                if context.event_sink is not None:
                    # Caller-supplied sink (e.g. test spy or custom router)
                    try:
                        context.event_sink(event_type, routed_payload)
                    except Exception as exc:
                        logger.warning(
                            "[NodusRuntimeAdapter] event_sink raised for '%s': %s",
                            event_type, exc,
                        )
                else:
                    # Default: queue as A.I.N.D.Y. SystemEvent
                    try:
                        from core.execution_signal_helper import queue_system_event
                        queue_system_event(
                            db=self._db,
                            event_type=event_type,
                            user_id=context.user_id,
                            trace_id=context.execution_unit_id,
                            source="nodus",
                            payload={
                                **routed_payload,
                                "execution_unit_id": context.execution_unit_id,
                            },
                            required=False,
                        )
                    except Exception as exc:
                        logger.warning(
                            "[NodusRuntimeAdapter] Default event queue failed for '%s': %s",
                            event_type, exc,
                        )

            _register_function_if_possible(runtime, "emit", _make_traced("emit", _emit_with_capture), arity=(1, 2))

            # State mutation — scripts call set_state(k, v) to write back
            def _set_state(key: str, value: Any) -> None:
                context.state[key] = value

            def _get_state(key: str, default: Any = None) -> Any:
                return context.state.get(key, default)

            _register_function_if_possible(runtime, "set_state", _make_traced("set_state", _set_state), arity=(1, 2))
            _register_function_if_possible(runtime, "get_state", _make_traced("get_state", _get_state), arity=(1, 2))

            # ── Syscall binding ───────────────────────────────────────────────
            # Build a SyscallContext from this execution context so Nodus scripts
            # can call sys("sys.v1.memory.read", {...}) without knowing HTTP.
            # Capabilities default to DEFAULT_NODUS_CAPABILITIES; callers may
            # extend by passing {"syscall_capabilities": [...]} in input_payload.
            from kernel.syscall_dispatcher import (
                DEFAULT_NODUS_CAPABILITIES,
                SyscallContext,
                get_dispatcher,
            )
            _extra_caps: list[str] = (
                context.input_payload.get("syscall_capabilities") or []
                if isinstance(context.input_payload, dict) else []
            )
            _syscall_ctx = SyscallContext(
                execution_unit_id=context.execution_unit_id,
                user_id=context.user_id,
                capabilities=list(DEFAULT_NODUS_CAPABILITIES) + _extra_caps,
                trace_id=context.execution_unit_id,
                memory_context=(
                    list(context.memory_context.values())
                    if isinstance(context.memory_context, dict)
                    else list(context.memory_context)
                ),
                metadata=dict(context.input_payload)
                if isinstance(context.input_payload, dict) else {},
            )
            _syscall_dispatcher = get_dispatcher()

            def _nodus_syscall(name: str, payload: Optional[dict[str, Any]] = None) -> dict[str, Any]:
                """Nodus-visible sys() builtin — routes to SyscallDispatcher."""
                return _syscall_dispatcher.dispatch(name, payload or {}, _syscall_ctx)

            # ── Inject context globals BEFORE execution ───────────────────────
            initial_globals: dict[str, Any] = {
                "memory_context": context.memory_context,
                "input_payload": context.input_payload,
                "state": dict(context.state),   # read-only snapshot; mutations via set_state()
                "execution_unit_id": context.execution_unit_id,
                "user_id": context.user_id,
                # Namespaced memory API: memory.recall / memory.write / memory.search
                "memory": memory_builtins,
                # Namespaced event API: event.emit / event.wait
                "event": event_builtins,
                # Syscall API: sys("sys.v1.memory.read", {...})
                "sys": _nodus_syscall,
            }

            logger.info(
                "[NodusRuntimeAdapter] Executing '%s' eu=%s user=%s",
                filename, context.execution_unit_id, context.user_id,
            )

            # ── Run (with timeout) ────────────────────────────────────────────
            # run_source() is executed in a daemon thread so a threading.Timer
            # can inject NodusTimeoutError asynchronously via
            # ctypes.PyThreadState_SetAsyncExc if the deadline is reached.
            # This works from any thread (no signal.alarm / main-thread restriction).
            _timeout_flag = threading.Event()
            _result_holder: list = [None]
            _exc_holder: list = [None]

            def _vm_run() -> None:
                try:
                    _result_holder[0] = runtime.run_source(
                        script,
                        filename=filename,
                        initial_globals=initial_globals,
                        host_globals=initial_globals,
                    )
                except Exception as _vm_exc:  # includes NodusTimeoutError
                    _exc_holder[0] = _vm_exc

            _vm_thread = threading.Thread(target=_vm_run, daemon=True)

            def _on_timeout() -> None:
                _timeout_flag.set()
                tid = _vm_thread.ident
                if tid is not None:
                    ctypes.pythonapi.PyThreadState_SetAsyncExc(
                        ctypes.c_ulong(tid),
                        ctypes.py_object(NodusTimeoutError),
                    )

            _deadline = threading.Timer(max_execution_ms / 1000.0, _on_timeout)
            _deadline.start()
            try:
                _vm_thread.start()
                _vm_thread.join()
            finally:
                _deadline.cancel()

            if _timeout_flag.is_set():
                logger.warning(
                    "[NodusRuntimeAdapter] '%s' timed out after %dms eu=%s",
                    filename, max_execution_ms, context.execution_unit_id,
                )
                return NodusExecutionResult(
                    output_state=dict(context.state),
                    emitted_events=[],
                    memory_writes=[],
                    status="failure",
                    error=f"execution_timeout: exceeded {max_execution_ms}ms",
                )

            if _exc_holder[0] is not None:
                raise _exc_holder[0]

            raw_result = _result_holder[0]

            # Merge event.emit() and memory.write() captures into shared lists
            collected_events.extend(event_builtins._emitted)
            collected_memory_writes.extend(memory_builtins._writes)

            # ── WAIT path (state-flag: VM swallowed NodusWaitSignal) ──────────
            if context.state.get("nodus_wait_requested"):
                wait_type = context.state.pop("nodus_wait_event_type", "unknown")
                context.state.pop("nodus_wait_requested", None)
                logger.info(
                    "[NodusRuntimeAdapter] '%s' → waiting_for='%s' eu=%s",
                    filename, wait_type, context.execution_unit_id,
                )
                return NodusExecutionResult(
                    output_state=dict(context.state),
                    emitted_events=collected_events,
                    memory_writes=collected_memory_writes,
                    status="waiting",
                    raw_result={"ok": True, "wait_for": wait_type},
                )

            success = bool(raw_result.get("ok", False))
            status: Literal["success", "failure", "waiting"] = "success" if success else "failure"
            error = raw_result.get("error") if not success else None

            logger.info(
                "[NodusRuntimeAdapter] '%s' → %s  events=%d  writes=%d",
                filename, status, len(collected_events), len(collected_memory_writes),
            )

            return NodusExecutionResult(
                output_state=dict(context.state),
                emitted_events=collected_events,
                memory_writes=collected_memory_writes,
                status=status,
                error=error,
                raw_result=raw_result,
            )

        except ImportError as exc:
            logger.warning("[NodusRuntimeAdapter] Nodus runtime not available: %s", exc)
            return NodusExecutionResult(
                output_state=dict(context.state),
                emitted_events=collected_events,
                memory_writes=collected_memory_writes,
                status="failure",
                error=f"Nodus runtime not available: {exc}",
            )
        except Exception as exc:
            # Check if the VM re-raised NodusWaitSignal (some VM implementations propagate
            # host function exceptions rather than wrapping them as script errors)
            try:
                from runtime.nodus_builtins import NodusWaitSignal as _WaitSig
                if isinstance(exc, _WaitSig):
                    logger.info(
                        "[NodusRuntimeAdapter] '%s' → waiting_for='%s' eu=%s (re-raised)",
                        filename, exc.event_type, context.execution_unit_id,
                    )
                    return NodusExecutionResult(
                        output_state=dict(context.state),
                        emitted_events=collected_events,
                        memory_writes=collected_memory_writes,
                        status="waiting",
                        raw_result={"ok": True, "wait_for": exc.event_type},
                    )
            except ImportError:
                pass
            logger.error(
                "[NodusRuntimeAdapter] Unhandled error in '%s': %s", filename, exc,
            )
            return NodusExecutionResult(
                output_state=dict(context.state),
                emitted_events=collected_events,
                memory_writes=collected_memory_writes,
                status="failure",
                error=str(exc),
            )
        finally:
            _flush_nodus_traces(collected_traces)


# ── Nodus trace helpers ───────────────────────────────────────────────────────

def _sanitize_args(args: tuple) -> list:
    """
    Convert host-function call args to a JSON-safe summary.

    Rules
    -----
    * None / bool / int / float — passed through unchanged.
    * str — truncated to 200 chars.
    * dict — first 10 keys kept; values truncated to 100 chars.
    * list / tuple — replaced with ``"[N items]"`` (avoids storing large lists).
    * anything else — replaced with its type name.
    """
    sanitized = []
    for a in args:
        if a is None or isinstance(a, (bool, int, float)):
            sanitized.append(a)
        elif isinstance(a, str):
            sanitized.append(a[:200] + "\u2026" if len(a) > 200 else a)
        elif isinstance(a, dict):
            sanitized.append({
                str(k)[:50]: str(v)[:100]
                for k, v in list(a.items())[:10]
            })
        elif isinstance(a, (list, tuple)):
            sanitized.append(f"[{len(a)} items]")
        else:
            sanitized.append(type(a).__name__)
    return sanitized


def _sanitize_result(result: Any) -> dict:
    """
    Convert a host-function return value to a JSON-safe summary dict.

    Rules
    -----
    * None / bool / int / float — ``{"value": <val>}``.
    * str — ``{"value": <truncated at 200 chars>}``.
    * dict — ``{"keys": [first 10 keys], "size": N}``.
    * list / tuple — ``{"length": N}``.
    * anything else — ``{"type": "<type name>"}``.
    """
    if result is None or isinstance(result, bool):
        return {"value": result}
    if isinstance(result, (int, float)):
        return {"value": result}
    if isinstance(result, str):
        v = result[:200] + "\u2026" if len(result) > 200 else result
        return {"value": v}
    if isinstance(result, dict):
        return {"keys": list(result.keys())[:10], "size": len(result)}
    if isinstance(result, (list, tuple)):
        return {"length": len(result)}
    return {"type": type(result).__name__}


def _flush_nodus_traces(traces: list) -> None:
    """
    Persist collected NodusTraceEvent rows to the DB.

    Opens its own short-lived SessionLocal so the caller's session is never
    contaminated.  All errors are swallowed — tracing is non-fatal.
    """
    if not traces:
        return
    try:
        import uuid as _uuid
        from db.database import SessionLocal
        from db.models.nodus_trace_event import NodusTraceEvent

        db = SessionLocal()
        try:
            for t in traces:
                user_raw = t.get("user_id")
                try:
                    user_uuid = _uuid.UUID(str(user_raw)) if user_raw else None
                except (ValueError, AttributeError):
                    user_uuid = None
                db.add(NodusTraceEvent(
                    id=_uuid.uuid4(),
                    execution_unit_id=t["execution_unit_id"],
                    trace_id=t["trace_id"],
                    sequence=t["sequence"],
                    fn_name=t["fn_name"],
                    args_summary=t.get("args_summary"),
                    result_summary=t.get("result_summary"),
                    duration_ms=t.get("duration_ms"),
                    status=t.get("status", "ok"),
                    error=t.get("error"),
                    user_id=user_uuid,
                    timestamp=t.get("timestamp"),
                ))
            db.commit()
        finally:
            db.close()
    except Exception as exc:
        logger.warning(
            "[NodusTrace] Failed to flush %d trace event(s): %s",
            len(traces),
            exc,
        )


# ── Helpers exported for nodus_adapter.py ────────────────────────────────────
#
# Node registration lives in nodus_adapter.py (which already imports flow_engine
# at module level).  These helpers are kept here so the contract module stays
# self-contained and importable without the full DB/settings chain.

def _build_event_sink(
    *,
    db: Any,
    user_id: str,
    trace_id: str,
    execution_unit_id: str,
) -> Callable[[str, dict], None]:
    """
    Return an event_sink that queues every Nodus emit() call as a SystemEvent
    under the current flow's trace context.
    """
    def _sink(event_type: str, payload: dict) -> None:
        try:
            from core.execution_signal_helper import queue_system_event
            queue_system_event(
                db=db,
                event_type=event_type,
                user_id=user_id,
                trace_id=trace_id,
                source="nodus",
                payload={**payload, "execution_unit_id": execution_unit_id},
                required=False,
            )
        except Exception as exc:
            logger.warning("[nodus.execute] event_sink queue failed for '%s': %s", event_type, exc)

    return _sink


def _flush_memory_writes(
    *,
    db: Any,
    user_id: str,
    run_id: str,
    memory_writes: list[dict[str, Any]],
    flow_name: str,
) -> None:
    """
    Queue a memory capture for each write collected during Nodus execution.
    Non-fatal — a single failed write does not abort the node.
    """
    from core.execution_signal_helper import queue_memory_capture

    for write in memory_writes:
        args = write.get("args", [])
        content = str(args[0]) if args else ""
        if not content:
            continue
        try:
            queue_memory_capture(
                db=db,
                user_id=user_id,
                agent_namespace="nodus",
                event_type="nodus.memory.write",
                content=content,
                source="nodus_execute_node",
                tags=["nodus", "script_execution", flow_name],
                node_type="outcome",
                context={"run_id": run_id, "execution_unit_id": write.get("execution_unit_id")},
                force=False,
            )
        except Exception as exc:
            logger.warning("[nodus.execute] memory write flush failed: %s", exc)



# ── NODUS_SCRIPT_FLOW example ─────────────────────────────────────────────────
#
# Importable flow definition for the nodus_execute workflow type.
# Nodes are registered in nodus_adapter.py (which already carries the full
# flow_engine import chain).  This dict is safe to import independently.
#
# Usage
# -----
#   from runtime.flow_engine import PersistentFlowRunner
#   from runtime.nodus_runtime_adapter import NODUS_SCRIPT_FLOW
#   import runtime.nodus_adapter  # ensure nodes are registered
#
#   runner = PersistentFlowRunner(
#       flow=NODUS_SCRIPT_FLOW,
#       db=db,
#       user_id=user_id,
#       workflow_type="nodus_execute",
#   )
#   result = runner.start(
#       {
#           "nodus_script": """
#               let goal = input_payload["goal"]
#               remember(goal, "nodus_goal")
#               emit("goal.processed", {goal: goal})
#               set_state("processed", true)
#           """,
#           "nodus_input_payload": {"goal": "Improve Q2 conversion"},
#           "nodus_error_policy": "retry",   # optional; defaults to "fail"
#       },
#       flow_name="nodus_script_flow",
#   )
#
# Flow graph
# ----------
#   [nodus.execute] ──success──► [nodus_record_outcome]  ──► END
#                   ──failure──► [nodus_handle_error]    ──► END
#
# State keys produced by nodus.execute
# -------------------------------------
#   nodus_status          "success" | "failure"
#   nodus_output_state    mutations written inside the script via set_state()
#   nodus_events          list of events emitted via emit()
#   nodus_memory_writes   list of memory nodes written via remember()
#   nodus_execute_result  summary dict {status, output_state, events_emitted,
#                                       memory_writes, error}


def _nodus_succeeded(state: dict) -> bool:
    return state.get("nodus_status") == "success"


def _nodus_failed(state: dict) -> bool:
    return state.get("nodus_status") != "success"


NODUS_SCRIPT_FLOW: dict = {
    "start": "nodus.execute",
    "edges": {
        "nodus.execute": [
            {"condition": _nodus_succeeded, "target": "nodus_record_outcome"},
            {"condition": _nodus_failed,    "target": "nodus_handle_error"},
        ],
        "nodus_record_outcome": [],
        "nodus_handle_error": [],
    },
    "end": ["nodus_record_outcome", "nodus_handle_error"],
}
