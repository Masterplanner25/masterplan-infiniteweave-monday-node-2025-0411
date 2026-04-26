"""Task agent tool implementations."""

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
        "task.create",
        risk="low",
        description="Create a new task in the user's task list",
        capability="tool:task.create",
        required_capability="manage_tasks",
        category="task",
        egress_scope="internal",
    )(task_create)
    register_tool(
        "task.complete",
        risk="medium",
        description="Mark a task as complete by name",
        capability="tool:task.complete",
        required_capability="manage_tasks",
        category="task",
        egress_scope="internal",
    )(task_complete)


def task_create(args: dict, user_id: str, db) -> dict:
    data = _dispatch_agent_tool("task.create", "sys.v1.task.create", args, user_id)
    return {"task_id": data.get("task_id"), "name": data.get("task_name"), "status": data.get("status")}


def task_complete(args: dict, user_id: str, db) -> dict:
    return _dispatch_agent_tool("task.complete_full", "sys.v1.task.complete_full", args, user_id)
