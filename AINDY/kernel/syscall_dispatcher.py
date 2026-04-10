"""
SyscallDispatcher — single entry point for all A.I.N.D.Y. system calls.

All sys.v{N}.{domain}.{action} calls route through dispatch(). The dispatcher:

  1. Parses version and action from the syscall name.
  2. Validates the syscall name exists in the registry.
  3. Enforces the required capability against the caller's SyscallContext.
  4. Validates input payload against the entry's input_schema (if present).
  5. Checks tenant isolation and resource quota.
  6. Executes the registered handler.
  7. Validates output against output_schema (non-fatal — logs warning only).
  8. Emits deprecation warning if the syscall is marked deprecated.
  9. Wraps the result in the standard response envelope.
 10. Emits a SYSCALL_EXECUTED SystemEvent (non-fatal, swallowed on failure).

Standard response envelope
--------------------------
All calls return::

    {
        "status":            "success" | "error",
        "data":              dict,      # handler output on success, {} on error
        "trace_id":          str,
        "execution_unit_id": str,
        "syscall":           str,       # fully-qualified syscall name
        "version":           str,       # parsed ABI version (e.g. "v1")
        "duration_ms":       int,
        "error":             str | None,
        "warning":           str | None # set when syscall is deprecated
    }

The dispatcher NEVER raises. Every code path returns the envelope.

Usage
-----
    from kernel.syscall_dispatcher import get_dispatcher, SyscallContext

    ctx = SyscallContext(
        execution_unit_id="run-123",
        user_id="user-456",
        capabilities=["memory.read", "event.emit"],
        trace_id="run-123",
    )
    result = get_dispatcher().dispatch("sys.v1.memory.read", {"query": "auth"}, ctx)
    assert result["status"] == "success"
    nodes = result["data"]["nodes"]
    version = result["version"]   # "v1"
"""
from __future__ import annotations

import logging
import time
import uuid as _uuid
from contextvars import ContextVar
from typing import Any

# Re-export SyscallContext so callers only need one import.
from kernel.syscall_registry import (  # noqa: F401
    DEFAULT_NODUS_CAPABILITIES,
    SYSCALL_REGISTRY,
    SyscallContext,
    SyscallEntry,
    register_syscall,
)
from kernel.syscall_versioning import (
    parse_syscall_name,
    validate_input,
    validate_output,
    resolve_version,
    SYSCALL_VERSION_FALLBACK,
)

__all__ = [
    "SyscallDispatcher",
    "SyscallContext",
    "DEFAULT_NODUS_CAPABILITIES",
    "register_syscall",
    "get_dispatcher",
    "make_syscall_ctx_from_flow",
    "make_syscall_ctx_from_tool",
    "child_context",
]

# ── Trace propagation ContextVars ─────────────────────────────────────────────
# These carry the root trace_id and execution_unit_id across nested dispatch()
# calls within the same thread or asyncio task.  The root dispatch() sets them
# and always resets them in a finally block — nested calls inherit them without
# writing a new token.
_TRACE_ID_CTX: ContextVar[str] = ContextVar("syscall_trace_id", default="")
_EU_ID_CTX: ContextVar[str] = ContextVar("syscall_eu_id", default="")

# Lazy import of ResourceManager to avoid circular imports at module load.
# The resource manager is only consulted inside dispatch(), so it's safe.
def _get_rm():
    from kernel.resource_manager import get_resource_manager
    return get_resource_manager()

logger = logging.getLogger(__name__)


class SyscallDispatcher:
    """Routes sys.v1.* calls to registered handlers with capability enforcement.

    Instantiate once and reuse (the module-level singleton is the normal path).
    The dispatcher itself is stateless — all state lives in the handlers and DB.
    """

    def dispatch(
        self,
        name: str,
        payload: dict[str, Any],
        context: SyscallContext,
    ) -> dict[str, Any]:
        """Execute a syscall and return the standard response envelope.

        This method never raises. All errors — unknown syscall, permission
        denial, handler failure — are captured in the returned envelope.

        Trace propagation
        -----------------
        If a parent dispatch() is already active in this thread / asyncio task,
        the child inherits its trace_id and execution_unit_id automatically via
        ContextVars — even if the caller passed a freshly-constructed context.
        This ensures a single trace_id across the full nested execution chain.

        If this is the root call (no parent active), the context's existing
        trace_id / execution_unit_id are used; empty strings cause a new UUID
        to be generated so observability is never missing an ID.

        Args:
            name:    Fully-qualified syscall name (sys.v1.{domain}.{action}).
            payload: Arbitrary handler-specific arguments.
            context: Caller's execution context (user_id, capabilities, trace_id).

        Returns:
            Standard response envelope (see module docstring).
        """
        t_start = time.monotonic()
        context, _tok_trace, _tok_eu = self._resolve_trace_context(context)
        try:
            return self._dispatch(name, payload, context, t_start)
        except Exception as exc:  # belt-and-suspenders — _dispatch shouldn't leak
            logger.error(
                "[SyscallDispatcher] unhandled exception for '%s': %s",
                name, exc, exc_info=True,
            )
            return self._error_envelope(name, context, str(exc), t_start)
        finally:
            if _tok_trace is not None:
                _TRACE_ID_CTX.reset(_tok_trace)
            if _tok_eu is not None:
                _EU_ID_CTX.reset(_tok_eu)

    # ── Private ───────────────────────────────────────────────────────────────

    def _resolve_trace_context(
        self,
        context: SyscallContext,
    ) -> tuple[SyscallContext, object, object]:
        """Return a (context, trace_token, eu_token) triple.

        If a parent dispatch() is active (ContextVars are set):
          - return a new SyscallContext inheriting the parent's trace_id and
            execution_unit_id; tokens are None (nothing to reset).

        If this is the root call (ContextVars are empty):
          - fill in any missing trace_id / execution_unit_id with new UUIDs,
          - set both ContextVars so nested dispatches inherit them,
          - return the tokens so dispatch() can reset them in its finally block.
        """
        inherited_trace = _TRACE_ID_CTX.get()
        inherited_eu = _EU_ID_CTX.get()

        if inherited_trace:
            # ── Nested call — inherit parent trace/EU ─────────────────────────
            if (
                context.trace_id != inherited_trace
                or context.execution_unit_id != inherited_eu
            ):
                logger.debug(
                    "[SyscallDispatcher] trace inherit: caller trace=%r eu=%r "
                    "→ parent trace=%r eu=%r",
                    context.trace_id, context.execution_unit_id,
                    inherited_trace, inherited_eu,
                )
                context = SyscallContext(
                    execution_unit_id=inherited_eu or context.execution_unit_id,
                    user_id=context.user_id,
                    capabilities=context.capabilities,
                    trace_id=inherited_trace,
                    memory_context=context.memory_context,
                    metadata=context.metadata,
                )
            return context, None, None

        # ── Root call — establish trace context ───────────────────────────────
        trace_id = context.trace_id or str(_uuid.uuid4())
        eu_id = context.execution_unit_id or str(_uuid.uuid4())
        if not context.trace_id or not context.execution_unit_id:
            context = SyscallContext(
                execution_unit_id=eu_id,
                user_id=context.user_id,
                capabilities=context.capabilities,
                trace_id=trace_id,
                memory_context=context.memory_context,
                metadata=context.metadata,
            )
        tok_trace = _TRACE_ID_CTX.set(context.trace_id)
        tok_eu = _EU_ID_CTX.set(context.execution_unit_id)
        return context, tok_trace, tok_eu

    def _dispatch(
        self,
        name: str,
        payload: dict[str, Any],
        context: SyscallContext,
        t_start: float,
    ) -> dict[str, Any]:
        # Step 1 — parse version and validate syscall exists
        try:
            parsed_version, _ = parse_syscall_name(name)
        except ValueError:
            parsed_version = "unknown"

        # Version fallback: if requested version has no entries, try latest stable
        if parsed_version != "unknown":
            available = frozenset(SYSCALL_REGISTRY.versions())
            resolved = resolve_version(parsed_version, available, SYSCALL_VERSION_FALLBACK)
            if resolved is None and parsed_version not in available:
                return self._error_envelope(
                    name, context,
                    f"Unknown syscall version: {parsed_version!r}; "
                    f"available versions: {sorted(available)}",
                    t_start,
                    version=parsed_version,
                )
            # If fallback resolved to a different version, rewrite the lookup key
            if resolved and resolved != parsed_version:
                _, action = parse_syscall_name(name)
                fallback_name = f"sys.{resolved}.{action}"
                logger.warning(
                    "[SyscallDispatcher] version fallback: %r → %r",
                    name, fallback_name,
                )
                name = fallback_name
                parsed_version = resolved

        entry: SyscallEntry | None = SYSCALL_REGISTRY.get(name)
        if entry is None:
            return self._error_envelope(
                name, context,
                f"Unknown syscall: {name!r}",
                t_start,
                version=parsed_version,
            )

        # Step 2 — enforce capability
        if entry.capability not in context.capabilities:
            return self._error_envelope(
                name, context,
                f"Permission denied: '{name}' requires capability "
                f"'{entry.capability}'; caller has {context.capabilities}",
                t_start,
                version=parsed_version,
            )

        # Step 2b — tenant isolation: validate context has a user_id
        if not context.user_id:
            return self._error_envelope(
                name, context,
                "TENANT_VIOLATION: syscall requires authenticated tenant context",
                t_start,
                version=parsed_version,
            )

        # Step 2c — resource quota check (syscall budget)
        # If _get_rm() or check_quota() raises, fail-open (log warning, allow execution).
        # Only a clean (False, reason) return blocks the syscall.
        try:
            rm = _get_rm()
            quota_ok, quota_reason = rm.check_quota(context.execution_unit_id)
        except Exception as _rm_exc:
            logger.warning("[SyscallDispatcher] resource quota check skipped: %s", _rm_exc)
        else:
            if not quota_ok:
                return self._error_envelope(name, context, quota_reason, t_start,
                                            version=parsed_version)

        # Step 2d — input validation against ABI schema
        if entry.input_schema:
            errors = validate_input(entry.input_schema, payload)
            if errors:
                return self._error_envelope(
                    name, context,
                    f"Input validation failed for {name!r}: " + "; ".join(errors),
                    t_start,
                    version=parsed_version,
                )

        # Step 2e — deprecation check (warn but still execute)
        deprecation_warning: str | None = None
        if entry.deprecated:
            parts = [f"Syscall '{name}' is deprecated"]
            if entry.deprecated_since:
                parts.append(f"since {entry.deprecated_since}")
            if entry.replacement:
                parts.append(f"— use '{entry.replacement}' instead")
            deprecation_warning = " ".join(parts) + "."
            logger.warning("[SyscallDispatcher] %s", deprecation_warning)

        # Step 3 — execute handler
        try:
            data = entry.handler(payload, context)
        except Exception as exc:
            logger.warning(
                "[SyscallDispatcher] handler error '%s': %s", name, exc, exc_info=True,
            )
            self._emit_syscall_event(name, context, "error")
            return self._error_envelope(name, context, str(exc), t_start,
                                        version=parsed_version)

        # Step 3b — output validation (non-fatal: log warning, never fail execution)
        if entry.output_schema:
            out_errors = validate_output(entry.output_schema, data if isinstance(data, dict) else {})
            if out_errors:
                logger.warning(
                    "[SyscallDispatcher] output schema mismatch for '%s': %s",
                    name, "; ".join(out_errors),
                )

        # Step 4 — record syscall usage in ResourceManager (non-fatal)
        try:
            duration_so_far = int((time.monotonic() - t_start) * 1000)
            _get_rm().record_usage(
                context.execution_unit_id,
                {"syscall_count": 1, "cpu_time_ms": duration_so_far},
            )
        except Exception as _rm_exc:
            logger.debug("[SyscallDispatcher] resource record skipped: %s", _rm_exc)

        # Step 5 — emit observability event (non-fatal)
        try:
            self._emit_syscall_event(name, context, "success")
        except Exception as exc:
            logger.debug("[SyscallDispatcher] observability skipped for '%s': %s", name, exc)

        # Step 6 — return structured result
        return {
            "status": "success",
            "data": data,
            "trace_id": context.trace_id,
            "execution_unit_id": context.execution_unit_id,
            "syscall": name,
            "version": parsed_version,
            "duration_ms": int((time.monotonic() - t_start) * 1000),
            "error": None,
            "warning": deprecation_warning,
        }

    def _error_envelope(
        self,
        name: str,
        context: SyscallContext,
        message: str,
        t_start: float,
        version: str = "unknown",
    ) -> dict[str, Any]:
        return {
            "status": "error",
            "data": {},
            "trace_id": context.trace_id,
            "execution_unit_id": context.execution_unit_id,
            "syscall": name,
            "version": version,
            "duration_ms": int((time.monotonic() - t_start) * 1000),
            "error": message,
            "warning": None,
        }

    def _emit_syscall_event(
        self,
        name: str,
        context: SyscallContext,
        status: str,
    ) -> None:
        """Emit SYSCALL_EXECUTED to the A.I.N.D.Y. event bus.

        Non-fatal: all exceptions are swallowed and logged at DEBUG level
        so a broken event bus never kills a syscall execution.
        """
        try:
            from db.database import SessionLocal
            from core.system_event_service import emit_system_event
            from core.system_event_types import SystemEventTypes

            db = SessionLocal()
            try:
                emit_system_event(
                    db=db,
                    event_type=SystemEventTypes.SYSCALL_EXECUTED,
                    user_id=context.user_id,
                    trace_id=context.trace_id,
                    source="syscall_dispatcher",
                    payload={
                        "syscall_name": name,
                        "execution_unit_id": context.execution_unit_id,
                        "status": status,
                    },
                )
                db.commit()
            except Exception:
                db.rollback()
                raise
            finally:
                db.close()
        except Exception as exc:
            logger.debug(
                "[SyscallDispatcher] observability event skipped for '%s': %s",
                name, exc,
            )


# ── Module-level singleton ────────────────────────────────────────────────────

_DISPATCHER = SyscallDispatcher()


def get_dispatcher() -> SyscallDispatcher:
    """Return the module-level SyscallDispatcher singleton.

    Use this in all production code. Tests can instantiate SyscallDispatcher()
    directly if they need isolation.
    """
    return _DISPATCHER


# ── Context builder helpers ───────────────────────────────────────────────────

def make_syscall_ctx_from_flow(
    context: dict,
    capabilities: list[str] | None = None,
) -> SyscallContext:
    """Build a SyscallContext from a flow node's execution context dict.

    Args:
        context:      The flow context dict (keys: run_id, user_id, trace_id,
                      workflow_type, flow_name, node_name, db).
        capabilities: Explicit capability list. Pass only what the node needs
                      (least-privilege). Defaults to DEFAULT_NODUS_CAPABILITIES.

    Returns:
        SyscallContext ready to pass to get_dispatcher().dispatch().
    """
    return SyscallContext(
        execution_unit_id=str(context.get("run_id") or ""),
        user_id=str(context.get("user_id") or ""),
        capabilities=list(capabilities) if capabilities is not None else list(DEFAULT_NODUS_CAPABILITIES),
        trace_id=str(context.get("trace_id") or context.get("run_id") or ""),
        metadata={
            "workflow_type": context.get("workflow_type"),
            "flow_name": context.get("flow_name"),
            "node_name": context.get("node_name"),
        },
    )


def make_syscall_ctx_from_tool(
    user_id: str,
    run_id: str = "",
    capabilities: list[str] | None = None,
) -> SyscallContext:
    """Build a SyscallContext for an agent tool call.

    Args:
        user_id:      The authenticated user ID.
        run_id:       Optional agent run ID for trace correlation.
        capabilities: Explicit capability list. Pass only what the tool needs.

    Returns:
        SyscallContext ready to pass to get_dispatcher().dispatch().
    """
    execution_unit_id = run_id or str(_uuid.uuid4())
    return SyscallContext(
        execution_unit_id=execution_unit_id,
        user_id=str(user_id or ""),
        capabilities=list(capabilities) if capabilities is not None else list(DEFAULT_NODUS_CAPABILITIES),
        trace_id=execution_unit_id,
    )


def child_context(
    parent: SyscallContext,
    *,
    capabilities: list[str] | None = None,
    metadata: dict | None = None,
) -> SyscallContext:
    """Build a child SyscallContext that inherits trace_id and eu_id from parent.

    Use this when a handler explicitly dispatches a nested syscall and wants to
    forward the full execution identity — trace_id, execution_unit_id, and
    user_id — unchanged.  capabilities and metadata can be overridden.

    The ContextVar mechanism in dispatch() already propagates the trace
    automatically for most cases; use child_context() when you need the
    explicit form (e.g. for documentation clarity or override of capabilities).

    Example::

        def _handle_flow_run(payload, context):
            ctx = child_context(context, capabilities=["memory.read"])
            return get_dispatcher().dispatch("sys.v1.memory.read", {}, ctx)
    """
    return SyscallContext(
        execution_unit_id=parent.execution_unit_id,
        user_id=parent.user_id,
        capabilities=capabilities if capabilities is not None else list(parent.capabilities),
        trace_id=parent.trace_id,
        memory_context=list(parent.memory_context),
        metadata=metadata if metadata is not None else dict(parent.metadata),
    )

