from __future__ import annotations

from typing import Any


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
