from __future__ import annotations

import inspect
import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from fastapi import HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import Response

logger = logging.getLogger(__name__)


# ── EU-type routing ───────────────────────────────────────────────────────────

# Maps the first segment of a route_name to the EU type used for retry-policy
# resolution and (when async is enabled) thread-pool dispatch mode decisions.
# Unmapped prefixes default to "task" which resolves to INLINE / low retry.
_EU_TYPE_BY_ROUTE_PREFIX: dict[str, str] = {
    "agent":      "agent",
    "arm":        "flow",
    "automation": "job",
    "dashboard":  "task",
    "flow":       "flow",
    "genesis":    "flow",
    "leadgen":    "flow",
    "masterplan": "flow",
    "memory":     "flow",
    "nodus":      "nodus",
    "platform":   "job",
    "score":      "task",
    "task":       "task",
    "watcher":    "task",
}


def _route_eu_type(route_name: str) -> str:
    """Derive the ExecutionUnit type from the route_name's first segment."""
    prefix = (route_name or "").split(".")[0]
    return _EU_TYPE_BY_ROUTE_PREFIX.get(prefix, "task")


@dataclass(slots=True)
class ExecutionContext:
    request_id: str
    route_name: str
    user_id: str | None = None
    input_payload: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)
    pipeline_active: bool = True

    @classmethod
    def from_request(cls, request: Request | None, route_name: str) -> "ExecutionContext":
        if request is None:
            return cls(
                request_id=str(uuid.uuid4()),
                route_name=route_name,
                input_payload={},
                metadata={},
            )

        request_id = (
            request.headers.get("X-Trace-ID")
            or request.headers.get("X-Request-ID")
            or str(uuid.uuid4())
        )
        return cls(
            request_id=request_id,
            route_name=route_name,
            input_payload={
                "method": request.method,
                "path": request.url.path,
                "query": dict(request.query_params),
                "path_params": dict(request.path_params),
            },
            metadata={},
        )


@dataclass(slots=True)
class ExecutionResult:
    success: bool
    data: Any = None
    error: str | None = None
    memory_context_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    eu_status: str | None = None
    # When set, overrides the default "success" / "error" label in to_response().
    # Use "waiting" when the handler entered WAIT, "resumed" when an EU is
    # picked back up.  All other values fall through to the success/error mapping.

    def to_response(self) -> dict[str, Any]:
        trace_id = str(self.metadata.get("trace_id") or "")
        eu_id = self.metadata.get("eu_id")
        payload_data = self.data if isinstance(self.data, Response) else jsonable_encoder(self.data)
        # eu_status overrides the default success/error label when set.
        # "waiting" and "resumed" are non-terminal states — data is still returned.
        status_label = self.eu_status or ("success" if self.success else "error")
        canonical_metadata = {
            "events": list(self.metadata.get("event_refs") or []),
            "next_action": self.metadata.get("next_action"),
        }
        if self.eu_status == "waiting":
            canonical_metadata["eu_wait_for"] = self.metadata.get("eu_wait_for")
        if not self.success:
            canonical_metadata["error"] = jsonable_encoder(
                self.metadata.get("detail") or self.error or "Execution failed"
            )
            status_code = self.metadata.get("status_code")
            if status_code is not None:
                canonical_metadata["status_code"] = status_code
        return {
            "status": status_label,
            "data": payload_data,
            "trace_id": trace_id,
            "eu_id": eu_id,
            "memory_context_count": self.memory_context_count,
            "metadata": canonical_metadata,
        }


class ExecutionPipeline:
    async def run(
        self,
        ctx: ExecutionContext,
        handler: Callable[[ExecutionContext], Any],
    ) -> ExecutionResult:
        # Lazy import to avoid circular dependency (execution_gate ↔ execution_pipeline).
        # Must be at the top of run() so the name is bound before the try/except.
        from AINDY.core.execution_gate import ExecutionWaitSignal

        trace_id = str(ctx.request_id)
        ctx.metadata.setdefault("trace_id", trace_id)
        started_event_id: str | None = None
        parent_token: Any = None
        pipeline_token: Any = None
        execution_ctx_token: Any = None

        logger.info(
            "execution.entry=PIPELINE",
            extra={"route": ctx.route_name, "trace_id": trace_id},
        )
        logger.info("pipeline.entry", extra={"route": ctx.route_name})

        try:
            started_event_id = self._safe_emit_event(
                ctx,
                event_type="execution.started",
                payload={"route_name": ctx.route_name},
            )
            parent_token = self._safe_set_parent_event(started_event_id)
            pipeline_token = self._safe_set_pipeline_active()
            execution_ctx_token = self._safe_set_current_execution_context(ctx)
            self._safe_require_eu(ctx)
            _handler_start = time.monotonic()
            result = handler(ctx)
            if inspect.isawaitable(result):
                result = await result

            if isinstance(result, Response):
                self._handle_contract_violation(
                    "ExecutionContract violation: raw Response returned",
                )
            result, signals = self._extract_execution_result_and_signals(result)
            signals = self._merge_queued_signals(ctx, signals)

            # ── WAIT detection (dict signal from flow/nodus/generic handlers) ──
            wait_signal = self._detect_wait(result)
            if wait_signal is not None:
                wait_for, wait_payload, _wc = wait_signal
                self._safe_transition_eu_waiting(ctx, wait_for=wait_for, wait_condition=_wc)
                wait_event_id = self._safe_emit_event(
                    ctx,
                    event_type="execution.waiting",
                    parent_event_id=started_event_id,
                    payload={
                        "route_name": ctx.route_name,
                        "wait_for": wait_for,
                        **wait_payload,
                    },
                )
                self._set_event_refs(
                    ctx,
                    started_event_id,
                    terminal_event_id=wait_event_id,
                    completed=False,
                )
                ctx.metadata["eu_status"] = "waiting"
                ctx.metadata["eu_wait_for"] = wait_for
                logger.info(
                    "execution.waiting",
                    extra={"route": ctx.route_name, "wait_for": wait_for},
                )
                return ExecutionResult(
                    success=True,
                    eu_status="waiting",
                    data=result,
                    metadata=ctx.metadata,
                )
            # ─────────────────────────────────────────────────────────────────

            injected_count = self._apply_execution_signals(ctx, signals)
            memory_context_count = max(
                self._extract_memory_context_count(result),
                injected_count,
                self._safe_recall_memory_count(ctx),
            )

            _duration_ms = round((time.monotonic() - _handler_start) * 1000, 2)
            result = self._inject_execution_envelope(ctx, result, _duration_ms)

            completed_event_id = self._safe_emit_event(
                ctx,
                event_type="execution.completed",
                parent_event_id=started_event_id,
                payload={"route_name": ctx.route_name, "success": True},
            )
            self._set_event_refs(
                ctx,
                started_event_id,
                terminal_event_id=completed_event_id,
                completed=True,
            )
            self._safe_finalize_eu(ctx, "completed")
            logger.info(
                "execution.completed",
                extra={"route": ctx.route_name, "success": True},
            )
            return ExecutionResult(
                success=True,
                data=result,
                memory_context_count=memory_context_count,
                metadata=ctx.metadata,
            )
        except ExecutionWaitSignal as exc:
            # Handler explicitly requested WAIT via raise — not a failure,
            # UNLESS the EU context is missing (no eu_id or no db).
            # _safe_transition_eu_waiting() raises RuntimeError in that case.
            # We catch it here so the error stays inside run() and becomes a
            # proper failure result rather than propagating to the caller.
            try:
                self._safe_transition_eu_waiting(
                    ctx, wait_for=exc.wait_for, wait_condition=exc.wait_condition
                )
            except Exception as _wait_guard_exc:
                # EU context absent — WAIT cannot be tracked and is unresumable.
                # Convert to a failure; do not silently swallow.
                logger.critical(
                    "execution.wait_untrackable eu=%s route=%s wait_for=%s: %s",
                    ctx.metadata.get("eu_id"),
                    ctx.route_name,
                    exc.wait_for,
                    _wait_guard_exc,
                )
                _guard_fail_event_id = self._safe_emit_event(
                    ctx,
                    event_type="execution.failed",
                    parent_event_id=started_event_id,
                    payload={
                        "route_name": ctx.route_name,
                        "detail": str(_wait_guard_exc),
                    },
                )
                self._set_event_refs(
                    ctx,
                    started_event_id,
                    terminal_event_id=_guard_fail_event_id,
                    completed=False,
                )
                self._safe_finalize_eu(ctx, "failed")
                return ExecutionResult(
                    success=False,
                    error=str(_wait_guard_exc),
                    metadata={
                        **ctx.metadata,
                        "status_code": 500,
                        "detail": str(_wait_guard_exc),
                    },
                )

            wait_event_id = self._safe_emit_event(
                ctx,
                event_type="execution.waiting",
                parent_event_id=started_event_id,
                payload={
                    "route_name": ctx.route_name,
                    "wait_for": exc.wait_for,
                    "resume_key": exc.resume_key,
                    **exc.payload,
                },
            )
            self._set_event_refs(
                ctx,
                started_event_id,
                terminal_event_id=wait_event_id,
                completed=False,
            )
            ctx.metadata["eu_status"] = "waiting"
            ctx.metadata["eu_wait_for"] = exc.wait_for
            logger.info(
                "execution.waiting (raised)",
                extra={"route": ctx.route_name, "wait_for": exc.wait_for},
            )
            return ExecutionResult(
                success=True,
                eu_status="waiting",
                data={
                    "status": "WAITING",
                    "wait_for": exc.wait_for,
                    "resume_key": exc.resume_key,
                    **exc.payload,
                },
                metadata=ctx.metadata,
            )
        except HTTPException as exc:
            failed_event_id = self._safe_emit_event(
                ctx,
                event_type="execution.failed",
                parent_event_id=started_event_id,
                payload={
                    "route_name": ctx.route_name,
                    "status_code": exc.status_code,
                    "detail": exc.detail,
                },
            )
            self._set_event_refs(
                ctx,
                started_event_id,
                terminal_event_id=failed_event_id,
                completed=False,
            )
            self._safe_finalize_eu(ctx, "failed")
            logger.info(
                "execution.completed",
                extra={"route": ctx.route_name, "success": False},
            )
            return ExecutionResult(
                success=False,
                error=str(exc.detail),
                metadata={
                    **ctx.metadata,
                    "status_code": exc.status_code,
                    "detail": exc.detail,
                },
            )
        except Exception as exc:
            failed_event_id = self._safe_emit_event(
                ctx,
                event_type="execution.failed",
                parent_event_id=started_event_id,
                payload={"route_name": ctx.route_name, "detail": str(exc)},
            )
            self._set_event_refs(
                ctx,
                started_event_id,
                terminal_event_id=failed_event_id,
                completed=False,
            )
            self._safe_finalize_eu(ctx, "failed")
            logger.exception("execution.failed", extra={"route": ctx.route_name})
            return ExecutionResult(
                success=False,
                error=str(exc),
                metadata={**ctx.metadata, "status_code": 500, "detail": str(exc)},
            )
        finally:
            self._safe_reset_current_execution_context(execution_ctx_token)
            self._safe_reset_pipeline_active(pipeline_token)
            self._safe_reset_parent_event(parent_token)

    def _extract_memory_context_count(self, result: Any) -> int:
        if isinstance(result, dict):
            count = result.get("memory_context_count")
            if isinstance(count, int):
                return count
            context = result.get("memory_context")
            if isinstance(context, list):
                return len(context)
            if isinstance(context, str) and context.strip():
                return 1
        return 0

    def _safe_emit_event(
        self,
        ctx: ExecutionContext,
        *,
        event_type: str,
        payload: dict[str, Any] | None = None,
        parent_event_id: str | None = None,
    ) -> str | None:
        db = ctx.metadata.get("db")
        if db is None:
            return None
        try:
            from AINDY.core.system_event_service import emit_system_event

            event_id = emit_system_event(
                db=db,
                event_type=event_type,
                user_id=ctx.user_id,
                trace_id=ctx.request_id,
                parent_event_id=parent_event_id,
                source=str(ctx.metadata.get("source") or ctx.route_name),
                payload=payload or {},
                required=False,
                skip_memory_capture=bool(ctx.metadata.get("disable_memory_capture")),
            )
            return str(event_id) if event_id else None
        except Exception:
            logger.debug("execution.event_emit_skipped", exc_info=True)
            return None

    def _safe_set_parent_event(self, parent_event_id: str | None) -> Any:
        if not parent_event_id:
            return None
        try:
            from AINDY.utils.trace_context import set_parent_event_id

            return set_parent_event_id(parent_event_id)
        except Exception:
            logger.debug("execution.parent_event_set_skipped", exc_info=True)
            return None

    def _safe_reset_parent_event(self, token: Any) -> None:
        if token is None:
            return
        try:
            from AINDY.utils.trace_context import reset_parent_event_id

            reset_parent_event_id(token)
        except Exception:
            logger.debug("execution.parent_event_reset_skipped", exc_info=True)

    def _set_event_refs(
        self,
        ctx: ExecutionContext,
        started_event_id: str | None,
        *,
        terminal_event_id: str | None,
        completed: bool,
    ) -> None:
        refs: list[dict[str, str]] = []
        if started_event_id:
            refs.append({"type": "execution.started", "id": str(started_event_id)})
        terminal_type = "execution.completed" if completed else "execution.failed"
        if terminal_event_id:
            refs.append({"type": terminal_type, "id": str(terminal_event_id)})
        ctx.metadata["event_refs"] = refs

    def _apply_execution_hints(self, ctx: ExecutionContext, result: Any) -> Any:
        if not isinstance(result, dict):
            return result

        hints = result.get("execution_hints") or {}
        memory_hints = []
        if isinstance(hints, dict):
            hinted_memory = hints.get("memory")
            if isinstance(hinted_memory, list):
                memory_hints.extend(item for item in hinted_memory if isinstance(item, dict))
            elif isinstance(hinted_memory, dict):
                memory_hints.append(hinted_memory)

        memory_hint = result.get("memory_hint")
        if isinstance(memory_hint, dict):
            memory_hints.append(memory_hint)

        for hint in memory_hints:
            self._safe_capture_memory_hint(ctx, hint)

        if "data" in result and ("execution_hints" in result or "memory_hint" in result):
            return result["data"]
        return result

    def _extract_execution_result_and_signals(self, result: Any) -> tuple[Any, dict[str, Any]]:
        if isinstance(result, dict):
            if "execution_signals" in result:
                return result.get("data"), dict(result.get("execution_signals") or {})
            if "execution_hints" in result:
                hints = dict(result.get("execution_hints") or {})
                signals = {
                    "memory": hints.get("memory"),
                    "events": hints.get("events"),
                    "log": hints.get("log"),
                }
                return result.get("data"), signals
            if "memory_hint" in result:
                return result.get("data"), {"memory": result.get("memory_hint")}

        object_signals = getattr(result, "_execution_signals", None)
        if object_signals:
            return result, dict(object_signals or {})
        return result, {}

    def _apply_execution_signals(self, ctx: ExecutionContext, signals: dict[str, Any]) -> int:
        memory_count = self._apply_memory_signals(ctx, signals.get("memory"))
        self._apply_event_signals(ctx, signals.get("events"))
        queued_signals = self._merge_queued_signals(ctx, {})
        if queued_signals.get("memory") or queued_signals.get("events"):
            memory_count = max(memory_count, self._apply_memory_signals(ctx, queued_signals.get("memory")))
            self._apply_event_signals(ctx, queued_signals.get("events"))
        self._apply_log_signal(ctx, signals.get("log"), memory_count=memory_count)
        return memory_count

    def _merge_queued_signals(self, ctx: ExecutionContext, signals: dict[str, Any]) -> dict[str, Any]:
        queued = dict(ctx.metadata.pop("queued_execution_signals", {}) or {})
        merged = dict(signals or {})
        for key in ("memory", "events"):
            queued_value = queued.get(key)
            if not queued_value:
                continue
            current_value = merged.get(key)
            items: list[Any] = []
            if isinstance(current_value, list):
                items.extend(current_value)
            elif current_value is not None:
                items.append(current_value)
            if isinstance(queued_value, list):
                items.extend(queued_value)
            else:
                items.append(queued_value)
            merged[key] = items
        return merged

    def _apply_memory_signals(self, ctx: ExecutionContext, memory_signal: Any) -> int:
        hints: list[dict[str, Any]] = []
        if isinstance(memory_signal, dict):
            hints.append(memory_signal)
        elif isinstance(memory_signal, list):
            hints.extend(item for item in memory_signal if isinstance(item, dict))

        count = 0
        for hint in hints:
            if self._safe_capture_memory_hint(ctx, hint):
                count += 1
        if count:
            logger.info("memory.injected", extra={"route": ctx.route_name, "count": count})
        return count

    def _apply_event_signals(self, ctx: ExecutionContext, events_signal: Any) -> None:
        events: list[dict[str, Any]] = []
        if isinstance(events_signal, dict):
            events.append(events_signal)
        elif isinstance(events_signal, list):
            events.extend(item for item in events_signal if isinstance(item, dict))

        injected = 0
        for event in events:
            event_type = str(event.get("event_type") or event.get("type") or "").strip()
            if not event_type:
                continue
            db = ctx.metadata.get("db")
            if db is None:
                continue
            try:
                from AINDY.core.system_event_service import emit_system_event

                event_id = emit_system_event(
                    db=db,
                    event_type=event_type,
                    user_id=event.get("user_id") or ctx.user_id,
                    trace_id=event.get("trace_id") or ctx.request_id,
                    parent_event_id=event.get("parent_event_id"),
                    source=str(event.get("source") or ctx.metadata.get("source") or ctx.route_name),
                    agent_id=event.get("agent_id"),
                    payload=dict(event.get("payload") or {}),
                    required=bool(event.get("required", False)),
                )
            except Exception:
                logger.debug("execution.event_emit_skipped", exc_info=True)
                event_id = None
            if event_id:
                injected += 1
        if injected:
            logger.info("events.injected", extra={"route": ctx.route_name, "count": injected})

    def _apply_log_signal(self, ctx: ExecutionContext, log_signal: Any, *, memory_count: int) -> None:
        if not isinstance(log_signal, dict):
            return
        level = str(log_signal.get("level") or "info").lower()
        message = str(log_signal.get("message") or "execution.signal")
        extra = dict(log_signal.get("extra") or {})
        extra.setdefault("route", ctx.route_name)
        extra.setdefault("trace_id", ctx.request_id)
        extra.setdefault("memory_used", memory_count > 0)
        log_fn = getattr(logger, level, logger.info)
        try:
            log_fn(message, extra=extra)
        except Exception:
            logger.debug("execution.log_signal_skipped", exc_info=True)

    def _safe_capture_memory_hint(self, ctx: ExecutionContext, hint: dict[str, Any]) -> bool:
        db = ctx.metadata.get("db")
        if db is None:
            return False
        try:
            from AINDY.memory.memory_capture_engine import MemoryCaptureEngine

            engine = MemoryCaptureEngine(
                db=db,
                user_id=str(hint.get("user_id") or ctx.user_id) if (hint.get("user_id") or ctx.user_id) else None,
                agent_namespace=str(hint.get("agent_namespace") or ctx.route_name.split(".")[0]),
            )
            engine.evaluate_and_capture(
                event_type=str(hint.get("event_type") or ctx.route_name),
                content=str(hint.get("content") or ""),
                source=str(hint.get("source") or ctx.route_name),
                tags=list(hint.get("tags") or []),
                node_type=str(hint.get("node_type") or "insight"),
                force=bool(hint.get("force", False)),
                extra=dict(hint.get("extra") or {}),
                allow_when_pipeline_active=True,
            )
            return True
        except Exception:
            logger.debug("execution.memory_hint_skipped", exc_info=True)
            return False

    def _safe_recall_memory_count(self, ctx: ExecutionContext) -> int:
        db = ctx.metadata.get("db")
        if db is None or not ctx.user_id:
            return 0
        try:
            from AINDY.db.dao.memory_node_dao import MemoryNodeDAO
            from AINDY.runtime.memory import MemoryOrchestrator

            query = ""
            if isinstance(ctx.input_payload, dict):
                query = str(
                    ctx.input_payload.get("query")
                    or ctx.input_payload.get("task_name")
                    or ctx.input_payload.get("name")
                    or ctx.route_name
                )
            else:
                query = str(ctx.input_payload or ctx.route_name)
            orchestrator = MemoryOrchestrator(MemoryNodeDAO)
            context = orchestrator.get_context(
                user_id=str(ctx.user_id),
                query=query,
                task_type="execution",
                db=db,
                max_tokens=300,
                metadata={"limit": 3},
            )
            return len(context.items) if context and getattr(context, "items", None) else 0
        except Exception:
            logger.debug("execution.memory_recall_skipped", exc_info=True)
            return 0

    def _handle_contract_violation(self, message: str) -> None:
        try:
            from AINDY.config import settings

            if settings.ENFORCE_EXECUTION_CONTRACT:
                raise RuntimeError(message)
        except Exception:
            raise
        logger.warning(message)

    def _safe_set_pipeline_active(self) -> Any:
        try:
            from AINDY.utils.trace_context import set_pipeline_active

            return set_pipeline_active(True)
        except Exception:
            logger.debug("execution.pipeline_active_set_skipped", exc_info=True)
            return None

    def _safe_reset_pipeline_active(self, token: Any) -> None:
        if token is None:
            return
        try:
            from AINDY.utils.trace_context import reset_pipeline_active

            reset_pipeline_active(token)
        except Exception:
            logger.debug("execution.pipeline_active_reset_skipped", exc_info=True)

    def _safe_set_current_execution_context(self, ctx: ExecutionContext) -> Any:
        try:
            from AINDY.utils.trace_context import set_current_execution_context

            return set_current_execution_context(ctx)
        except Exception:
            logger.debug("execution.current_ctx_set_skipped", exc_info=True)
            return None

    def _safe_reset_current_execution_context(self, token: Any) -> None:
        if token is None:
            return
        try:
            from AINDY.utils.trace_context import reset_current_execution_context

            reset_current_execution_context(token)
        except Exception:
            logger.debug("execution.current_ctx_reset_skipped", exc_info=True)

    # ── WAIT detection and transition ────────────────────────────────────────

    def _detect_wait(self, result: Any) -> tuple[str, dict, Any] | None:
        """
        Return ``(wait_for, extra_payload, wait_condition)`` if ``result``
        signals a WAIT, otherwise return ``None``.

        ``wait_condition`` is a ``WaitCondition`` instance when the signal
        carries one, otherwise ``None`` (caller constructs a default).

        Two accepted forms:
        - ``ExecutionWaitSignal`` instance returned as a value (unusual but
          supported — some handlers prefer returning over raising).
        - Dict with ``{"status": "WAITING", ...}`` — the shape produced by
          ``PersistentFlowRunner`` and generic WAITING responses.

        The raise-based path is handled by ``except ExecutionWaitSignal``
        in ``run()``.  This method only handles the return-value form.
        """
        from AINDY.core.execution_gate import ExecutionWaitSignal  # lazy to avoid circular

        if isinstance(result, ExecutionWaitSignal):
            return result.wait_for, result.payload, result.wait_condition
        if isinstance(result, dict) and str(result.get("status") or "").upper() == "WAITING":
            wait_for = str(
                result.get("wait_for")
                or result.get("waiting_for")
                or "unknown"
            )
            return wait_for, {}, None
        return None

    def _safe_transition_eu_waiting(
        self,
        ctx: ExecutionContext,
        *,
        wait_for: str,
        wait_condition=None,  # WaitCondition | None
    ) -> None:
        """
        Transition the route-level EU from ``executing`` to ``waiting`` and
        register the wait with SchedulerEngine — the single WAIT authority.

        **WAIT requires an ExecutionUnit.**  If ``eu_id`` or ``db`` is absent
        this method raises ``RuntimeError`` rather than silently returning.
        A WAIT without an EU can never be resumed — allowing it would create
        permanently lost executions.  Callers must convert the raised error
        into a failure result; both WAIT paths in ``run()`` do this.

        Raises:
            RuntimeError: When ``eu_id`` is absent (EU was never created —
                          unauthenticated or DB-less route) or when ``db`` is
                          absent (cannot persist the waiting status).

        Args:
            ctx:            Current ExecutionContext.
            wait_for:       Event name that will wake this EU.
            wait_condition: Optional ``WaitCondition`` instance.  When absent,
                            a default event-type condition is constructed from
                            ``wait_for``.

        SchedulerEngine.register_wait() is called with:
          run_id          = eu_id  (unique per wait; flows use FlowRun.id)
          wait_for_event  = wait_for
          resume_callback = ExecutionUnitService.resume_execution_unit(eu_id)
          correlation_id  = trace_id from ctx
          trace_id        = trace_id from ctx
          wait_condition  = structured WaitCondition (event or time)
        """
        eu_id = ctx.metadata.get("eu_id")
        db = ctx.metadata.get("db")

        # ── Guard: WAIT requires ExecutionUnit context ─────────────────────────
        # Missing eu_id → EU was never created (route has no user_id or no db).
        # Missing db    → cannot persist waiting status or WaitCondition.
        # Either condition makes the WAIT permanently unresumable — fail early.
        if not eu_id:
            raise RuntimeError(
                f"WAIT requires ExecutionUnit context — eu_id is absent "
                f"(route={ctx.route_name!r}, wait_for={wait_for!r}). "
                "Ensure the route has an authenticated user_id and a DB session "
                "so an ExecutionUnit can be created before entering WAIT."
            )
        if db is None:
            raise RuntimeError(
                f"WAIT requires ExecutionUnit context — db session is absent "
                f"(route={ctx.route_name!r}, eu_id={eu_id!r}, wait_for={wait_for!r}). "
                "Cannot persist waiting status without a database session."
            )
        # ─────────────────────────────────────────────────────────────────────

        try:
            from AINDY.core.execution_unit_service import ExecutionUnitService
            from AINDY.core.wait_condition import WaitCondition

            # Build a WaitCondition if the caller didn't provide one.
            if wait_condition is None:
                _trace = str(ctx.metadata.get("trace_id") or ctx.request_id)
                wait_condition = WaitCondition.for_event(wait_for, correlation_id=_trace)

            eus = ExecutionUnitService(db)
            eus.update_status(eu_id, "waiting")
            eus.set_wait_condition(eu_id, wait_condition)

            # Register with SchedulerEngine so notify_event(event_type) can
            # re-enqueue this EU when the awaited event fires.
            try:
                from AINDY.kernel.scheduler_engine import get_scheduler_engine, PRIORITY_NORMAL

                _eu_id = eu_id
                _db = db
                _trace = str(ctx.metadata.get("trace_id") or ctx.request_id)
                get_scheduler_engine().register_wait(
                    run_id=_eu_id,
                    wait_for_event=wait_for,
                    tenant_id=str(ctx.user_id or ""),
                    eu_id=_eu_id,
                    resume_callback=lambda: ExecutionUnitService(_db).resume_execution_unit(_eu_id),
                    priority=PRIORITY_NORMAL,
                    correlation_id=_trace,
                    trace_id=_trace,
                    eu_type=_route_eu_type(ctx.route_name),
                    wait_condition=wait_condition,
                )
                logger.debug(
                    "[Pipeline] SchedulerEngine.register_wait eu=%s wait_for=%s cond_type=%s trace=%s",
                    _eu_id, wait_for, wait_condition.type, _trace,
                )
            except Exception as _se_exc:
                logger.debug("[Pipeline] scheduler register_wait skipped: %s", _se_exc)

            logger.info(
                "[Pipeline] EU→waiting eu_id=%s wait_for=%s",
                eu_id,
                wait_for,
            )
        except Exception:
            logger.debug("execution.eu_transition_waiting_skipped", exc_info=True)

    # ── ExecutionEnvelope auto-injection ─────────────────────────────────────

    def _inject_execution_envelope(
        self,
        ctx: ExecutionContext,
        result: Any,
        duration_ms: float,
    ) -> Any:
        """
        Inject ``execution_envelope`` into the result dict when absent.

        Uses ``setdefault`` so routes that already embed an envelope manually
        (task, genesis, arm, watcher, memory routers) are left untouched.
        Non-dict results (lists, None, raw objects) are returned unchanged.
        Non-fatal: any import/call error is swallowed and logged at DEBUG.
        """
        if not isinstance(result, dict):
            return result
        try:
            from AINDY.core.execution_gate import to_envelope

            result.setdefault(
                "execution_envelope",
                to_envelope(
                    eu_id=ctx.metadata.get("eu_id"),
                    trace_id=str(ctx.metadata.get("trace_id") or ctx.request_id),
                    status="SUCCESS",
                    output=None,
                    error=None,
                    duration_ms=duration_ms,
                    attempt_count=1,
                ),
            )
        except Exception:
            logger.debug("execution.envelope_inject_skipped", exc_info=True)
        return result

    # ── ExecutionUnit integration ─────────────────────────────────────────────

    def _safe_require_eu(self, ctx: ExecutionContext) -> str | None:
        """
        Create (or re-enter) a DB-backed ExecutionUnit for this request.

        Skipped silently when:
          - ``ctx.metadata["db"]`` is absent (route doesn't use a DB session)
          - ``ctx.user_id`` is None (unauthenticated / background routes)

        The EU id is stored in ``ctx.metadata["eu_id"]`` so handlers,
        adapters, and ``to_response()`` can surface it without extra lookups.
        Non-fatal: any exception is caught and logged at DEBUG level.
        """
        db = ctx.metadata.get("db")
        if db is None or not ctx.user_id:
            return None
        try:
            from AINDY.core.execution_gate import require_execution_unit

            eu = require_execution_unit(
                db=db,
                eu_type=_route_eu_type(ctx.route_name),
                user_id=str(ctx.user_id),
                source_type="route",
                source_id=ctx.request_id,
                correlation_id=ctx.request_id,
                extra={
                    "route_name": ctx.route_name,
                    "workflow_type": ctx.route_name,
                },
            )
            eu_id = str(eu.id) if eu is not None else None
            ctx.metadata["eu_id"] = eu_id
            logger.debug(
                "[Pipeline] EU registered route=%s eu_id=%s trace_id=%s",
                ctx.route_name,
                eu_id,
                ctx.request_id,
            )
            return eu_id
        except Exception:
            logger.debug("execution.eu_register_skipped", exc_info=True)
            return None

    def _safe_finalize_eu(self, ctx: ExecutionContext, status: str) -> None:
        """
        Transition the route-level EU to ``status`` (``"completed"`` or
        ``"failed"``).  No-op when no EU was created for this request.
        Non-fatal: any exception is caught and logged at DEBUG level.
        """
        eu_id = ctx.metadata.get("eu_id")
        if not eu_id:
            return
        db = ctx.metadata.get("db")
        if db is None:
            return
        try:
            from AINDY.core.execution_unit_service import ExecutionUnitService

            ExecutionUnitService(db).update_status(eu_id, status)
            logger.debug(
                "[Pipeline] EU finalised eu_id=%s status=%s",
                eu_id,
                status,
            )
        except Exception:
            logger.debug("execution.eu_finalize_skipped", exc_info=True)

