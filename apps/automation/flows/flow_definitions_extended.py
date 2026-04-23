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
import importlib
import logging

logger = logging.getLogger(__name__)

# Cross-domain modules: failures are isolated — one bad domain does not abort others.
_CROSS_DOMAIN_FLOW_MODULES = [
    "apps.arm.flows.arm_flows",
    "apps.analytics.flows.analytics_flows",
    "apps.agent.flows.agent_flows",
    "apps.freelance.flows.freelance_flows",
    "apps.masterplan.flows.masterplan_flows",
    "apps.search.flows.search_flows",
    "apps.tasks.flows.tasks_flows",
]

# Intra-domain modules within apps.automation.
_INTRA_DOMAIN_FLOW_MODULES = [
    "apps.automation.flows.memory_flows",
    "apps.automation.flows.flow_engine_flows",
    "apps.automation.flows.automation_system_flows",
    "apps.automation.flows.observability_flows",
    "apps.automation.flows.dashboard_autonomy_flows",
]


def register_extended_flows() -> None:
    _register_intra_domain_flows()
    _register_cross_domain_flows()


def _register_intra_domain_flows() -> None:
    from AINDY.platform_layer.registry import register_symbols
    from AINDY.runtime.flow_engine import FLOW_REGISTRY as _default_registry
    from AINDY.runtime.flow_engine import register_flow as _default_register_flow
    from AINDY.runtime import flow_helpers

    # Prefer values injected into this module's globals by the runtime shim (used in
    # tests). Fall back to the canonical imports when no injection is active or when
    # the shim has restored None after a test (its cleanup sets the key to None when
    # the key was absent before injection, so we must treat None as "not injected").
    _g = globals()
    _injected_registry = _g.get("FLOW_REGISTRY")
    FLOW_REGISTRY = _injected_registry if _injected_registry is not None else _default_registry
    _injected_flow = _g.get("register_flow")
    _register_flow = _injected_flow if _injected_flow is not None else _default_register_flow

    automation_flows = importlib.import_module("apps.automation.flows.automation_flows")
    intra_modules = [importlib.import_module(p) for p in _INTRA_DOMAIN_FLOW_MODULES]

    # Inject registry references so intra-domain modules share the same objects.
    flow_helpers.FLOW_REGISTRY = FLOW_REGISTRY
    flow_helpers.register_flow = _register_flow
    automation_flows.FLOW_REGISTRY = FLOW_REGISTRY
    automation_flows.register_flow = _register_flow
    for mod in intra_modules:
        mod.FLOW_REGISTRY = FLOW_REGISTRY
        mod.register_flow = _register_flow

    # Register all public symbols so they're discoverable via the runtime shim.
    all_intra = [flow_helpers, automation_flows, *intra_modules]
    register_symbols(
        {
            name: value
            for mod in all_intra
            for name, value in vars(mod).items()
            if not name.startswith("__")
        }
    )

    if hasattr(automation_flows, "register"):
        automation_flows.register()


def _register_cross_domain_flows() -> None:
    from AINDY.platform_layer.registry import register_symbols
    from AINDY.runtime.flow_engine import FLOW_REGISTRY as _default_registry
    from AINDY.runtime.flow_engine import register_flow as _default_register_flow

    _g = globals()
    _injected_registry = _g.get("FLOW_REGISTRY")
    FLOW_REGISTRY = _injected_registry if _injected_registry is not None else _default_registry
    _injected_flow = _g.get("register_flow")
    _register_flow = _injected_flow if _injected_flow is not None else _default_register_flow

    for module_path in _CROSS_DOMAIN_FLOW_MODULES:
        try:
            mod = importlib.import_module(module_path)
            # Inject registry references in case the module relies on them being set.
            mod.FLOW_REGISTRY = FLOW_REGISTRY
            mod.register_flow = _register_flow
            # Register module's public symbols so they're discoverable via the runtime shim.
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
                    "Flow module %s has no register() function — skipping", module_path
                )
        except Exception as exc:
            logger.error(
                "Flow module %s failed to register (flows from this domain will be "
                "unavailable): %s",
                module_path,
                exc,
                exc_info=True,
            )
