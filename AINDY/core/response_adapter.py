from __future__ import annotations

from typing import Any

from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from AINDY.core.execution_envelope import success as legacy_success


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
    if canonical.get("status") == "error":
        if route_name == "memory.execute.complete":
            error_status = canonical.get("metadata", {}).get("status_code") or status_code
            detail = canonical.get("metadata", {}).get("error", "Execution failed")
            return JSONResponse(
                status_code=int(error_status),
                content={"error": "http_error", "details": jsonable_encoder(detail)},
                headers=_trace_headers(canonical),
            )
        return _legacy_error_response(canonical, status_code=status_code)

    payload = canonical.get("data")
    if isinstance(payload, Response):
        trace_id = str(canonical.get("trace_id") or "")
        if trace_id:
            payload.headers.setdefault("X-Trace-ID", trace_id)
        return payload

    if route_name.startswith("memory.") and not route_name.startswith((
        "memory.execute",
        "memory.nodus.execute",
    )):
        return JSONResponse(
            status_code=status_code,
            content=jsonable_encoder(payload),
            headers=_trace_headers(canonical),
        )

    if route_name == "memory.execute" and isinstance(payload, dict):
        merged = dict(payload)
        merged["status"] = canonical.get("status")
        merged["trace_id"] = canonical.get("trace_id")
        merged["data"] = payload
        metadata = canonical.get("metadata", {})
        if metadata.get("events") is not None:
            merged["events"] = metadata.get("events")
        if metadata.get("next_action") is not None:
            merged["next_action"] = metadata.get("next_action")
        return JSONResponse(
            status_code=status_code,
            content=jsonable_encoder(merged),
            headers=_trace_headers(canonical),
        )

    if route_name.startswith((
        "auth.", "analytics.", "arm.", "automation.", "main.",
        "authorship.", "bridge.", "db.",
        "flow.", "health.", "leadgen.", "masterplan.", "network_bridge.",
        "observability.", "rippletrace.", "score.", "seo.",
        "legacy_surface.", "watcher.",
    )) or route_name.startswith("scores"):
        return JSONResponse(
            status_code=status_code,
            content=jsonable_encoder(payload),
            headers=_trace_headers(canonical),
        )

    if route_name.startswith(("social.", "autonomy.", "system.", "coordination.")):
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

