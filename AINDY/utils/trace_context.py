from __future__ import annotations

from services.trace_context import _trace_id_ctx
from services.trace_context import ensure_trace_id
from services.trace_context import get_trace_id
from services.trace_context import reset_trace_id
from services.trace_context import set_trace_id
from services.trace_context import reset_current_request as _reset_current_request
from services.trace_context import get_current_request as _get_current_request
from services.trace_context import set_current_request as _set_current_request


def get_current_trace_id(default: str | None = None) -> str | None:
    return get_trace_id(default=default)


def set_current_trace_id(trace_id: str):
    return set_trace_id(trace_id)


def set_current_request(request: Any) -> Any:
    return _set_current_request(request)


def reset_current_trace_id(token) -> None:
    reset_trace_id(token)


def get_current_request(default: Any | None = None) -> Any | None:
    return _get_current_request(default=default)


def reset_current_request(token) -> None:
    _reset_current_request(token)
