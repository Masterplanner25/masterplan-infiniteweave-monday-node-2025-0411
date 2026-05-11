"""Search and research agent tool implementations."""

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
        "leadgen.search",
        risk="medium",
        description="Search for B2B leads matching a query",
        capability="tool:leadgen.search",
        required_capability="external_api_call",
        category="leadgen",
        egress_scope="external_web",
    )(leadgen_search)
    register_tool(
        "research.query",
        risk="low",
        description="Query external sources for research on a topic",
        capability="tool:research.query",
        required_capability="external_api_call",
        category="research",
        egress_scope="external_web",
    )(research_query)


def leadgen_search(args: dict, user_id: str, db) -> dict:
    data = _dispatch_tool_syscall("sys.v1.leadgen.search_ai", args, user_id, capability="leadgen.search_ai")
    return {"leads": data.get("leads", []), "count": data.get("count", 0)}


def research_query(args: dict, user_id: str, db) -> dict:
    return _dispatch_tool_syscall("sys.v1.research.query", args, user_id, capability="research.query")
