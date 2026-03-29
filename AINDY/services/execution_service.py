from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from services.execution_envelope import error, success
from services.system_event_service import emit_system_event
from services.system_event_types import SystemEventTypes
from services.trace_context import ensure_trace_id, reset_parent_event_id, set_parent_event_id


@dataclass(slots=True)
class ExecutionErrorConfig:
    status_code: int
    message: str


@dataclass(slots=True)
class ExecutionContext:
    db: Session
    user_id: str | None
    source: str
    operation: str
    trace_id: str | None = None
    start_payload: dict[str, Any] = field(default_factory=dict)


def _event_refs(*items: tuple[str, object | None]) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    for event_type, event_id in items:
        if event_id:
            refs.append({"type": event_type, "id": str(event_id)})
    return refs


def _success_response(
    *,
    trace_id: str,
    result: Any,
    started_event_id: object | None,
    completed_event_id: object | None,
    next_action: Any = None,
    status_code: int = 200,
) -> dict[str, Any] | JSONResponse:
    body = success(
        result=result,
        events=_event_refs(
            (SystemEventTypes.EXECUTION_STARTED, started_event_id),
            (SystemEventTypes.EXECUTION_COMPLETED, completed_event_id),
        ),
        trace_id=trace_id,
        next_action=next_action,
    )
    if status_code == 200:
        return body
    return JSONResponse(status_code=status_code, content=body)


def _error_response(
    *,
    context: ExecutionContext,
    trace_id: str,
    started_event_id: object | None,
    status_code: int,
    message: str,
    details: str | None = None,
) -> JSONResponse:
    failed_event_id = emit_system_event(
        db=context.db,
        event_type=SystemEventTypes.EXECUTION_FAILED,
        user_id=context.user_id,
        trace_id=trace_id,
        parent_event_id=started_event_id,
        source=context.source,
        payload={
            "operation": context.operation,
            "message": message,
            "details": details,
        },
        required=False,
    )
    body = error(
        message,
        _event_refs(
            (SystemEventTypes.EXECUTION_STARTED, started_event_id),
            (SystemEventTypes.EXECUTION_FAILED, failed_event_id),
        ),
        trace_id,
    )
    if details:
        body["data"]["details"] = details
        body["result"]["details"] = details
    return JSONResponse(status_code=status_code, content=body)


def run_execution(
    context: ExecutionContext,
    fn: Callable[[], Any],
    *,
    success_status_code: int = 200,
    handled_exceptions: dict[type[Exception], ExecutionErrorConfig] | None = None,
    completed_payload_builder: Callable[[Any], dict[str, Any] | None] | None = None,
    next_action_builder: Callable[[Any], Any] | None = None,
) -> dict[str, Any] | JSONResponse:
    trace_id = ensure_trace_id(context.trace_id)
    started_event_id = emit_system_event(
        db=context.db,
        event_type=SystemEventTypes.EXECUTION_STARTED,
        user_id=context.user_id,
        trace_id=trace_id,
        source=context.source,
        payload={"operation": context.operation, **(context.start_payload or {})},
        required=True,
    )
    parent_token = set_parent_event_id(str(started_event_id) if started_event_id else None)
    try:
        result = fn()
        completed_payload = {"operation": context.operation}
        if completed_payload_builder:
            completed_payload.update(completed_payload_builder(result) or {})
        completed_event_id = emit_system_event(
            db=context.db,
            event_type=SystemEventTypes.EXECUTION_COMPLETED,
            user_id=context.user_id,
            trace_id=trace_id,
            parent_event_id=started_event_id,
            source=context.source,
            payload=completed_payload,
            required=True,
        )
        next_action = next_action_builder(result) if next_action_builder else None
        return _success_response(
            trace_id=trace_id,
            result=result,
            started_event_id=started_event_id,
            completed_event_id=completed_event_id,
            next_action=next_action,
            status_code=success_status_code,
        )
    except Exception as exc:
        if handled_exceptions:
            for exc_type, config in handled_exceptions.items():
                if isinstance(exc, exc_type):
                    return _error_response(
                        context=context,
                        trace_id=trace_id,
                        started_event_id=started_event_id,
                        status_code=config.status_code,
                        message=config.message,
                        details=str(exc),
                    )
        return _error_response(
            context=context,
            trace_id=trace_id,
            started_event_id=started_event_id,
            status_code=500,
            message=f"{context.operation} failed",
            details=str(exc),
        )
    finally:
        reset_parent_event_id(parent_token)
