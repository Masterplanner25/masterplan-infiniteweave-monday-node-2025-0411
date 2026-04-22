"""Application plugin bootstrap — thin aggregator.

Each domain owns its own apps/<domain>/bootstrap.py with a register() function.
This file imports and calls them in dependency order.
"""
from __future__ import annotations

import logging

from AINDY.platform_layer.bootstrap_graph import resolve_boot_order

logger = logging.getLogger(__name__)

_BOOTSTRAPPED = False


def discover_app_bootstraps() -> dict[str, object]:
    from apps.tasks import bootstrap as tasks_bootstrap
    from apps.analytics import bootstrap as analytics_bootstrap
    from apps.masterplan import bootstrap as masterplan_bootstrap
    from apps.automation import bootstrap as automation_bootstrap
    from apps.arm import bootstrap as arm_bootstrap
    from apps.search import bootstrap as search_bootstrap
    from apps.identity import bootstrap as identity_bootstrap
    from apps.rippletrace import bootstrap as rippletrace_bootstrap
    from apps.social import bootstrap as social_bootstrap
    from apps.freelance import bootstrap as freelance_bootstrap
    from apps.agent import bootstrap as agent_bootstrap
    from apps.authorship import bootstrap as authorship_bootstrap
    from apps.bridge import bootstrap as bridge_bootstrap
    from apps.autonomy import bootstrap as autonomy_bootstrap
    from apps.dashboard import bootstrap as dashboard_bootstrap
    from apps.network_bridge import bootstrap as network_bridge_bootstrap

    return {
        "tasks": tasks_bootstrap,
        "analytics": analytics_bootstrap,
        "masterplan": masterplan_bootstrap,
        "automation": automation_bootstrap,
        "arm": arm_bootstrap,
        "search": search_bootstrap,
        "identity": identity_bootstrap,
        "rippletrace": rippletrace_bootstrap,
        "social": social_bootstrap,
        "freelance": freelance_bootstrap,
        "agent": agent_bootstrap,
        "authorship": authorship_bootstrap,
        "bridge": bridge_bootstrap,
        "autonomy": autonomy_bootstrap,
        "dashboard": dashboard_bootstrap,
        "network_bridge": network_bridge_bootstrap,
    }


def get_resolved_boot_order() -> list[str]:
    return resolve_boot_order(discover_app_bootstraps())


def bootstrap() -> None:
    global _BOOTSTRAPPED
    if _BOOTSTRAPPED:
        return
    _BOOTSTRAPPED = True

    app_bootstraps = discover_app_bootstraps()
    ordered_apps = resolve_boot_order(app_bootstraps)
    logger.info("Boot order resolved: %s", " → ".join(ordered_apps))

    for app_name in ordered_apps:
        mod = app_bootstraps[app_name]
        try:
            mod.register()
        except ValueError as exc:
            app_name = mod.__name__.removesuffix(".bootstrap")
            logger.exception("Bootstrap registration failed for %s: %s", app_name, exc)
            raise RuntimeError(f"Bootstrap registration failed for {app_name}: {exc}") from exc


def bootstrap_models() -> None:
    """Backward-compatible entry point — delegates to bootstrap()."""
    bootstrap()
