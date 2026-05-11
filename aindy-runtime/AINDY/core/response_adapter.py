from __future__ import annotations

from typing import Any

from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from AINDY.platform_layer.registry import get_response_adapter


def _legacy_error_response(canonical: dict[str, Any], *, status_code: int) -> JSONResponse:
    error_status = canonical.get("metadata", {}).get("status_code") or status_code
    return JSONResponse(
        status_code=int(error_status),
        content={"detail": jsonable_encoder(canonical.get("metadata", {}).get("error", "Execution failed"))},
        headers=_trace_headers(canonical),
    )


def _trace_headers(canonical: dict[str, Any]) -> dict[str, str]:
    headers: dict[str, str] = {}
    trace_id = str(canonical.get("trace_id") or "")
    if trace_id:
        headers["X-Trace-ID"] = trace_id
    eu_id = str(canonical.get("eu_id") or "")
    if eu_id:
        headers["X-EU-ID"] = eu_id
    return headers


def adapt_response(route_name: str, canonical: dict[str, Any], *, status_code: int = 200) -> Response:
    route_prefix = route_name.split(".", 1)[0]
    underscore_prefix = route_name.split("_", 1)[0]
    exact_adapter = get_response_adapter(route_name)

    if exact_adapter is not None:
        return exact_adapter(
            route_name=route_name,
            canonical=canonical,
            status_code=status_code,
            trace_headers=_trace_headers(canonical),
        )

    if canonical.get("status") == "error":
        return _legacy_error_response(canonical, status_code=status_code)

    payload = canonical.get("data")
    if isinstance(payload, Response):
        trace_id = str(canonical.get("trace_id") or "")
        if trace_id:
            payload.headers.setdefault("X-Trace-ID", trace_id)
        return payload

    adapter = (
        get_response_adapter(route_prefix)
        or get_response_adapter(underscore_prefix)
    )
    if adapter is not None:
        return adapter(
            route_name=route_name,
            canonical=canonical,
            status_code=status_code,
            trace_headers=_trace_headers(canonical),
        )

    return JSONResponse(
        status_code=status_code,
        content=jsonable_encoder(canonical),
        headers=_trace_headers(canonical),
    )

