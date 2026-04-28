"""SQLAlchemy model registration and registry access helpers.

Importing this module populates the shared ``Base.metadata`` with platform
models only. App-owned models are loaded by app bootstrap through
``register_models`` so AINDY does not import apps directly.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from typing import Any

from AINDY.platform_layer.registry import get_symbol, load_plugins

# Platform models.
import AINDY.db.models.agent  # noqa: F401
import AINDY.db.models.agent_event  # noqa: F401
import AINDY.db.models.agent_registry  # noqa: F401
import AINDY.db.models.agent_run  # noqa: F401
import AINDY.db.models.api_key  # noqa: F401
import AINDY.db.models.background_task_lease  # noqa: F401
import AINDY.db.models.capability  # noqa: F401
import AINDY.db.models.dynamic_flow  # noqa: F401
import AINDY.db.models.dynamic_node  # noqa: F401
import AINDY.db.models.execution_unit  # noqa: F401
import AINDY.db.models.event_edge  # noqa: F401
import AINDY.db.models.flow_run  # noqa: F401
import AINDY.db.models.job_log  # noqa: F401
import AINDY.db.models.memory_metrics  # noqa: F401
import AINDY.db.models.memory_node_history  # noqa: F401
import AINDY.db.models.memory_trace  # noqa: F401
import AINDY.db.models.memory_trace_node  # noqa: F401
import AINDY.db.models.nodus_scheduled_job  # noqa: F401
import AINDY.db.models.nodus_trace_event  # noqa: F401
import AINDY.db.models.request_metric  # noqa: F401
import AINDY.db.models.system_event  # noqa: F401
import AINDY.db.models.system_health_log  # noqa: F401
import AINDY.db.models.system_state_snapshot  # noqa: F401
import AINDY.db.models.user  # noqa: F401
import AINDY.db.models.user_identity  # noqa: F401
import AINDY.db.models.waiting_flow_run  # noqa: F401
import AINDY.db.models.webhook_subscription  # noqa: F401


def register_models(import_fn: Callable[[], Any]) -> Any:
    """Run an app-owned model import callback to populate shared metadata."""
    return import_fn()


def get_registered_model(name: str) -> Any:
    load_plugins()
    model = get_symbol(name)
    if model is None:
        raise LookupError(f"ORM model {name!r} is not registered")
    module_name = getattr(model, "__module__", "")
    module_candidates = []
    parts = module_name.split(".")
    if len(parts) >= 3:
        module_candidates.append(".".join(parts[:2] + ["models"]))
    module_candidates.append(module_name)
    for candidate in dict.fromkeys(module_candidates):
        if not candidate:
            continue
        try:
            module = importlib.import_module(candidate)
        except Exception:
            continue
        current = getattr(module, name, None)
        if current is not None:
            return current
    return model
