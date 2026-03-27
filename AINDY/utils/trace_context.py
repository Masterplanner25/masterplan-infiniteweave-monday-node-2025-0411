from __future__ import annotations

import uuid
from contextvars import ContextVar, Token


_trace_id_ctx: ContextVar[str] = ContextVar("trace_id", default="-")


def get_current_trace_id(default: str | None = None) -> str | None:
    trace_id = _trace_id_ctx.get()
    if trace_id == "-":
        return default
    return trace_id


def set_current_trace_id(trace_id: str) -> Token:
    return _trace_id_ctx.set(str(trace_id))


def reset_current_trace_id(token: Token) -> None:
    _trace_id_ctx.reset(token)


def ensure_trace_id(trace_id: str | None = None) -> str:
    current = get_current_trace_id()
    if current:
        return current
    generated = str(trace_id or uuid.uuid4())
    _trace_id_ctx.set(generated)
    return generated
