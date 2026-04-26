"""Agent-owned syscall handlers."""

from __future__ import annotations

from AINDY.kernel.syscall_registry import SyscallContext


def handle_agent_dispatch_tool(payload: dict, context: SyscallContext) -> dict:
    from apps.agent.agents.tool_helpers import dispatch_tool_syscall

    tool_name = payload.get("tool_name")
    user_id = payload.get("user_id")
    syscall_name = payload.get("syscall_name")
    inner_payload = payload.get("payload")
    capability = payload.get("capability") or tool_name

    if not tool_name:
        raise ValueError("sys.v1.agent.dispatch_tool requires 'tool_name'")
    if not user_id:
        raise ValueError("sys.v1.agent.dispatch_tool requires 'user_id'")
    if not syscall_name:
        raise ValueError("sys.v1.agent.dispatch_tool requires 'syscall_name'")
    if inner_payload is None:
        inner_payload = {}
    if not isinstance(inner_payload, dict):
        raise ValueError("sys.v1.agent.dispatch_tool requires 'payload' to be a dict")

    return dispatch_tool_syscall(syscall_name, inner_payload, user_id, capability)
