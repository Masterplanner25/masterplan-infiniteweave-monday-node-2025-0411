from __future__ import annotations

from typing import Any

from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from services.execution_envelope import success as legacy_success


def _legacy_error_response(canonical: dict[str, Any], *, status_code: int) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"detail": jsonable_encoder(canonical.get("metadata", {}).get("error", "Execution failed"))},
        headers=_trace_headers(canonical),
    )


def _trace_headers(canonical: dict[str, Any]) -> dict[str, str]:
    trace_id = str(canonical.get("trace_id") or "")
    return {"X-Trace-ID": trace_id} if trace_id else {}


def adapt_response(route_name: str, canonical: dict[str, Any], *, status_code: int = 200) -> Response:
    if canonical.get("status") == "error":
        return _legacy_error_response(canonical, status_code=status_code)

    payload = canonical.get("data")
    if isinstance(payload, Response):
        trace_id = str(canonical.get("trace_id") or "")
        if trace_id:
            payload.headers.setdefault("X-Trace-ID", trace_id)
        return payload

    if route_name.startswith(("auth.", "analytics.", "arm.", "main.", "memory.")):
        return JSONResponse(
            status_code=status_code,
            content=jsonable_encoder(payload),
            headers=_trace_headers(canonical),
        )

    if route_name.startswith(("watcher.", "social.", "autonomy.", "system.", "coordination.")):
        if isinstance(payload, dict) and "status" in payload and "trace_id" in payload:
            return JSONResponse(
                status_code=status_code,
                content=jsonable_encoder(payload),
                headers=_trace_headers(canonical),
            )
        body = legacy_success(
            payload,
            canonical.get("metadata", {}).get("events") or [],
            str(canonical.get("trace_id") or ""),
            next_action=canonical.get("metadata", {}).get("next_action"),
        )
        return JSONResponse(
            status_code=status_code,
            content=jsonable_encoder(body),
            headers=_trace_headers(canonical),
        )

    return JSONResponse(
        status_code=status_code,
        content=jsonable_encoder(canonical),
        headers=_trace_headers(canonical),
    )
