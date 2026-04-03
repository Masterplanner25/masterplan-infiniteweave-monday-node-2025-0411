from __future__ import annotations

import uuid
from typing import Any

from services.trace_context import get_current_execution_context, is_pipeline_active


def _ensure_signal_bucket(ctx: Any) -> dict[str, list[dict[str, Any]]]:
    queued = ctx.metadata.setdefault("queued_execution_signals", {})
    queued.setdefault("events", [])
    queued.setdefault("memory", [])
    return queued


def queue_system_event(
    *,
    db,
    event_type: str,
    user_id=None,
    trace_id: str | None = None,
    parent_event_id=None,
    source: str | None = None,
    agent_id=None,
    payload: dict[str, Any] | None = None,
    required: bool = False,
):
    ctx = get_current_execution_context()
    if is_pipeline_active() and ctx is not None:
        provisional_id = str(uuid.uuid4())
        queued = _ensure_signal_bucket(ctx)
        queued["events"].append(
            {
                "id": provisional_id,
                "type": event_type,
                "event_type": event_type,
                "payload": dict(payload or {}),
                "parent_event_id": str(parent_event_id) if parent_event_id else None,
                "source": source,
                "agent_id": str(agent_id) if agent_id else None,
                "required": required,
                "trace_id": str(trace_id) if trace_id else None,
                "user_id": str(user_id) if user_id else None,
            }
        )
        return provisional_id

    from services.system_event_service import emit_system_event

    return emit_system_event(
        db=db,
        event_type=event_type,
        user_id=user_id,
        trace_id=trace_id,
        parent_event_id=parent_event_id,
        source=source,
        agent_id=agent_id,
        payload=payload,
        required=required,
    )


def queue_memory_capture(
    *,
    db,
    user_id,
    agent_namespace: str,
    event_type: str,
    content: str,
    source: str,
    tags: list[str] | None = None,
    node_type: str | None = None,
    context: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
    force: bool = False,
    allow_when_pipeline_active: bool = False,
):
    ctx = get_current_execution_context()
    if is_pipeline_active() and ctx is not None and not allow_when_pipeline_active:
        queued = _ensure_signal_bucket(ctx)
        queued["memory"].append(
            {
                "event_type": event_type,
                "content": content,
                "source": source,
                "tags": list(tags or []),
                "node_type": node_type,
                "extra": dict(extra or {}),
                "force": force,
                "user_id": str(user_id) if user_id else None,
                "agent_namespace": agent_namespace,
                "context": dict(context or {}),
            }
        )
        return {
            "queued": True,
            "event_type": event_type,
            "content": content,
            "source": source,
        }

    from memory.memory_capture_engine import MemoryCaptureEngine

    engine = MemoryCaptureEngine(
        db=db,
        user_id=str(user_id) if user_id else None,
        agent_namespace=agent_namespace,
    )
    return engine.evaluate_and_capture(
        event_type=event_type,
        content=content,
        source=source,
        tags=tags,
        node_type=node_type,
        context=context,
        extra=extra,
        force=force,
        allow_when_pipeline_active=True,
    )


def record_agent_event(*args, **kwargs):
    from services.agent_event_service import emit_event

    return emit_event(*args, **kwargs)
