"""Shared helpers for app-owned agent tools."""

from __future__ import annotations

from AINDY.kernel.syscall_dispatcher import get_dispatcher, make_syscall_ctx_from_tool


def dispatch_tool_syscall(name: str, payload: dict, user_id: str, capability: str) -> dict:
    ctx = make_syscall_ctx_from_tool(user_id, capabilities=[capability])
    result = get_dispatcher().dispatch(name, payload, ctx)
    if result["status"] == "error":
        raise RuntimeError(result["error"])
    return result["data"]
