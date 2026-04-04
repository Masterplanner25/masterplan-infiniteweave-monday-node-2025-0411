from __future__ import annotations

import time
from typing import Any, Callable

from core.execution_signal_helper import queue_system_event
from core.system_event_service import emit_error_event
from utils.trace_context import get_current_trace_id


def external_metadata(
    *,
    service_name: str,
    endpoint: str | None = None,
    model: str | None = None,
    method: str | None = None,
    status: str | None = None,
    latency_ms: float | None = None,
    error: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "service_name": service_name,
        "endpoint": endpoint,
        "model": model,
        "method": method,
        "status": status,
        "latency_ms": latency_ms,
        "error": error,
    }
    if extra:
        payload.update(extra)
    return payload


def perform_external_call(
    *,
    service_name: str,
    operation: Callable[[], Any],
    db=None,
    user_id=None,
    endpoint: str | None = None,
    model: str | None = None,
    method: str | None = None,
    extra: dict[str, Any] | None = None,
):
    from db.database import SessionLocal

    owned_db = db is None
    active_db = db or SessionLocal()
    trace_id = get_current_trace_id()
    started_payload = external_metadata(
        service_name=service_name,
        endpoint=endpoint,
        model=model,
        method=method,
        status="started",
        extra=extra,
    )
    queue_system_event(
        db=active_db,
        event_type="external.call.started",
        user_id=user_id,
        trace_id=trace_id,
        payload=started_payload,
        required=True,
    )

    started_at = time.perf_counter()
    try:
        result = operation()
        latency_ms = round((time.perf_counter() - started_at) * 1000, 2)
        completed_payload = external_metadata(
            service_name=service_name,
            endpoint=endpoint,
            model=model,
            method=method,
            status="success",
            latency_ms=latency_ms,
            extra=extra,
        )
        queue_system_event(
            db=active_db,
            event_type="external.call.completed",
            user_id=user_id,
            trace_id=trace_id,
            payload=completed_payload,
            required=True,
        )
        return result
    except Exception as exc:
        latency_ms = round((time.perf_counter() - started_at) * 1000, 2)
        failed_payload = external_metadata(
            service_name=service_name,
            endpoint=endpoint,
            model=model,
            method=method,
            status="failure",
            latency_ms=latency_ms,
            error=str(exc),
            extra=extra,
        )
        queue_system_event(
            db=active_db,
            event_type="external.call.failed",
            user_id=user_id,
            trace_id=trace_id,
            payload=failed_payload,
            required=True,
        )
        emit_error_event(
            db=active_db,
            error_type="external_call",
            message=str(exc),
            user_id=user_id,
            trace_id=trace_id,
            payload=failed_payload,
            required=True,
        )
        raise
    finally:
        if owned_db:
            active_db.close()

