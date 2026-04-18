"""Registry-backed compatibility access to registered flow extension symbols."""

from __future__ import annotations

from typing import Any

from AINDY.platform_layer.registry import get_symbol, load_plugins


def _resolve_symbol(name: str) -> Any:
    load_plugins()
    value = get_symbol(name)
    if value is None:
        raise AttributeError(f"flow extension symbol {name!r} is not registered")
    return value


def register_extended_flows(*args, **kwargs):
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
