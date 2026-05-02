"""Agent-owned syscall handlers."""

from __future__ import annotations

import logging

from AINDY.kernel.syscall_registry import SyscallContext, register_syscall

logger = logging.getLogger(__name__)


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


def register_agent_syscall_handlers() -> None:
    register_syscall(
        name="sys.v1.agent.dispatch_tool",
        handler=handle_agent_dispatch_tool,
        capability="agent.tool_dispatch",
        description="Dispatch an approved agent tool syscall through the agent boundary.",
        input_schema={
            "required": ["tool_name", "payload", "user_id", "syscall_name"],
            "properties": {
                "tool_name": {"type": "string"},
                "payload": {"type": "dict"},
                "user_id": {"type": "string"},
                "syscall_name": {"type": "string"},
                "capability": {"type": "string"},
            },
        },
        stable=False,
    )
    logger.info(
        "[agent_syscalls] registered dispatch_tool"
    )
