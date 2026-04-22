from AINDY.core.execution_pipeline.shared import Any, logger


def _requires_route_side_effects(self, ctx) -> bool:
    return ctx.metadata.get("db") is not None


def _record_side_effect(self, ctx, name: str, *, status: str, required: bool, error: Any = None) -> None:
    detail: dict[str, Any] = {"status": status, "required": bool(required)}
    if error is not None:
        detail["error"] = str(error)
    ctx.metadata.setdefault("side_effects", {})[name] = detail


def _safe_set_parent_event(self, parent_event_id: str | None) -> Any:
    if not parent_event_id:
        return None
    try:
        from AINDY.platform_layer.trace_context import set_parent_event_id

        return set_parent_event_id(parent_event_id)
    except Exception:
        logger.debug("execution.parent_event_set_skipped", exc_info=True)
        return None


def _safe_reset_parent_event(self, token: Any) -> None:
    if token is None:
        return
    try:
        from AINDY.platform_layer.trace_context import reset_parent_event_id

        reset_parent_event_id(token)
    except Exception:
        logger.debug("execution.parent_event_reset_skipped", exc_info=True)


def _set_event_refs(self, ctx, started_event_id: str | None, *, terminal_event_id: str | None, completed: bool) -> None:
    refs: list[dict[str, str]] = []
    if started_event_id:
        refs.append({"type": "execution.started", "id": str(started_event_id)})
    terminal_type = "execution.completed" if completed else "execution.failed"
    if terminal_event_id:
        refs.append({"type": terminal_type, "id": str(terminal_event_id)})
    ctx.metadata["event_refs"] = refs


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
        from AINDY.platform_layer.trace_context import set_pipeline_active

        return set_pipeline_active(True)
    except Exception:
        logger.debug("execution.pipeline_active_set_skipped", exc_info=True)
        return None


def _safe_reset_pipeline_active(self, token: Any) -> None:
    if token is None:
        return
    try:
        from AINDY.platform_layer.trace_context import reset_pipeline_active

        reset_pipeline_active(token)
    except Exception:
        logger.debug("execution.pipeline_active_reset_skipped", exc_info=True)


def _safe_set_current_execution_context(self, ctx) -> Any:
    try:
        from AINDY.platform_layer.trace_context import set_current_execution_context

        return set_current_execution_context(ctx)
    except Exception:
        logger.debug("execution.current_ctx_set_skipped", exc_info=True)
        return None


def _safe_reset_current_execution_context(self, token: Any) -> None:
    if token is None:
        return
    try:
        from AINDY.platform_layer.trace_context import reset_current_execution_context

        reset_current_execution_context(token)
    except Exception:
        logger.debug("execution.current_ctx_reset_skipped", exc_info=True)


def _inject_execution_envelope(self, ctx, result, duration_ms: float):
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
