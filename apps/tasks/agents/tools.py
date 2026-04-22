"""Task agent tool implementations."""

from __future__ import annotations

from AINDY.agents.tool_registry import register_tool


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
    from apps.agent.agents.tool_helpers import dispatch_tool_syscall

    data = dispatch_tool_syscall("sys.v1.task.create", args, user_id, "task.create")
    return {"task_id": data.get("task_id"), "name": data.get("task_name"), "status": data.get("status")}


def task_complete(args: dict, user_id: str, db) -> dict:
    from apps.agent.agents.tool_helpers import dispatch_tool_syscall

    return dispatch_tool_syscall("sys.v1.task.complete_full", args, user_id, "task.complete_full")
