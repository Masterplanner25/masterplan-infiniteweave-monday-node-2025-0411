"""Masterplan agent tool implementations."""

from __future__ import annotations

from AINDY.agents.tool_registry import register_tool
from apps.agent.agents.tool_helpers import dispatch_tool_syscall


def register() -> None:
    register_tool(
        "genesis.message",
        risk="high",
        description="Send a message to the Genesis strategic planning session (modifies MasterPlan state)",
        capability="tool:genesis.message",
        required_capability="strategic_planning",
        category="genesis",
        egress_scope="external_llm",
    )(genesis_message)


def genesis_message(args: dict, user_id: str, db) -> dict:
    return dispatch_tool_syscall("sys.v1.genesis.message", args, user_id, "genesis.message")
