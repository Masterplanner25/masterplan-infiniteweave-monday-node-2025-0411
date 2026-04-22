"""Application plugin bootstrap aggregator with degraded-mode handling.

`BOOTSTRAP_DEPENDS_ON` is the hard startup-order graph used by the runtime.
`APP_DEPENDS_ON` is the broader direct cross-app import graph used for
architecture governance and drift detection.
"""
from __future__ import annotations

import logging

from AINDY.platform_layer.bootstrap_graph import resolve_boot_order
from AINDY.platform_layer.registry import publish_degraded_domains

logger = logging.getLogger(__name__)

_BOOTSTRAPPED = False
_DEGRADED_DOMAINS: list[str] = []

CORE_DOMAINS: frozenset[str] = frozenset({
    "tasks",
    "identity",
    "analytics",
    "agent",
})


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


def get_degraded_domains() -> list[str]:
    return list(_DEGRADED_DOMAINS)


def bootstrap() -> None:
    global _BOOTSTRAPPED, _DEGRADED_DOMAINS
    if _BOOTSTRAPPED:
        return

    publish_degraded_domains(())
    app_bootstraps = discover_app_bootstraps()
    ordered_apps = resolve_boot_order(app_bootstraps)
    logger.info("Boot order resolved: %s", " -> ".join(ordered_apps))

    failed_domains: set[str] = set()
    failed_peripheral: list[str] = []

    for app_name in ordered_apps:
        mod = app_bootstraps[app_name]
        depends_on = getattr(mod, "BOOTSTRAP_DEPENDS_ON", [])
        blocked_by = [dependency for dependency in depends_on if dependency in failed_domains]

        if blocked_by:
            if app_name in CORE_DOMAINS:
                _BOOTSTRAPPED = False
                _DEGRADED_DOMAINS = failed_peripheral
                publish_degraded_domains(_DEGRADED_DOMAINS)
                raise RuntimeError(
                    f"Core domain {app_name} blocked by failed dependency: {blocked_by}"
                )
            logger.warning("Skipping %s: dependency failed: %s", app_name, blocked_by)
            failed_domains.add(app_name)
            failed_peripheral.append(app_name)
            continue

        try:
            mod.register()
            logger.info("Bootstrap OK: %s", app_name)
        except Exception as exc:
            failed_domains.add(app_name)
            if app_name in CORE_DOMAINS:
                _BOOTSTRAPPED = False
                _DEGRADED_DOMAINS = failed_peripheral
                publish_degraded_domains(_DEGRADED_DOMAINS)
                logger.exception("Core domain bootstrap failed for %s: %s", app_name, exc)
                raise RuntimeError(
                    f"Core domain bootstrap failed for {app_name}: {exc}"
                ) from exc
            logger.warning(
                "Peripheral domain bootstrap failed for %s (skipping): %s",
                app_name,
                exc,
                exc_info=True,
            )
            failed_peripheral.append(app_name)

    _DEGRADED_DOMAINS = failed_peripheral
    publish_degraded_domains(_DEGRADED_DOMAINS)
    _BOOTSTRAPPED = True
    if failed_peripheral:
        logger.warning(
            "System started with degraded domains: %s",
            ", ".join(failed_peripheral),
        )


def bootstrap_models() -> None:
    """Backward-compatible entry point - delegates to bootstrap()."""
    bootstrap()
