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


def adapt_pipeline_result(result: Any, *, next_action: Any = None) -> dict[str, Any] | JSONResponse | Response:
    trace_id = str(getattr(result, "metadata", {}).get("trace_id") or "")
    status_code = int(
        getattr(result, "metadata", {}).get(
            "status_code",
            200 if getattr(result, "success", False) else 500,
        )
    )
    event_refs = list(getattr(result, "metadata", {}).get("event_refs") or [])

    data = getattr(result, "data", None)
    if isinstance(data, Response):
        if trace_id:
            data.headers.setdefault("X-Trace-ID", trace_id)
        return data

    if getattr(result, "success", False):
        if isinstance(data, dict) and "status" in data and "trace_id" in data:
            body = dict(data)
            body["trace_id"] = body.get("trace_id") or trace_id
            body["events"] = [*body.get("events", []), *event_refs]
            if "data" not in body and "result" in body:
                body["data"] = body["result"]
            if "result" not in body and "data" in body:
                body["result"] = body["data"]
            if body.get("next_action") is None:
                body["next_action"] = next_action
        else:
            body = success(data, event_refs, trace_id, next_action=next_action)
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

