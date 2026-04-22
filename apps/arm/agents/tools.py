"""ARM agent tool implementations."""

from __future__ import annotations

from AINDY.agents.tool_registry import register_tool


def register() -> None:
    register_tool(
        "arm.analyze",
        risk="medium",
        description="Analyze code or a topic using the ARM reasoning engine",
        capability="tool:arm.analyze",
        required_capability="external_api_call",
        category="arm",
        egress_scope="external_llm",
    )(arm_analyze)
    register_tool(
        "arm.generate",
        risk="medium",
        description="Generate or refactor code using the ARM code generation engine",
        capability="tool:arm.generate",
        required_capability="external_api_call",
        category="arm",
        egress_scope="external_llm",
    )(arm_generate)


def arm_analyze(args: dict, user_id: str, db) -> dict:
    from apps.agent.agents.tool_helpers import dispatch_tool_syscall

    data = dispatch_tool_syscall("sys.v1.arm.analyze", args, user_id, "arm.analyze")
    return {
        "summary": data.get("summary", ""),
        "architecture_score": data.get("architecture_score"),
        "integrity_score": data.get("integrity_score"),
        "analysis_id": data.get("analysis_id"),
    }


def arm_generate(args: dict, user_id: str, db) -> dict:
    from apps.agent.agents.tool_helpers import dispatch_tool_syscall

    data = dispatch_tool_syscall("sys.v1.arm.generate", args, user_id, "arm.generate")
    return {
        "generated_code": data.get("generated_code", ""),
        "explanation": data.get("explanation", ""),
        "generation_id": data.get("generation_id"),
    }
