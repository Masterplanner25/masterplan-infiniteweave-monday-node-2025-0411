"""Search and research agent tool implementations."""

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
    data = _dispatch_agent_tool("leadgen.search_ai", "sys.v1.leadgen.search_ai", args, user_id)
    return {"leads": data.get("leads", []), "count": data.get("count", 0)}


def research_query(args: dict, user_id: str, db) -> dict:
    return _dispatch_agent_tool("research.query", "sys.v1.research.query", args, user_id)
