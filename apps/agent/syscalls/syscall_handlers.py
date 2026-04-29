"""Agent-owned syscall handlers."""

from __future__ import annotations

import logging

from AINDY.kernel.syscall_registry import SyscallContext, register_syscall

logger = logging.getLogger(__name__)


def handle_agent_dispatch_tool(payload: dict, context: SyscallContext) -> dict:
    from apps.agent.agents.tool_helpers import dispatch_tool_syscall

    tool_name = payload.get("tool_name")
    user_id = payload.get("user_id")
    syscall_name = payload.get("syscall_name")
    inner_payload = payload.get("payload")
    capability = payload.get("capability") or tool_name

    if not tool_name:
        raise ValueError("sys.v1.agent.dispatch_tool requires 'tool_name'")
    if not user_id:
        raise ValueError("sys.v1.agent.dispatch_tool requires 'user_id'")
    if not syscall_name:
        raise ValueError("sys.v1.agent.dispatch_tool requires 'syscall_name'")
    if inner_payload is None:
        inner_payload = {}
    if not isinstance(inner_payload, dict):
        raise ValueError("sys.v1.agent.dispatch_tool requires 'payload' to be a dict")

    return dispatch_tool_syscall(syscall_name, inner_payload, user_id, capability)


def _handle_count_runs(payload: dict, ctx: SyscallContext) -> dict:
    from AINDY.platform_layer.user_ids import parse_user_id
    from apps.agent.models.agent_run import AgentRun

    db = ctx.db
    if db is None:
        return {"count": 0}
    user_id = parse_user_id(payload.get("user_id"))
    if user_id is None:
        return {"count": 0}
    query = db.query(AgentRun.id).filter(AgentRun.user_id == user_id)
    status_filter = payload.get("status")
    if status_filter:
        statuses = status_filter if isinstance(status_filter, list) else [status_filter]
        query = query.filter(AgentRun.status.in_(statuses))
    return {"count": query.count()}


def _handle_list_recent_runs(payload: dict, ctx: SyscallContext) -> dict:
    from AINDY.agents.agent_runtime import run_to_dict
    from AINDY.platform_layer.user_ids import parse_user_id
    from apps.agent.models.agent_run import AgentRun

    db = ctx.db
    if db is None:
        return {"runs": []}
    user_id = parse_user_id(payload.get("user_id"))
    if user_id is None:
        return {"runs": []}
    limit = int(payload.get("limit", 10))
    rows = (
        db.query(AgentRun)
        .filter(AgentRun.user_id == user_id)
        .order_by(AgentRun.created_at.desc(), AgentRun.id.desc())
        .limit(limit)
        .all()
    )
    return {"runs": [run_to_dict(row) for row in rows]}


def _handle_ensure_initial_run(payload: dict, ctx: SyscallContext) -> dict:
    from AINDY.platform_layer.user_ids import parse_user_id
    from apps.agent.models.agent_run import AgentRun

    db = ctx.db
    if db is None:
        return {"run_id": None, "created": False}
    user_id_raw = payload.get("user_id")
    user_id = parse_user_id(user_id_raw)
    if user_id is None:
        return {"run_id": None, "created": False}
    existing = (
        db.query(AgentRun)
        .filter(
            AgentRun.user_id == user_id,
            AgentRun.goal == "Initial agent context",
        )
        .first()
    )
    if existing:
        return {"run_id": str(existing.id), "created": False}
    run = AgentRun(
        user_id=user_id,
        goal="Initial agent context",
        status="completed",
        overall_risk="low",
        steps_total=0,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return {"run_id": str(run.id), "created": True}


def register_agent_syscall_handlers() -> None:
    register_syscall(
        name="sys.v1.agent.dispatch_tool",
        handler=handle_agent_dispatch_tool,
        capability="agent.tool_dispatch",
        description="Dispatch an approved agent tool syscall through the agent boundary.",
        input_schema={
            "required": ["tool_name", "payload", "user_id", "syscall_name"],
            "properties": {
                "tool_name": {"type": "string"},
                "payload": {"type": "dict"},
                "user_id": {"type": "string"},
                "syscall_name": {"type": "string"},
                "capability": {"type": "string"},
            },
        },
        stable=False,
    )
    register_syscall(
        name="sys.v1.agent.count_runs",
        handler=_handle_count_runs,
        capability="agent.read",
        description="Count AgentRun rows for a user, optionally filtered by status.",
        input_schema={
            "properties": {
                "user_id": {"type": "string"},
                "status": {"type": "list"},
            },
        },
        output_schema={
            "required": ["count"],
            "properties": {"count": {"type": "int"}},
        },
        stable=False,
    )
    register_syscall(
        name="sys.v1.agent.list_recent_runs",
        handler=_handle_list_recent_runs,
        capability="agent.read",
        description="List recent AgentRun rows for a user as plain dicts.",
        input_schema={
            "properties": {
                "user_id": {"type": "string"},
                "limit": {"type": "int"},
            },
        },
        output_schema={
            "required": ["runs"],
            "properties": {"runs": {"type": "list"}},
        },
        stable=False,
    )
    register_syscall(
        name="sys.v1.agent.ensure_initial_run",
        handler=_handle_ensure_initial_run,
        capability="agent.write",
        description="Find or create the initial signup AgentRun sentinel for a user.",
        input_schema={
            "properties": {
                "user_id": {"type": "string"},
            },
        },
        output_schema={
            "required": ["run_id", "created"],
            "properties": {
                "run_id": {"type": "string"},
                "created": {"type": "bool"},
            },
        },
        stable=False,
    )
    logger.info(
        "[agent_syscalls] registered dispatch_tool, count_runs, list_recent_runs, ensure_initial_run"
    )
