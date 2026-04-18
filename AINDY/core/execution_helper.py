from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from fastapi import Request

from AINDY.core.execution_pipeline import ExecutionContext, ExecutionPipeline
from AINDY.core.response_adapter import adapt_response
from AINDY.platform_layer.trace_context import get_current_request

logger = logging.getLogger(__name__)


async def execute_with_pipeline(
    request: Request | None,
    route_name: str,
    handler: Callable[[ExecutionContext], Any],
    *,
    user_id: str | None = None,
    input_payload: Any = None,
    metadata: dict[str, Any] | None = None,
    success_status_code: int = 200,
    return_result: bool = False,
):
    active_request = request or get_current_request()
    ctx = ExecutionContext.from_request(active_request, route_name)
    trace_id = (metadata or {}).get("trace_id")
    if trace_id:
        ctx.request_id = str(trace_id)
    ctx.user_id = user_id
    if input_payload is not None:
        ctx.input_payload = input_payload
    ctx.metadata.update(metadata or {})
    ctx.metadata["status_code"] = success_status_code
    if active_request is not None:
        active_request.state.execution_context = ctx
    pipeline = ExecutionPipeline()
    result = await pipeline.run(ctx, handler)
    if return_result:
        return result
    canonical = result.to_response()
    logger.info(
        "response.normalized",
        extra={"route": route_name, "status": canonical.get("status")},
    )
    return adapt_response(route_name, canonical, status_code=success_status_code)


def execute_with_pipeline_sync(
    request: Request | None,
    route_name: str,
    handler: Callable[[ExecutionContext], Any],
    *,
    user_id: str | None = None,
    input_payload: Any = None,
    metadata: dict[str, Any] | None = None,
    success_status_code: int = 200,
    return_result: bool = False,
):
    return asyncio.run(
        execute_with_pipeline(
            request=request,
            route_name=route_name,
            handler=handler,
            user_id=user_id,
            input_payload=input_payload,
            metadata=metadata,
            success_status_code=success_status_code,
            return_result=return_result,
        )
    )

