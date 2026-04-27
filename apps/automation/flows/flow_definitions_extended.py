"""
flow_definitions_extended.py - Hard Execution Boundary node extensions.

Coordinator only. All cross-domain imports are deferred to registration time
so a failure in any single domain does not abort the entire bootstrap.
Domain module symbols are explicitly registered with the platform symbol
registry so they remain discoverable via AINDY.runtime.flow_definitions_extended.

Injection contract: the runtime shim may inject FLOW_REGISTRY and register_flow
into this module's globals for testing. Both helpers check globals() first so
the injected values are propagated to flow_helpers and all sub-modules.
"""
from __future__ import annotations

import importlib
import logging

logger = logging.getLogger(__name__)

_RUNTIME_FLOW_MODULES = [
    "AINDY.runtime.flow_definitions_memory",
    "AINDY.runtime.flow_definitions_engine",
    "AINDY.runtime.flow_definitions_observability",
]

_AUTOMATION_DOMAIN_FLOW_MODULES = [
    "apps.automation.flows.memory_flows",
    "apps.automation.flows.system_flows",
    "apps.automation.flows.dashboard_autonomy_flows",
]

_CROSS_DOMAIN_FLOW_MODULES = [
    "apps.arm.flows.arm_flows",
    "apps.analytics.flows.analytics_flows",
    "apps.agent.flows.agent_flows",
    "apps.freelance.flows.freelance_flows",
    "apps.masterplan.flows.masterplan_flows",
    "apps.search.flows.search_flows",
    "apps.tasks.flows.tasks_flows",
]


def register_extended_flows() -> None:
    _register_runtime_flow_modules()
    _register_automation_domain_flows()
    _register_cross_domain_flows()


def _resolve_registry_bindings():
    from AINDY.runtime.flow_engine import FLOW_REGISTRY as _default_registry
    from AINDY.runtime.flow_engine import register_flow as _default_register_flow

    _g = globals()
    _injected_registry = _g.get("FLOW_REGISTRY")
    flow_registry = _injected_registry if _injected_registry is not None else _default_registry
    _injected_flow = _g.get("register_flow")
    register_flow = _injected_flow if _injected_flow is not None else _default_register_flow
    return flow_registry, register_flow


def _register_runtime_flow_modules() -> None:
    from AINDY.platform_layer.registry import register_symbols
    from AINDY.runtime import flow_helpers

    flow_registry, register_flow = _resolve_registry_bindings()
    runtime_modules = [importlib.import_module(path) for path in _RUNTIME_FLOW_MODULES]

    flow_helpers.FLOW_REGISTRY = flow_registry
    flow_helpers.register_flow = register_flow
    for mod in runtime_modules:
        mod.FLOW_REGISTRY = flow_registry
        mod.register_flow = register_flow

    register_symbols(
        {
            name: value
            for mod in [flow_helpers, *runtime_modules]
            for name, value in vars(mod).items()
            if not name.startswith("__")
        }
    )

    for mod in runtime_modules:
        if hasattr(mod, "register"):
            mod.register()


def _register_automation_domain_flows() -> None:
    from AINDY.platform_layer.registry import register_symbols

    flow_registry, register_flow = _resolve_registry_bindings()
    automation_modules = [importlib.import_module(path) for path in _AUTOMATION_DOMAIN_FLOW_MODULES]

    for mod in automation_modules:
        mod.FLOW_REGISTRY = flow_registry
        mod.register_flow = register_flow

    register_symbols(
        {
            name: value
            for mod in automation_modules
            for name, value in vars(mod).items()
            if not name.startswith("__")
        }
    )

    for mod in automation_modules:
        if hasattr(mod, "register"):
            mod.register()


def _register_cross_domain_flows() -> None:
    from AINDY.platform_layer.registry import register_symbols

    flow_registry, register_flow = _resolve_registry_bindings()

    for module_path in _CROSS_DOMAIN_FLOW_MODULES:
        try:
            mod = importlib.import_module(module_path)
            mod.FLOW_REGISTRY = flow_registry
            mod.register_flow = register_flow
            register_symbols(
                {
                    name: value
                    for name, value in vars(mod).items()
                    if not name.startswith("__")
                }
            )
            if hasattr(mod, "register"):
                mod.register()
            else:
                logger.warning(
                    "Flow module %s has no register() function - skipping", module_path
                )
        except Exception as exc:
            logger.error(
                "Flow module %s failed to register (flows from this domain will be "
                "unavailable): %s",
                module_path,
                exc,
                exc_info=True,
            )
