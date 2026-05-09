"""Masterplan agent tool implementations."""

from __future__ import annotations

from AINDY.agents.tool_registry import register_tool
from AINDY.agents.tool_syscalls import invoke_tool_syscall


def _dispatch_tool_syscall(syscall_name: str, args: dict, user_id: str, *, capability: str) -> dict:
    return invoke_tool_syscall(
        syscall_name,
        args,
        user_id=user_id,
        capability=capability,
    )


def register() -> None:
    register_tool(
        "genesis.message",
        risk="high",
        description="Send a message to the Genesis strategic planning session (modifies MasterPlan state)",
        capability="tool:genesis.message",
        required_capability="strategic_planning",
        category="planning",
        egress_scope="external_llm",
    )(genesis_message)


def genesis_message(args: dict, user_id: str, db) -> dict:
    return _dispatch_tool_syscall("sys.v1.genesis.message", args, user_id, capability="genesis.message")
