"""Masterplan agent tool implementations."""

from __future__ import annotations

from AINDY.agents.tool_registry import register_tool
from AINDY.kernel.syscall_dispatcher import get_dispatcher, make_syscall_ctx_from_tool


def _dispatch_agent_tool(tool_name: str, syscall_name: str, args: dict, user_id: str) -> dict:
    ctx = make_syscall_ctx_from_tool(user_id, capabilities=["agent.tool_dispatch"])
    result = get_dispatcher().dispatch(
        "sys.v1.agent.dispatch_tool",
        {
            "tool_name": tool_name,
            "payload": args,
            "user_id": user_id,
            "syscall_name": syscall_name,
            "capability": tool_name,
        },
        ctx,
    )
    if result["status"] == "error":
        raise RuntimeError(result["error"])
    return result["data"]


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
    return _dispatch_agent_tool("genesis.message", "sys.v1.genesis.message", args, user_id)
