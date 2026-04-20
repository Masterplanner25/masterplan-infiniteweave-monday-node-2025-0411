"""Application plugin bootstrap — thin aggregator.

Each domain owns its own apps/<domain>/bootstrap.py with a register() function.
This file imports and calls them in dependency order.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_BOOTSTRAPPED = False


def bootstrap() -> None:
    global _BOOTSTRAPPED
    if _BOOTSTRAPPED:
        return
    _BOOTSTRAPPED = True

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

    for mod in (
        tasks_bootstrap,
        analytics_bootstrap,
        masterplan_bootstrap,
        automation_bootstrap,
        arm_bootstrap,
        search_bootstrap,
        identity_bootstrap,
        rippletrace_bootstrap,
        social_bootstrap,
        freelance_bootstrap,
        agent_bootstrap,
        authorship_bootstrap,
        bridge_bootstrap,
        autonomy_bootstrap,
        dashboard_bootstrap,
        network_bridge_bootstrap,
    ):
        mod.register()


def bootstrap_models() -> None:
    """Backward-compatible entry point — delegates to bootstrap()."""
    bootstrap()
