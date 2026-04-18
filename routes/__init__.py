"""Compatibility mirrors for legacy route source/import tests."""

from __future__ import annotations

import sys
from importlib import import_module

_ROUTE_ALIASES = {
    "agent_router": "apps.agent.routes.agent_router",
    "analytics_router": "apps.analytics.routes.analytics_router",
    "arm_router": "apps.arm.routes.arm_router",
    "auth_router": "AINDY.routes.auth_router",
    "automation_router": "apps.automation.routes.automation_router",
    "bridge_router": "apps.bridge.routes.bridge_router",
    "dashboard_router": "apps.dashboard.routes.dashboard_router",
    "flow_router": "AINDY.routes.flow_router",
    "freelance_router": "apps.freelance.routes.freelance_router",
    "genesis_router": "apps.masterplan.routes.genesis_router",
    "goals_router": "apps.masterplan.routes.goals_router",
    "health_router": "AINDY.routes.health_router",
    "identity_router": "apps.identity.routes.identity_router",
    "leadgen_router": "apps.search.routes.leadgen_router",
    "masterplan_router": "apps.masterplan.routes.masterplan_router",
    "memory_metrics_router": "AINDY.routes.memory_metrics_router",
    "memory_router": "AINDY.routes.memory_router",
    "observability_router": "AINDY.routes.observability_router",
    "platform_router": "AINDY.routes.platform_router",
    "research_results_router": "apps.search.routes.research_results_router",
    "rippletrace_router": "apps.rippletrace.routes.rippletrace_router",
    "score_router": "apps.masterplan.routes.score_router",
    "social_router": "apps.social.routes.social_router",
    "task_router": "apps.tasks.routes.task_router",
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
