from __future__ import annotations

import os
from typing import Any

from AINDY.config import settings

BOOT_MODE_ENV_VAR = "AINDY_BOOT_MODE"
RUNTIME_ONLY_BOOT_MODE = "runtime-only"
APP_PROFILE_BOOT_MODE = "app-profile"
RUNTIME_ONLY_BOOT_PROFILE = "platform-only"
RUNTIME_ONLY_REQUIRED_ROUTES = (
    "/health",
    "/ready",
    "/apps/agent/run",
    "/apps/agent/tools",
    "/apps/memory/recall",
    "/apps/memory/nodes",
    "/platform/syscalls",
)
RUNTIME_ONLY_REQUIRED_ROUTE_PREFIXES = (
    "/platform/",
    "/apps/agent/",
    "/apps/memory/",
)
RUNTIME_ONLY_BASELINE_AGENT_TOOLS = (
    "memory.recall",
    "memory.write",
)
RUNTIME_ONLY_BASELINE_AGENT_CAPABILITIES = (
    "execute_flow",
    "read_memory",
    "write_memory",
)
RUNTIME_BASELINE_AGENT_ENRICHMENTS = (
    {
        "type": "planner_context",
        "behavior": "generic runtime-owned planner prompt with empty context block",
    },
    {
        "type": "tool_catalog",
        "behavior": "runtime-owned memory.recall and memory.write only",
    },
    {
        "type": "trigger_evaluator",
        "behavior": "runtime default evaluator with no domain-specific scoring assumptions",
    },
    {
        "type": "suggestions",
        "behavior": "empty unless a plugin registers a provider",
    },
    {
        "type": "completion_hook",
        "behavior": "runtime no-op completion hook",
    },
)
OPTIONAL_PLUGIN_AGENT_ENRICHMENTS = (
    {
        "type": "planner_context",
        "behavior": "KPI-aware prompt enrichment and app-selected memory/planning guidance",
    },
    {
        "type": "suggestions",
        "behavior": "KPI-driven or persisted-loop tool suggestions",
    },
    {
        "type": "completion_hook",
        "behavior": "post-run Infinity orchestration and next_action enrichment",
    },
    {
        "type": "tool_catalog",
        "behavior": "additional app-owned tools such as task, ARM, search, or masterplan actions",
    },
)
AMBIGUOUS_AGENT_ENRICHMENTS = (
    {
        "type": "planner_context",
        "behavior": "memory-context prompt enrichment is domain-agnostic but is currently bundled with KPI-aware app enrichment",
        "refactor_goal": "split runtime-owned memory-context augmentation from app-owned KPI planning context",
    },
    {
        "type": "suggestions",
        "behavior": "KPI suggestion heuristics and persisted-loop replay are duplicated across app provider and owner syscall paths",
        "refactor_goal": "keep the feature plugin-owned but consolidate the implementation behind one owner boundary",
    },
    {
        "type": "completion_hook",
        "behavior": "analytics orchestration currently mutates generic run.result through a completion hook",
        "refactor_goal": "keep orchestration plugin-owned but consider a dedicated post-run enrichment contract instead of an overloaded generic hook",
    },
)
RUNTIME_ONLY_INTENTIONALLY_UNAVAILABLE = (
    "app-domain routers from apps/*",
    "app-owned agent tools beyond runtime defaults",
    "app-owned planner enrichment and suggestion providers",
    "app-owned completion hooks and Infinity orchestration",
    "app-owned syscalls and startup hooks",
)

_api_runtime_state: dict[str, Any] = {
    "startup_complete": False,
    "background_enabled": False,
    "scheduler_role": "disabled",
    "event_bus_ready": False,
    "boot_mode": "unknown",
    "boot_profile": "unknown",
    "boot_profile_source": "unknown",
    "app_plugins_loaded": False,
    "app_plugin_count": 0,
}

_worker_runtime_state: dict[str, Any] = {
    "startup_complete": False,
    "queue_ready": False,
    "schema_ready": False,
    "scheduler_role": "disabled",
}


def runtime_ui_surface_state() -> dict[str, Any]:
    api_state = get_api_runtime_state()
    boot_mode = api_state.get("boot_mode", "unknown")
    runtime_only = boot_mode == RUNTIME_ONLY_BOOT_MODE
    return {
        "boot_mode": boot_mode,
        "boot_profile": api_state.get("boot_profile", "unknown"),
        "boot_profile_source": api_state.get("boot_profile_source", "unknown"),
        "app_plugins_loaded": bool(api_state.get("app_plugins_loaded", False)),
        "app_plugin_count": int(api_state.get("app_plugin_count", 0) or 0),
        "ui_mode": RUNTIME_ONLY_BOOT_MODE if runtime_only else APP_PROFILE_BOOT_MODE,
        "default_route": "/memory" if runtime_only else "/dashboard",
        "platform_home": "/platform/agent",
    }


def background_tasks_enabled() -> bool:
    if settings.is_testing or os.getenv("PYTEST_CURRENT_TEST"):
        return False
    return os.getenv("AINDY_ENABLE_BACKGROUND_TASKS", "true").lower() in {
        "1",
        "true",
        "yes",
    }


def redis_required() -> bool:
    return settings.requires_redis


def worker_required() -> bool:
    return not settings.is_testing and settings.EXECUTION_MODE == "distributed"


def event_bus_required() -> bool:
    return redis_required()


def queue_backend_required() -> bool:
    return worker_required()


def schema_enforcement_required() -> bool:
    return not settings.is_testing


def publish_api_runtime_state(**updates: Any) -> dict[str, Any]:
    _api_runtime_state.update(updates)
    return dict(_api_runtime_state)


def get_api_runtime_state() -> dict[str, Any]:
    return dict(_api_runtime_state)


def publish_worker_runtime_state(**updates: Any) -> dict[str, Any]:
    _worker_runtime_state.update(updates)
    return dict(_worker_runtime_state)


def get_worker_runtime_state() -> dict[str, Any]:
    return dict(_worker_runtime_state)


def reset_runtime_state() -> None:
    _api_runtime_state.clear()
    _api_runtime_state.update(
        {
            "startup_complete": False,
            "background_enabled": False,
            "scheduler_role": "disabled",
            "event_bus_ready": False,
            "boot_mode": "unknown",
            "boot_profile": "unknown",
            "boot_profile_source": "unknown",
            "app_plugins_loaded": False,
            "app_plugin_count": 0,
        }
    )
    _worker_runtime_state.clear()
    _worker_runtime_state.update(
        {
            "startup_complete": False,
            "queue_ready": False,
            "schema_ready": False,
            "scheduler_role": "disabled",
        }
    )


def runtime_only_deployment_contract() -> dict[str, Any]:
    return {
        "boot_mode": RUNTIME_ONLY_BOOT_MODE,
        "boot_profile": RUNTIME_ONLY_BOOT_PROFILE,
        "activation": {
            "preferred": f"{BOOT_MODE_ENV_VAR}={RUNTIME_ONLY_BOOT_MODE}",
            "entrypoint": "uvicorn AINDY.runtime_only:app",
            "legacy_profile_override": f"AINDY_BOOT_PROFILE={RUNTIME_ONLY_BOOT_PROFILE}",
        },
        "mounted_routes": {
            "required_routes": list(RUNTIME_ONLY_REQUIRED_ROUTES),
            "required_prefixes": list(RUNTIME_ONLY_REQUIRED_ROUTE_PREFIXES),
        },
        "baseline_agent_capabilities": {
            "planner": "generic runtime prompt",
            "tools": list(RUNTIME_ONLY_BASELINE_AGENT_TOOLS),
            "capabilities": list(RUNTIME_ONLY_BASELINE_AGENT_CAPABILITIES),
            "suggestions": "empty unless a plugin registers a provider",
            "completion_hook": "runtime no-op",
        },
        "agent_enrichment_boundary": agent_runtime_enrichment_contract(),
        "health_and_readiness": {
            "liveness_route": "/health",
            "readiness_route": "/ready",
        },
        "intentionally_unavailable": list(RUNTIME_ONLY_INTENTIONALLY_UNAVAILABLE),
    }


def deployment_contract_summary() -> dict[str, Any]:
    return {
        "environment": settings.ENV,
        "execution_mode": settings.EXECUTION_MODE,
        "runtime_only_support": runtime_only_deployment_contract(),
        "requires": {
            "redis": redis_required(),
            "worker": worker_required(),
            "event_bus": event_bus_required(),
            "queue_backend": queue_backend_required(),
            "schema_enforcement": schema_enforcement_required(),
        },
        "optional_in_dev": {
            "redis": settings.is_dev or settings.is_testing,
            "worker": settings.is_dev or settings.is_testing,
            "scheduler_leadership": True,
            "peripheral_domains": True,
        },
    }


def agent_runtime_enrichment_contract() -> dict[str, Any]:
    return {
        "baseline_runtime_contract": list(RUNTIME_BASELINE_AGENT_ENRICHMENTS),
        "optional_plugin_enrichment": list(OPTIONAL_PLUGIN_AGENT_ENRICHMENTS),
        "ambiguous_or_refactor": list(AMBIGUOUS_AGENT_ENRICHMENTS),
    }


def resolve_boot_mode_for_profile(profile_name: str | None) -> str:
    if profile_name == RUNTIME_ONLY_BOOT_PROFILE:
        return RUNTIME_ONLY_BOOT_MODE
    return APP_PROFILE_BOOT_MODE


def get_requested_boot_mode() -> str | None:
    value = os.getenv(BOOT_MODE_ENV_VAR, "").strip()
    if not value:
        return None
    if value == RUNTIME_ONLY_BOOT_MODE:
        return value
    raise ValueError(
        f"Unsupported {BOOT_MODE_ENV_VAR} value {value!r}. "
        f"Supported values: {RUNTIME_ONLY_BOOT_MODE!r}."
    )


def resolve_profile_for_boot_mode(boot_mode: str | None) -> str | None:
    if boot_mode is None:
        return None
    if boot_mode == RUNTIME_ONLY_BOOT_MODE:
        return RUNTIME_ONLY_BOOT_PROFILE
    raise ValueError(f"Unsupported boot mode {boot_mode!r}")
