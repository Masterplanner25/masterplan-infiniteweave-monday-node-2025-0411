from __future__ import annotations

import uuid
from contextvars import ContextVar, Token
from typing import Any


_trace_id_ctx: ContextVar[str] = ContextVar("trace_id", default="-")
_parent_event_id_ctx: ContextVar[str] = ContextVar("parent_event_id", default="-")
_pipeline_active_ctx: ContextVar[bool] = ContextVar("pipeline_active", default=False)
_current_request_ctx: ContextVar[Any] = ContextVar("current_request", default=None)


def get_trace_id(default: str | None = None) -> str | None:
    trace_id = _trace_id_ctx.get()
    if trace_id == "-":
        return default
    return trace_id


def set_trace_id(trace_id: str) -> Token:
    return _trace_id_ctx.set(str(trace_id))


def reset_trace_id(token: Token) -> None:
    _trace_id_ctx.reset(token)


def ensure_trace_id(trace_id: str | None = None) -> str:
    current = get_trace_id()
    if current:
        return current
    generated = str(trace_id or uuid.uuid4())
    _trace_id_ctx.set(generated)
    return generated


def get_parent_event_id(default: str | None = None) -> str | None:
    parent_event_id = _parent_event_id_ctx.get()
    if parent_event_id == "-":
        return default
    return parent_event_id


def set_parent_event_id(parent_event_id: str | None) -> Token:
    return _parent_event_id_ctx.set("-" if not parent_event_id else str(parent_event_id))


def reset_parent_event_id(token: Token) -> None:
    _parent_event_id_ctx.reset(token)


def is_pipeline_active() -> bool:
    return bool(_pipeline_active_ctx.get())


def set_pipeline_active(active: bool = True) -> Token:
    return _pipeline_active_ctx.set(bool(active))


def reset_pipeline_active(token: Token) -> None:
    _pipeline_active_ctx.reset(token)


def get_current_request(default: Any = None) -> Any:
    current = _current_request_ctx.get()
    if current is None:
        return default
    return current


def set_current_request(request: Any) -> Token:
    return _current_request_ctx.set(request)


def reset_current_request(token: Token) -> None:
    _current_request_ctx.reset(token)
