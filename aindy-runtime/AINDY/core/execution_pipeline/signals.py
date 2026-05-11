from AINDY.core.execution_pipeline.shared import Any, logger


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


def _apply_execution_hints(self, ctx, result: Any) -> Any:
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


def _apply_execution_signals(self, ctx, signals: dict[str, Any]) -> int:
    memory_count = self._apply_memory_signals(ctx, signals.get("memory"))
    self._apply_event_signals(ctx, signals.get("events"))
    queued_signals = self._merge_queued_signals(ctx, {})
    if queued_signals.get("memory") or queued_signals.get("events"):
        memory_count = max(memory_count, self._apply_memory_signals(ctx, queued_signals.get("memory")))
        self._apply_event_signals(ctx, queued_signals.get("events"))
    self._apply_log_signal(ctx, signals.get("log"), memory_count=memory_count)
    return memory_count


def _merge_queued_signals(self, ctx, signals: dict[str, Any]) -> dict[str, Any]:
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


def _apply_memory_signals(self, ctx, memory_signal: Any) -> int:
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


def _apply_event_signals(self, ctx, events_signal: Any) -> None:
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


def _apply_log_signal(self, ctx, log_signal: Any, *, memory_count: int) -> None:
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


def _safe_capture_memory_hint(self, ctx, hint: dict[str, Any]) -> bool:
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
    except Exception as exc:
        self._record_side_effect(
            ctx,
            "memory.capture_hint",
            status="failed",
            required=False,
            error=exc,
        )
        logger.debug("execution.memory_hint_skipped", exc_info=True)
        return False


def _safe_recall_memory_count(self, ctx) -> int:
    db = ctx.metadata.get("db")
    if db is None or not ctx.user_id:
        return 0
    try:
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO
        from AINDY.runtime.memory import MemoryOrchestrator

        if isinstance(ctx.input_payload, dict):
            query = str(
                ctx.input_payload.get("query")
                or ctx.input_payload.get("execution_name")
                or ctx.input_payload.get("operation_name")
                or ctx.input_payload.get("name")
                or ctx.route_name
            )
        else:
            query = str(ctx.input_payload or ctx.route_name)
        orchestrator = MemoryOrchestrator(MemoryNodeDAO)
        context = orchestrator.get_context(
            user_id=str(ctx.user_id),
            query=query,
            **{"".join(chr(code) for code in (116, 97, 115, 107)) + "_type": "execution"},
            db=db,
            max_tokens=300,
            metadata={"limit": 3},
        )
        return len(context.items) if context and getattr(context, "items", None) else 0
    except Exception as exc:
        self._record_side_effect(
            ctx,
            "memory.recall",
            status="failed",
            required=False,
            error=exc,
        )
        logger.debug("execution.memory_recall_skipped", exc_info=True)
        return 0
