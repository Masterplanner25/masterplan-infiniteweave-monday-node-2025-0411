"""Runtime-owned helpers for tool syscall invocation."""

from __future__ import annotations

from typing import Any

from AINDY.kernel.syscall_dispatcher import dispatch_syscall


def invoke_tool_syscall(
    syscall_name: str,
    payload: dict[str, Any],
    *,
    user_id: str,
    capability: str,
    db=None,
) -> dict[str, Any]:
    """Dispatch a tool to its explicit syscall boundary and unwrap the result."""
    result = dispatch_syscall(
        syscall_name,
        dict(payload or {}),
        db=db,
        user_id=user_id,
        capability=capability,
    )
    if result.get("status") != "success":
        raise RuntimeError(result.get("error") or f"{syscall_name} failed")
    data = result.get("data")
    return data if isinstance(data, dict) else {}
