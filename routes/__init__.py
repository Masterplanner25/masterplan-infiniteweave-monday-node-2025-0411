"""Runtime-owned compatibility mirrors for legacy route source/import tests.

This package must remain safe to publish with the runtime alone. It may expose
only aliases that resolve fully within ``AINDY.routes``.
"""

from __future__ import annotations

import sys
from importlib import import_module

_ROUTE_ALIASES = {
    "agent_router": "AINDY.routes.agent_router",
    "auth_router": "AINDY.routes.auth_router",
    "flow_router": "AINDY.routes.flow_router",
    "health_router": "AINDY.routes.health_router",
    "memory_metrics_router": "AINDY.routes.memory_metrics_router",
    "memory_router": "AINDY.routes.memory_router",
    "observability_router": "AINDY.routes.observability_router",
    "platform_router": "AINDY.routes.platform_router",
    "watcher_router": "AINDY.routes.watcher_router",
}


def __getattr__(name: str):
    target = _ROUTE_ALIASES.get(name)
    if target is None:
        raise AttributeError(name)
    module = import_module(target)
    sys.modules.setdefault(f"routes.{name}", module)
    globals()[name] = module
    return module
