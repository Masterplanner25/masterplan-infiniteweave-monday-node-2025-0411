from __future__ import annotations

import inspect
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from fastapi import HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import Response

logger = logging.getLogger(__name__)


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

    def to_response(self) -> dict[str, Any]:
        trace_id = str(self.metadata.get("trace_id") or "")
        payload_data = self.data if isinstance(self.data, Response) else jsonable_encoder(self.data)
        canonical_metadata = {
            "events": list(self.metadata.get("event_refs") or []),
            "next_action": self.metadata.get("next_action"),
        }
        if not self.success:
            canonical_metadata["error"] = jsonable_encoder(
                self.metadata.get("detail") or self.error or "Execution failed"
            )
        return {
            "status": "success" if self.success else "error",
            "data": None if not self.success else payload_data,
            "trace_id": trace_id,
            "memory_context_count": self.memory_context_count,
            "metadata": canonical_metadata,
        }


class ExecutionPipeline:
    async def run(
        self,
        ctx: ExecutionContext,
        handler: Callable[[ExecutionContext], Any],
    ) -> ExecutionResult:
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
            result = handler(ctx)
            if inspect.isawaitable(result):
                result = await result

            if isinstance(result, Response):
                self._handle_contract_violation(
                    "ExecutionContract violation: raw Response returned",
                )
            result, signals = self._extract_execution_result_and_signals(result)
            signals = self._merge_queued_signals(ctx, signals)
            injected_count = self._apply_execution_signals(ctx, signals)
            memory_context_count = max(
                self._extract_memory_context_count(result),
                injected_count,
                self._safe_recall_memory_count(ctx),
            )

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
            from core.system_event_service import emit_system_event

            event_id = emit_system_event(
                db=db,
                event_type=event_type,
                user_id=ctx.user_id,
                trace_id=ctx.request_id,
                parent_event_id=parent_event_id,
                source=str(ctx.metadata.get("source") or ctx.route_name),
                payload=payload or {},
                required=False,
            )
            return str(event_id) if event_id else None
        except Exception:
            logger.debug("execution.event_emit_skipped", exc_info=True)
            return None

    def _safe_set_parent_event(self, parent_event_id: str | None) -> Any:
        if not parent_event_id:
            return None
        try:
            from utils.trace_context import set_parent_event_id

            return set_parent_event_id(parent_event_id)
        except Exception:
            logger.debug("execution.parent_event_set_skipped", exc_info=True)
            return None

    def _safe_reset_parent_event(self, token: Any) -> None:
        if token is None:
            return
        try:
            from utils.trace_context import reset_parent_event_id

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
            event_id = self._safe_emit_event(
                ctx,
                event_type=event_type,
                payload=dict(event.get("payload") or {}),
                parent_event_id=event.get("parent_event_id"),
            )
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
            from memory.memory_capture_engine import MemoryCaptureEngine

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
            from db.dao.memory_node_dao import MemoryNodeDAO
            from runtime.memory import MemoryOrchestrator

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
            from config import settings

            if settings.ENFORCE_EXECUTION_CONTRACT:
                raise RuntimeError(message)
        except Exception:
            raise
        logger.warning(message)

    def _safe_set_pipeline_active(self) -> Any:
        try:
            from utils.trace_context import set_pipeline_active

            return set_pipeline_active(True)
        except Exception:
            logger.debug("execution.pipeline_active_set_skipped", exc_info=True)
            return None

    def _safe_reset_pipeline_active(self, token: Any) -> None:
        if token is None:
            return
        try:
            from utils.trace_context import reset_pipeline_active

            reset_pipeline_active(token)
        except Exception:
            logger.debug("execution.pipeline_active_reset_skipped", exc_info=True)

    def _safe_set_current_execution_context(self, ctx: ExecutionContext) -> Any:
        try:
            from utils.trace_context import set_current_execution_context

            return set_current_execution_context(ctx)
        except Exception:
            logger.debug("execution.current_ctx_set_skipped", exc_info=True)
            return None

    def _safe_reset_current_execution_context(self, token: Any) -> None:
        if token is None:
            return
        try:
            from utils.trace_context import reset_current_execution_context

            reset_current_execution_context(token)
        except Exception:
            logger.debug("execution.current_ctx_reset_skipped", exc_info=True)

