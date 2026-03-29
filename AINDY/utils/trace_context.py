from __future__ import annotations

from services.trace_context import _trace_id_ctx
from services.trace_context import ensure_trace_id
from services.trace_context import get_trace_id
from services.trace_context import reset_trace_id
from services.trace_context import set_trace_id


def get_current_trace_id(default: str | None = None) -> str | None:
    return get_trace_id(default=default)


def set_current_trace_id(trace_id: str):
    return set_trace_id(trace_id)


def reset_current_trace_id(token) -> None:
    reset_trace_id(token)
