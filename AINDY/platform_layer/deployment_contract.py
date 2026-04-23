from __future__ import annotations

import os
from typing import Any

from AINDY.config import settings

_api_runtime_state: dict[str, Any] = {
    "startup_complete": False,
    "background_enabled": False,
    "scheduler_role": "disabled",
    "event_bus_ready": False,
}

_worker_runtime_state: dict[str, Any] = {
    "startup_complete": False,
    "queue_ready": False,
    "schema_ready": False,
    "scheduler_role": "disabled",
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


def deployment_contract_summary() -> dict[str, Any]:
    return {
        "environment": settings.ENV,
        "execution_mode": settings.EXECUTION_MODE,
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
