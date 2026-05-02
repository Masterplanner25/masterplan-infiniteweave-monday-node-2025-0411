"""
flow_definitions_extended.py - Hard Execution Boundary node extensions.

Coordinator only. All cross-domain imports are deferred to registration time
so a failure in any single domain does not abort the entire bootstrap.
App flow module symbols are explicitly registered with the platform symbol
registry so they remain discoverable via AINDY.runtime.flow_definitions_extended.

Injection contract: the runtime shim may inject FLOW_REGISTRY and register_flow
into this module's globals for testing. Both helpers check globals() first so
the injected values are propagated to flow_helpers and all sub-modules.
"""
from __future__ import annotations

import importlib
import logging

logger = logging.getLogger(__name__)

_AUTOMATION_DOMAIN_FLOW_MODULES = [
    "apps.automation.flows.memory_flows",
    "apps.automation.flows.system_flows",
    "apps.automation.flows.dashboard_autonomy_flows",
]

def register_extended_flows() -> None:
    _register_automation_domain_flows()


def _resolve_registry_bindings():
    from AINDY.runtime.flow_engine import FLOW_REGISTRY as _default_registry
    from AINDY.runtime.flow_engine import register_flow as _default_register_flow

    _g = globals()
    _injected_registry = _g.get("FLOW_REGISTRY")
    flow_registry = _injected_registry if _injected_registry is not None else _default_registry
    _injected_flow = _g.get("register_flow")
    register_flow = _injected_flow if _injected_flow is not None else _default_register_flow
    return flow_registry, register_flow


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
