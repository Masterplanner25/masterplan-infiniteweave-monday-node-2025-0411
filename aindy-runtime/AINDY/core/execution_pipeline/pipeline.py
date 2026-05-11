from AINDY.core.execution_pipeline.context import ExecutionResult
from AINDY.core.execution_pipeline.resources import (
    _safe_check_quota,
    _safe_finalize_eu,
    _safe_require_eu,
    _safe_rm_mark_completed,
    _safe_rm_mark_started,
    _safe_rm_record_and_complete,
)
from AINDY.core.execution_pipeline.runtime_state import (
    _handle_contract_violation,
    _inject_execution_envelope,
    _record_side_effect,
    _requires_route_side_effects,
    _safe_reset_current_execution_context,
    _safe_reset_parent_event,
    _safe_reset_pipeline_active,
    _safe_set_current_execution_context,
    _safe_set_parent_event,
    _safe_set_pipeline_active,
    _set_event_refs,
)
from AINDY.core.execution_pipeline.shared import (
    Any,
    Callable,
    HTTPException,
    Response,
    _METRICS_AVAILABLE,
    aindy_active_executions_total,
    execution_duration_seconds,
    execution_total,
    inspect,
    logger,
    time,
)
from AINDY.core.execution_pipeline.signals import (
    _apply_event_signals,
    _apply_execution_hints,
    _apply_execution_signals,
    _apply_log_signal,
    _apply_memory_signals,
    _extract_execution_result_and_signals,
    _extract_memory_context_count,
    _merge_queued_signals,
    _safe_capture_memory_hint,
    _safe_recall_memory_count,
)
from AINDY.core.execution_pipeline.waits import _detect_wait, _safe_transition_eu_waiting


class ExecutionPipeline:
    _record_side_effect = _record_side_effect
    _requires_route_side_effects = _requires_route_side_effects
    _safe_set_parent_event = _safe_set_parent_event
    _safe_reset_parent_event = _safe_reset_parent_event
    _set_event_refs = _set_event_refs
    _handle_contract_violation = _handle_contract_violation
    _safe_set_pipeline_active = _safe_set_pipeline_active
    _safe_reset_pipeline_active = _safe_reset_pipeline_active
    _safe_set_current_execution_context = _safe_set_current_execution_context
    _safe_reset_current_execution_context = _safe_reset_current_execution_context
    _inject_execution_envelope = _inject_execution_envelope
    _extract_memory_context_count = _extract_memory_context_count
    _apply_execution_hints = _apply_execution_hints
    _extract_execution_result_and_signals = _extract_execution_result_and_signals
    _apply_execution_signals = _apply_execution_signals
    _merge_queued_signals = _merge_queued_signals
    _apply_memory_signals = _apply_memory_signals
    _apply_event_signals = _apply_event_signals
    _apply_log_signal = _apply_log_signal
    _safe_capture_memory_hint = _safe_capture_memory_hint
    _safe_recall_memory_count = _safe_recall_memory_count
    _detect_wait = _detect_wait
    _safe_transition_eu_waiting = _safe_transition_eu_waiting
    _safe_require_eu = _safe_require_eu
    _safe_check_quota = _safe_check_quota
    _safe_rm_mark_started = _safe_rm_mark_started
    _safe_rm_mark_completed = _safe_rm_mark_completed
    _safe_rm_record_and_complete = _safe_rm_record_and_complete
    _safe_finalize_eu = _safe_finalize_eu

    async def run(self, ctx, handler: Callable[[Any], Any]) -> ExecutionResult:
        from AINDY.core.execution_gate import ExecutionWaitSignal
        from AINDY.core import execution_pipeline as execution_pipeline_module

        trace_id = str(ctx.request_id)
        ctx.metadata.setdefault("trace_id", trace_id)
        required_side_effects = self._requires_route_side_effects(ctx)
        started_event_id: str | None = None
        parent_token: Any = None
        pipeline_token: Any = None
        execution_ctx_token: Any = None
        rm_started = False

        logger.info("execution.entry=PIPELINE", extra={"route": ctx.route_name, "trace_id": trace_id})
        logger.info("pipeline.entry", extra={"route": ctx.route_name})
        metrics_available = execution_pipeline_module._METRICS_AVAILABLE
        active_metric = execution_pipeline_module.aindy_active_executions_total
        duration_metric = execution_pipeline_module.execution_duration_seconds
        total_metric = execution_pipeline_module.execution_total

        if metrics_available:
            try:
                active_metric.inc()
            except Exception:
                pass

        try:
            started_event_id = self._safe_emit_event(
                ctx,
                event_type="execution.started",
                payload={"route_name": ctx.route_name},
                required=required_side_effects,
            )
            parent_token = self._safe_set_parent_event(started_event_id)
            pipeline_token = self._safe_set_pipeline_active()
            execution_ctx_token = self._safe_set_current_execution_context(ctx)
            self._safe_require_eu(ctx)
            if not self._safe_check_quota(ctx, started_event_id):
                return ExecutionResult(
                    success=False,
                    error="Tenant concurrency limit exceeded",
                    metadata={**ctx.metadata, "status_code": 429, "detail": "Too many concurrent executions for this tenant."},
                )
            self._safe_rm_mark_started(ctx)
            rm_started = True
            handler_start = time.monotonic()
            result = handler(ctx)
            if inspect.isawaitable(result):
                result = await result
            if isinstance(result, Response):
                self._handle_contract_violation("ExecutionContract violation: raw Response returned")
            result, signals = self._extract_execution_result_and_signals(result)
            signals = self._merge_queued_signals(ctx, signals)

            wait_signal = self._detect_wait(result)
            if wait_signal is not None:
                wait_for, wait_payload, wait_condition = wait_signal
                self._safe_transition_eu_waiting(ctx, wait_for=wait_for, wait_condition=wait_condition)
                wait_event_id = self._safe_emit_event(
                    ctx,
                    event_type="execution.waiting",
                    parent_event_id=started_event_id,
                    required=required_side_effects,
                    payload={"route_name": ctx.route_name, "wait_for": wait_for, **wait_payload},
                )
                self._set_event_refs(ctx, started_event_id, terminal_event_id=wait_event_id, completed=False)
                ctx.metadata["eu_status"] = "waiting"
                ctx.metadata["eu_wait_for"] = wait_for
                logger.info("execution.waiting", extra={"route": ctx.route_name, "wait_for": wait_for})
                if metrics_available:
                    try:
                        total_metric.labels(route=ctx.route_name, status="waiting").inc()
                    except Exception:
                        pass
                return ExecutionResult(success=True, eu_status="waiting", data=result, metadata=ctx.metadata)

            injected_count = self._apply_execution_signals(ctx, signals)
            memory_context_count = max(
                self._extract_memory_context_count(result),
                injected_count,
                self._safe_recall_memory_count(ctx),
            )
            duration_ms = round((time.monotonic() - handler_start) * 1000, 2)
            self._safe_rm_record_and_complete(ctx, duration_ms)
            rm_started = False
            if metrics_available:
                try:
                    duration_metric.labels(route=ctx.route_name).observe(duration_ms / 1000)
                    total_metric.labels(route=ctx.route_name, status="success").inc()
                except Exception:
                    pass
            result = self._inject_execution_envelope(ctx, result, duration_ms)

            completed_event_id = self._safe_emit_event(
                ctx,
                event_type="execution.completed",
                parent_event_id=started_event_id,
                required=required_side_effects,
                payload={"route_name": ctx.route_name, "success": True},
            )
            self._set_event_refs(ctx, started_event_id, terminal_event_id=completed_event_id, completed=True)
            self._safe_finalize_eu(ctx, "completed")
            logger.info("execution.completed", extra={"route": ctx.route_name, "success": True})
            return ExecutionResult(
                success=True,
                data=result,
                memory_context_count=memory_context_count,
                metadata=ctx.metadata,
            )
        except ExecutionWaitSignal as exc:
            try:
                self._safe_transition_eu_waiting(ctx, wait_for=exc.wait_for, wait_condition=exc.wait_condition)
            except Exception as wait_guard_exc:
                logger.critical(
                    "execution.wait_untrackable eu=%s route=%s wait_for=%s: %s",
                    ctx.metadata.get("eu_id"),
                    ctx.route_name,
                    exc.wait_for,
                    wait_guard_exc,
                )
                guard_fail_event_id = self._safe_emit_event(
                    ctx,
                    event_type="execution.failed",
                    parent_event_id=started_event_id,
                    required=required_side_effects,
                    payload={"route_name": ctx.route_name, "detail": str(wait_guard_exc)},
                )
                self._set_event_refs(ctx, started_event_id, terminal_event_id=guard_fail_event_id, completed=False)
                self._safe_finalize_eu(ctx, "failed")
                return ExecutionResult(
                    success=False,
                    error=str(wait_guard_exc),
                    metadata={**ctx.metadata, "status_code": 500, "detail": str(wait_guard_exc)},
                )

            wait_event_id = self._safe_emit_event(
                ctx,
                event_type="execution.waiting",
                parent_event_id=started_event_id,
                required=required_side_effects,
                payload={"route_name": ctx.route_name, "wait_for": exc.wait_for, "resume_key": exc.resume_key, **exc.payload},
            )
            self._set_event_refs(ctx, started_event_id, terminal_event_id=wait_event_id, completed=False)
            ctx.metadata["eu_status"] = "waiting"
            ctx.metadata["eu_wait_for"] = exc.wait_for
            logger.info("execution.waiting (raised)", extra={"route": ctx.route_name, "wait_for": exc.wait_for})
            if metrics_available:
                try:
                    total_metric.labels(route=ctx.route_name, status="waiting").inc()
                except Exception:
                    pass
            return ExecutionResult(
                success=True,
                eu_status="waiting",
                data={"status": "WAITING", "wait_for": exc.wait_for, "resume_key": exc.resume_key, **exc.payload},
                metadata=ctx.metadata,
            )
        except HTTPException as exc:
            failed_event_id = self._safe_emit_event(
                ctx,
                event_type="execution.failed",
                parent_event_id=started_event_id,
                required=required_side_effects,
                payload={"route_name": ctx.route_name, "status_code": exc.status_code, "detail": exc.detail},
            )
            self._set_event_refs(ctx, started_event_id, terminal_event_id=failed_event_id, completed=False)
            self._safe_finalize_eu(ctx, "failed")
            logger.info("execution.completed", extra={"route": ctx.route_name, "success": False})
            if metrics_available:
                try:
                    total_metric.labels(route=ctx.route_name, status="failed").inc()
                except Exception:
                    pass
            return ExecutionResult(
                success=False,
                error=str(exc.detail),
                metadata={**ctx.metadata, "status_code": exc.status_code, "detail": exc.detail},
            )
        except Exception as exc:
            failed_event_id = self._safe_emit_event(
                ctx,
                event_type="execution.failed",
                parent_event_id=started_event_id,
                required=required_side_effects,
                payload={"route_name": ctx.route_name, "detail": str(exc)},
            )
            self._set_event_refs(ctx, started_event_id, terminal_event_id=failed_event_id, completed=False)
            self._safe_finalize_eu(ctx, "failed")
            logger.exception("execution.failed", extra={"route": ctx.route_name})
            if metrics_available:
                try:
                    total_metric.labels(route=ctx.route_name, status="failed").inc()
                except Exception:
                    pass
            return ExecutionResult(
                success=False,
                error=str(exc),
                metadata={**ctx.metadata, "status_code": 500, "detail": str(exc)},
            )
        finally:
            if metrics_available:
                try:
                    active_metric.dec()
                except Exception:
                    pass
            if rm_started:
                self._safe_rm_mark_completed(ctx)
            self._safe_reset_current_execution_context(execution_ctx_token)
            self._safe_reset_pipeline_active(pipeline_token)
            self._safe_reset_parent_event(parent_token)

    def _safe_emit_event(
        self,
        ctx,
        *,
        event_type: str,
        payload: dict[str, Any] | None = None,
        parent_event_id: str | None = None,
        required: bool = False,
    ) -> str | None:
        side_effect_name = f"system_event.{event_type}"
        db = ctx.metadata.get("db")
        if db is None:
            if required:
                self._record_side_effect(
                    ctx,
                    side_effect_name,
                    status="missing",
                    required=True,
                    error="db session is absent",
                )
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
                required=required,
                skip_memory_capture=bool(ctx.metadata.get("disable_memory_capture")),
            )
            if not event_id:
                self._record_side_effect(
                    ctx,
                    side_effect_name,
                    status="missing",
                    required=required,
                    error="emit_system_event returned no event id",
                )
                return None
            self._record_side_effect(ctx, side_effect_name, status="ok", required=required)
            return str(event_id)
        except Exception as exc:
            self._record_side_effect(
                ctx,
                side_effect_name,
                status="failed",
                required=required,
                error=exc,
            )
            logger.debug("execution.event_emit_skipped", exc_info=True)
            return None
