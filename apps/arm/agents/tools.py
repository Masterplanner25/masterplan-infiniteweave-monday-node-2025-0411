"""ARM agent tool implementations."""

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
        "arm.analyze",
        risk="medium",
        description="Analyze code or a topic using the ARM reasoning engine",
        capability="tool:arm.analyze",
        required_capability="external_api_call",
        category="analysis",
        egress_scope="external_llm",
    )(arm_analyze)
    register_tool(
        "arm.generate",
        risk="medium",
        description="Generate or refactor code using the ARM code generation engine",
        capability="tool:arm.generate",
        required_capability="external_api_call",
        category="analysis",
        egress_scope="external_llm",
    )(arm_generate)


def arm_analyze(args: dict, user_id: str, db) -> dict:
    data = _dispatch_agent_tool("arm.analyze", "sys.v1.arm.analyze", args, user_id)
    return {
        "summary": data.get("summary", ""),
        "architecture_score": data.get("architecture_score"),
        "integrity_score": data.get("integrity_score"),
        "analysis_id": data.get("analysis_id"),
    }


def arm_generate(args: dict, user_id: str, db) -> dict:
    data = _dispatch_agent_tool("arm.generate", "sys.v1.arm.generate", args, user_id)
    return {
        "generated_code": data.get("generated_code", ""),
        "explanation": data.get("explanation", ""),
        "generation_id": data.get("generation_id"),
    }
