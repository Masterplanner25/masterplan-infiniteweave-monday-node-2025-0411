"""Application plugin bootstrap aggregator with degraded-mode handling.

`BOOTSTRAP_DEPENDS_ON` is the hard startup-order graph used by the runtime.
`APP_DEPENDS_ON` is the broader direct cross-app import graph used for
architecture governance and drift detection.
"""
from __future__ import annotations

import ast
import importlib
import logging
from pathlib import Path
from types import SimpleNamespace

from AINDY.platform_layer.bootstrap_graph import resolve_boot_order
from AINDY.platform_layer.registry import (
    publish_core_domains,
    publish_bootstrap_registration,
    publish_degraded_domains,
)

logger = logging.getLogger(__name__)

_BOOTSTRAPPED = False
_DEGRADED_DOMAINS: list[str] = []
_BOOTSTRAP_METADATA_CACHE: dict[str, dict[str, object]] | None = None

APP_BOOTSTRAP_MODULES: dict[str, str] = {
    "tasks": "apps.tasks.bootstrap",
    "analytics": "apps.analytics.bootstrap",
    "masterplan": "apps.masterplan.bootstrap",
    "automation": "apps.automation.bootstrap",
    "arm": "apps.arm.bootstrap",
    "search": "apps.search.bootstrap",
    "identity": "apps.identity.bootstrap",
    "rippletrace": "apps.rippletrace.bootstrap",
    "social": "apps.social.bootstrap",
    "freelance": "apps.freelance.bootstrap",
    "agent": "apps.agent.bootstrap",
    "authorship": "apps.authorship.bootstrap",
    "bridge": "apps.bridge.bootstrap",
    "autonomy": "apps.autonomy.bootstrap",
    "dashboard": "apps.dashboard.bootstrap",
    "network_bridge": "apps.network_bridge.bootstrap",
}

BOOTSTRAP_DEPENDS_ON_FALLBACKS: dict[str, list[str]] = {
    "tasks": [],
    "analytics": ["identity", "tasks"],
    "masterplan": ["automation", "identity", "tasks"],
    "automation": [],
    "arm": ["analytics"],
    "search": ["analytics"],
    "identity": [],
    "rippletrace": ["analytics", "automation"],
    "social": ["analytics"],
    "freelance": ["automation"],
    "agent": [],
    "authorship": [],
    "bridge": ["automation"],
    "autonomy": [],
    "dashboard": [],
    "network_bridge": ["authorship", "rippletrace"],
}

_ACCEPTED_APP_DEPENDS_ON_GAPS: frozenset[tuple[str, str]] = frozenset({
    ("analytics", "arm"),  # circular after arm -> analytics ordering is declared
})


def _bootstrap_file(app_name: str) -> Path:
    return Path(__file__).resolve().parent / app_name / "bootstrap.py"


def _load_bootstrap_metadata() -> dict[str, dict[str, object]]:
    global _BOOTSTRAP_METADATA_CACHE
    if _BOOTSTRAP_METADATA_CACHE is not None:
        return _BOOTSTRAP_METADATA_CACHE

    metadata: dict[str, dict[str, object]] = {}
    for app_name in APP_BOOTSTRAP_MODULES:
        bootstrap_path = _bootstrap_file(app_name)
        depends_on: list[str] | None = None
        app_depends_on: list[str] = []
        is_core_domain = False
        try:
            tree = ast.parse(bootstrap_path.read_text(encoding="utf-8", errors="ignore"))
            for node in tree.body:
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if getattr(target, "id", None) == "BOOTSTRAP_DEPENDS_ON":
                            depends_on = list(ast.literal_eval(node.value) or [])
                        elif getattr(target, "id", None) == "APP_DEPENDS_ON":
                            app_depends_on = list(ast.literal_eval(node.value) or [])
                        elif getattr(target, "id", None) == "IS_CORE_DOMAIN":
                            is_core_domain = bool(ast.literal_eval(node.value))
                elif isinstance(node, ast.AnnAssign):
                    if getattr(node.target, "id", None) == "BOOTSTRAP_DEPENDS_ON":
                        depends_on = list(ast.literal_eval(node.value) or [])
                    elif getattr(node.target, "id", None) == "APP_DEPENDS_ON":
                        app_depends_on = list(ast.literal_eval(node.value) or [])
                    elif getattr(node.target, "id", None) == "IS_CORE_DOMAIN":
                        is_core_domain = bool(ast.literal_eval(node.value))
        except SyntaxError as exc:
            depends_on = list(BOOTSTRAP_DEPENDS_ON_FALLBACKS.get(app_name, []))
            logger.warning(
                "Bootstrap metadata parse failed for %s; using fallback dependencies %s: %s",
                app_name,
                depends_on,
                exc,
            )
        if depends_on is None:
            raise RuntimeError(f"{bootstrap_path} must declare BOOTSTRAP_DEPENDS_ON")
        metadata[app_name] = {
            "BOOTSTRAP_DEPENDS_ON": depends_on,
            "APP_DEPENDS_ON": app_depends_on,
            "IS_CORE_DOMAIN": is_core_domain,
        }

    _BOOTSTRAP_METADATA_CACHE = metadata
    return metadata


def _bootstrap_graph_nodes() -> dict[str, object]:
    metadata = _load_bootstrap_metadata()
    return {
        app_name: SimpleNamespace(
            BOOTSTRAP_DEPENDS_ON=list(data["BOOTSTRAP_DEPENDS_ON"]),
            APP_DEPENDS_ON=list(data.get("APP_DEPENDS_ON", [])),
            IS_CORE_DOMAIN=bool(data.get("IS_CORE_DOMAIN", False)),
        )
        for app_name, data in metadata.items()
    }


def _import_bootstrap_module(app_name: str) -> object:
    return importlib.import_module(APP_BOOTSTRAP_MODULES[app_name])


def discover_app_bootstraps() -> dict[str, object]:
    return {
        app_name: _import_bootstrap_module(app_name)
        for app_name in APP_BOOTSTRAP_MODULES
    }


def get_resolved_boot_order() -> list[str]:
    return resolve_boot_order(_bootstrap_graph_nodes())


def _get_core_domains_from_metadata() -> frozenset[str]:
    metadata = _load_bootstrap_metadata()
    return frozenset(
        app_name
        for app_name, data in metadata.items()
        if (
            bool(data.get("IS_CORE_DOMAIN", False))
            if isinstance(data, dict)
            else bool(getattr(data, "IS_CORE_DOMAIN", False))
        )
    )


def _check_app_depends_on_ordering() -> list[str]:
    """
    Return warnings for APP_DEPENDS_ON edges where the dependency
    boots after the declaring app in BOOTSTRAP_DEPENDS_ON ordering.
    """
    ordered = get_resolved_boot_order()
    position = {name: idx for idx, name in enumerate(ordered)}
    metadata = _load_bootstrap_metadata()
    warnings = []
    for app_name in ordered:
        app_position = position.get(app_name, -1)
        app_metadata = metadata.get(app_name, SimpleNamespace(APP_DEPENDS_ON=[]))
        if isinstance(app_metadata, dict):
            app_depends_on = list(app_metadata.get("APP_DEPENDS_ON", []))
        else:
            app_depends_on = list(getattr(app_metadata, "APP_DEPENDS_ON", []))
        for dep in app_depends_on:
            if (app_name, dep) in _ACCEPTED_APP_DEPENDS_ON_GAPS:
                continue  # documented circular dependency - deferred calls only
            dep_position = position.get(dep)
            if dep_position is None:
                warnings.append(
                    f"{app_name}: APP_DEPENDS_ON declares '{dep}' but "
                    f"'{dep}' is not in APP_BOOTSTRAP_MODULES"
                )
            elif dep_position > app_position:
                warnings.append(
                    f"{app_name}: APP_DEPENDS_ON declares '{dep}' but "
                    f"'{dep}' boots at position {dep_position} after "
                    f"'{app_name}' at position {app_position}. "
                    f"Add '{dep}' to {app_name}'s BOOTSTRAP_DEPENDS_ON or "
                    f"ensure all calls to '{dep}' are deferred until after "
                    f"bootstrap completes."
                )
    return warnings


def get_degraded_domains() -> list[str]:
    return list(_DEGRADED_DOMAINS)


def bootstrap() -> None:
    global _BOOTSTRAPPED, _DEGRADED_DOMAINS
    if _BOOTSTRAPPED:
        return

    core_domains = _get_core_domains_from_metadata()
    publish_core_domains(core_domains)
    publish_degraded_domains(())
    ordered_apps = get_resolved_boot_order()
    metadata = _load_bootstrap_metadata()
    logger.info("Boot order resolved: %s", " -> ".join(ordered_apps))
    # Accepted APP_DEPENDS_ON gaps:
    # - analytics -> arm cannot be added once arm -> analytics is declared,
    #   because that would create an analytics <-> arm cycle.
    # - bridge -> automation cannot be added because automation already
    #   depends on other boot-time upstreams and the validator sees a cycle
    #   once bridge points back at automation.
    # In all accepted cases the calls are deferred inside service functions and never
    # run during register(), so the warnings are structurally accepted and
    # suppressed to avoid startup noise.
    _ordering_warnings = _check_app_depends_on_ordering()
    for _warning in _ordering_warnings:
        logger.warning("[bootstrap] APP_DEPENDS_ON ordering gap: %s", _warning)

    failed_domains: set[str] = set()
    failed_peripheral: list[str] = []

    for app_name in ordered_apps:
        depends_on = list(metadata[app_name]["BOOTSTRAP_DEPENDS_ON"])
        blocked_by = [dependency for dependency in depends_on if dependency in failed_domains]

        if blocked_by and app_name in core_domains:
            _BOOTSTRAPPED = False
            _DEGRADED_DOMAINS = failed_peripheral
            publish_degraded_domains(_DEGRADED_DOMAINS)
            raise RuntimeError(
                f"Core domain {app_name} blocked by failed dependency: {blocked_by}"
            )

        if blocked_by:
            logger.warning(
                "Peripheral domain %s has failed dependency %s; attempting bootstrap anyway.",
                app_name,
                blocked_by,
            )

        try:
            mod = _import_bootstrap_module(app_name)
            mod.register()
            publish_bootstrap_registration(app_name, depends_on)
            logger.info("Bootstrap OK: %s", app_name)
        except Exception as exc:
            failed_domains.add(app_name)
            if app_name in core_domains:
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
