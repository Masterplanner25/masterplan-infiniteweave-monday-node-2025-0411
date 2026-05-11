"""Registry-backed compatibility access to registered flow extension symbols."""

from __future__ import annotations

import importlib
from typing import Any

from AINDY.platform_layer.registry import get_symbol, load_plugins, register_flows, register_symbols

_RUNTIME_SYMBOL_MODULES = [
    "AINDY.runtime.flow_definitions_memory",
    "AINDY.runtime.flow_definitions_engine",
    "AINDY.runtime.flow_definitions_observability",
]


def _resolve_registry_bindings() -> tuple[Any, Any]:
    from AINDY.runtime.flow_engine import FLOW_REGISTRY as _default_registry
    from AINDY.runtime.flow_engine import register_flow as _default_register_flow

    _g = globals()
    flow_registry = _g.get("FLOW_REGISTRY", _default_registry)
    register_flow_fn = _g.get("register_flow", _default_register_flow)
    return flow_registry, register_flow_fn


def _register_runtime_symbols() -> None:
    from AINDY.runtime import flow_helpers

    flow_registry, register_flow_fn = _resolve_registry_bindings()
    runtime_modules = [importlib.import_module(path) for path in _RUNTIME_SYMBOL_MODULES]

    flow_helpers.FLOW_REGISTRY = flow_registry
    flow_helpers.register_flow = register_flow_fn
    for mod in runtime_modules:
        mod.FLOW_REGISTRY = flow_registry
        mod.register_flow = register_flow_fn

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


def _resolve_symbol(name: str) -> Any:
    load_plugins()
    _register_runtime_symbols()
    value = get_symbol(name)
    if value is None:
        # Flow handlers may not have run yet (server lifespan not started). Trigger
        # them now so domain modules are imported and their symbols registered.
        register_flows()
        value = get_symbol(name)
    if value is None:
        raise AttributeError(f"flow extension symbol {name!r} is not registered")
    return value


def register_extended_flows(*args, **kwargs):
    _register_runtime_symbols()
    register_fn = _resolve_symbol("register_extended_flows")
    original_flow_registry = register_fn.__globals__.get("FLOW_REGISTRY")
    original_register_flow = register_fn.__globals__.get("register_flow")
    if "FLOW_REGISTRY" in globals():
        register_fn.__globals__["FLOW_REGISTRY"] = globals()["FLOW_REGISTRY"]
    if "register_flow" in globals():
        register_fn.__globals__["register_flow"] = globals()["register_flow"]
    try:
        return register_fn(*args, **kwargs)
    finally:
        register_fn.__globals__["FLOW_REGISTRY"] = original_flow_registry
        register_fn.__globals__["register_flow"] = original_register_flow


def __getattr__(name: str) -> Any:
    value = _resolve_symbol(name)
    globals()[name] = value
    return value
