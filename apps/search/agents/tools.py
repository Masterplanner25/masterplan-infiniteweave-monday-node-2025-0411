"""Search and research agent tool implementations."""

from __future__ import annotations

from AINDY.agents.tool_registry import register_tool


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
    from apps.agent.agents.tool_helpers import dispatch_tool_syscall

    data = dispatch_tool_syscall("sys.v1.leadgen.search_ai", args, user_id, "leadgen.search_ai")
    return {"leads": data.get("leads", []), "count": data.get("count", 0)}


def research_query(args: dict, user_id: str, db) -> dict:
    from apps.agent.agents.tool_helpers import dispatch_tool_syscall

    return dispatch_tool_syscall("sys.v1.research.query", args, user_id, "research.query")
