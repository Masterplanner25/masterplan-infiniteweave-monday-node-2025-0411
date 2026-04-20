"""Shared response adapter functions for domain bootstraps.

All imports are deferred to the call site to avoid module-load side-effects.
"""
from __future__ import annotations


def raw_json_adapter(*, route_name, canonical, status_code, trace_headers):
    from fastapi.encoders import jsonable_encoder
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=status_code,
        content=jsonable_encoder(canonical.get("data")),
        headers=trace_headers,
    )


def legacy_envelope_adapter(*, route_name, canonical, status_code, trace_headers):
    from fastapi.encoders import jsonable_encoder
    from fastapi.responses import JSONResponse
    from AINDY.core.execution_envelope import success as legacy_success

    payload = canonical.get("data")
    if isinstance(payload, dict) and "status" in payload and "trace_id" in payload:
        body = payload
    else:
        body = legacy_success(
            payload,
            canonical.get("metadata", {}).get("events") or [],
            str(canonical.get("trace_id") or ""),
            next_action=canonical.get("metadata", {}).get("next_action"),
        )
    return JSONResponse(
        status_code=status_code,
        content=jsonable_encoder(body),
        headers=trace_headers,
    )


def raw_canonical_adapter(*, route_name, canonical, status_code, trace_headers):
    from fastapi.encoders import jsonable_encoder
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=status_code,
        content=jsonable_encoder(canonical),
        headers=trace_headers,
    )


def memory_execute_adapter(*, route_name, canonical, status_code, trace_headers):
    payload = canonical.get("data")
    if not isinstance(payload, dict):
        return raw_canonical_adapter(
            route_name=route_name,
            canonical=canonical,
            status_code=status_code,
            trace_headers=trace_headers,
        )
    from fastapi.encoders import jsonable_encoder
    from fastapi.responses import JSONResponse

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
        headers=trace_headers,
    )


def memory_completion_adapter(*, route_name, canonical, status_code, trace_headers):
    if canonical.get("status") == "error":
        from fastapi.encoders import jsonable_encoder
        from fastapi.responses import JSONResponse

        error_status = canonical.get("metadata", {}).get("status_code") or status_code
        detail = canonical.get("metadata", {}).get("error", "Execution failed")
        return JSONResponse(
            status_code=int(error_status),
            content={"error": "http_error", "details": jsonable_encoder(detail)},
            headers=trace_headers,
        )
    return raw_canonical_adapter(
        route_name=route_name,
        canonical=canonical,
        status_code=status_code,
        trace_headers=trace_headers,
    )
