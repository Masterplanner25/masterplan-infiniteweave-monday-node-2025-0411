"""
Public surface for the agent domain.
Consumers: automation
"""

from __future__ import annotations

from AINDY.kernel.syscall_registry import SyscallContext

PUBLIC_API_VERSION = "1.0"


def dispatch_tool_request(payload: dict, context: SyscallContext) -> dict:
    from apps.agent.syscalls.syscall_handlers import handle_agent_dispatch_tool

    return dict(handle_agent_dispatch_tool(payload, context) or {})


__all__ = [
    "dispatch_tool_request",
]
