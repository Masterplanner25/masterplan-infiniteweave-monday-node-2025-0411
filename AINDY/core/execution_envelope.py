from __future__ import annotations

from typing import Any

from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response


def success(
    result: Any,
    events: list[Any] | None,
    trace_id: str,
    next_action: Any = None,
) -> dict[str, Any]:
    return {
        "status": "SUCCESS",
        "data": result,
        "result": result,
        "events": events or [],
        "next_action": next_action,
        "trace_id": str(trace_id),
    }


def error(message: str, events: list[Any] | None, trace_id: str) -> dict[str, Any]:
    payload = {"message": message}
    return {
        "status": "ERROR",
        "data": payload,
        "result": payload,
        "events": events or [],
        "next_action": None,
        "trace_id": str(trace_id),
    }


def unified(
    *,
    eu_id: str | None,
    trace_id: str | None,
    status: str,
    output: Any,
    error: str | None,
    duration_ms: Any = None,
    attempt_count: Any = None,
) -> dict[str, Any]:
    """
    Canonical ExecutionEnvelope used by the unification layer (execution_gate.py).

    This is the single, stable shape that all execution paths must produce.
    Existing ``success()`` / ``error()`` helpers are preserved for backward
    compatibility with current route handlers — new code should use this.
    """
    return {
        "eu_id": eu_id,
        "trace_id": str(trace_id) if trace_id else None,
        "status": status,
        "output": output,
        "error": error,
        "duration_ms": duration_ms,
        "attempt_count": attempt_count,
    }


def adapt_pipeline_result(result: Any, *, next_action: Any = None) -> dict[str, Any] | JSONResponse | Response:
    metadata: dict[str, Any] = getattr(result, "metadata", {}) or {}
    trace_id = str(metadata.get("trace_id") or "")
    eu_id: str | None = metadata.get("eu_id") or None
    status_code = int(
        metadata.get(
            "status_code",
            200 if getattr(result, "success", False) else 500,
        )
    )
    event_refs = list(metadata.get("event_refs") or [])

    data = getattr(result, "data", None)
    if isinstance(data, Response):
        if trace_id:
            data.headers.setdefault("X-Trace-ID", trace_id)
        if eu_id:
            data.headers.setdefault("X-EU-ID", eu_id)
        return data

    if getattr(result, "success", False):
        if isinstance(data, dict) and "status" in data and "trace_id" in data:
            body = dict(data)
            body["trace_id"] = body.get("trace_id") or trace_id
            body.setdefault("eu_id", eu_id)
            body["events"] = [*body.get("events", []), *event_refs]
            if "data" not in body and "result" in body:
                body["data"] = body["result"]
            if "result" not in body and "data" in body:
                body["result"] = body["data"]
            if body.get("next_action") is None:
                body["next_action"] = next_action
        else:
            body = success(data, event_refs, trace_id, next_action=next_action)
            body.setdefault("eu_id", eu_id)
        if status_code == 200:
            return body
        return JSONResponse(status_code=status_code, content=jsonable_encoder(body))

    detail = getattr(result, "metadata", {}).get("detail")
    message = getattr(result, "error", None) or "Execution failed"
    if isinstance(detail, dict):
        payload = dict(jsonable_encoder(detail))
        payload.setdefault("message", message)
    else:
        payload = {"message": message}
        if detail not in (None, message):
            payload["details"] = jsonable_encoder(detail)

    body = error(payload["message"], event_refs, trace_id)
    body["data"] = payload
    body["result"] = payload
    return JSONResponse(status_code=status_code, content=jsonable_encoder(body))

