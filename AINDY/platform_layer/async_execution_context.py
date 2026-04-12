from __future__ import annotations

from contextvars import ContextVar

_ASYNC_EXECUTION_CONTEXT: ContextVar[bool] = ContextVar(
    "_ASYNC_EXECUTION_CONTEXT", default=False
)


def activate_async_execution_context() -> ContextVar.Token[bool]:
    """Mark the current execution as running inside an async job."""
    return _ASYNC_EXECUTION_CONTEXT.set(True)


def deactivate_async_execution_context(token: ContextVar.Token[bool]) -> None:
    """Restore the async execution context token."""
    _ASYNC_EXECUTION_CONTEXT.reset(token)


def is_async_execution_active() -> bool:
    """Return True when the context is currently executing an async job."""
    return _ASYNC_EXECUTION_CONTEXT.get()
