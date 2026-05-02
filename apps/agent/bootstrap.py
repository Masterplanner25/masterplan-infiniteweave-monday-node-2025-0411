"""Agent domain bootstrap."""
from __future__ import annotations

BOOTSTRAP_DEPENDS_ON: list[str] = []
IS_CORE_DOMAIN: bool = True
APP_DEPENDS_ON: list[str] = []


def register() -> None:
    _register_models()
    _register_route_prefixes()
    _register_syscalls()
    _register_async_jobs()
    _register_agent_tools()
    _register_agent_capabilities()
    _register_agent_runtime_extensions()
    _register_trigger_evaluators()
    _register_health_check()


def _register_models() -> None:
    # Agent persistence models are runtime-owned and loaded by AINDY.db.model_registry.
    return None

def _register_route_prefixes() -> None:
    from AINDY.platform_layer.registry import register_route_prefix
    register_route_prefix("agent", "agent")


def _register_syscalls() -> None:
    from apps.agent.syscalls.syscall_handlers import register_agent_syscall_handlers

    register_agent_syscall_handlers()


def _register_async_jobs() -> None:
    from AINDY.platform_layer.async_job_service import register_async_job
    register_async_job("agent.create_run")(_job_agent_create_run)
    register_async_job("agent.approve_run")(_job_agent_approve_run)


def _register_agent_tools() -> None:
    from apps.agent.agents.tools import register as register_agent_tools
    register_agent_tools()


def _register_agent_capabilities() -> None:
    from apps.agent.agents.capabilities import register as register_agent_capabilities
    register_agent_capabilities()


def _register_agent_runtime_extensions() -> None:
    from apps.agent.agents.runtime_extensions import register
    register()


def _register_trigger_evaluators() -> None:
    from apps.agent.agents.triggers import register
    register()

def _job_agent_create_run(payload: dict, db):
    from AINDY.agents.agent_runtime import create_run, execute_run, to_execution_response

    user_id = payload["user_id"]
    run = create_run(goal=payload["goal"], user_id=user_id, db=db)
    if not run:
        raise RuntimeError("Failed to generate plan")
    if run["status"] == "approved":
        run = execute_run(run_id=run["run_id"], user_id=user_id, db=db) or run
    return to_execution_response(run, db)


def _job_agent_approve_run(payload: dict, db):
    from AINDY.agents.agent_runtime import approve_run, to_execution_response

    run = approve_run(run_id=payload["run_id"], user_id=payload["user_id"], db=db)
    if not run:
        raise RuntimeError("Run not found or not approvable")
    return to_execution_response(run, db)


def _register_health_check() -> None:
    from AINDY.platform_layer.registry import register_health_check

    register_health_check("agent", lambda: {"status": "ok"})
