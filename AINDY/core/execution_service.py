from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from fastapi import HTTPException
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

from AINDY.core.execution_helper import execute_with_pipeline_sync
from AINDY.core.execution_envelope import adapt_pipeline_result


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


def _raise_mapped_exception(
    exc: Exception,
    handled_exceptions: dict[type[Exception], ExecutionErrorConfig] | None,
) -> None:
    if handled_exceptions:
        for exc_type, config in handled_exceptions.items():
            if isinstance(exc, exc_type):
                raise HTTPException(
                    status_code=config.status_code,
                    detail={"message": config.message, "details": str(exc)},
                ) from exc
    raise exc


def run_execution(
    context: ExecutionContext,
    fn: Callable[[], Any],
    *,
    success_status_code: int = 200,
    handled_exceptions: dict[type[Exception], ExecutionErrorConfig] | None = None,
    completed_payload_builder: Callable[[Any], dict[str, Any] | None] | None = None,
    next_action_builder: Callable[[Any], Any] | None = None,
) -> dict[str, Any] | JSONResponse | Response:
    compatibility: dict[str, Any] = {"next_action": None}

    def handler(_ctx: Any) -> Any:
        try:
            result = fn()
        except Exception as exc:
            _raise_mapped_exception(exc, handled_exceptions)

        if completed_payload_builder:
            completed_payload_builder(result)
        if next_action_builder:
            compatibility["next_action"] = next_action_builder(result)
        return result

    pipeline_result = execute_with_pipeline_sync(
        request=None,
        route_name=context.operation,
        handler=handler,
        user_id=context.user_id,
        input_payload=context.start_payload,
        metadata={
            "db": context.db,
            "trace_id": context.trace_id,
            "source": context.source,
            "status_code": success_status_code,
        },
        success_status_code=success_status_code,
        return_result=True,
    )
    return adapt_pipeline_result(pipeline_result, next_action=compatibility["next_action"])

