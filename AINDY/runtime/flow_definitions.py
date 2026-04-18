"""Registry-backed compatibility facade for application flow definitions."""

from __future__ import annotations

from AINDY.platform_layer.registry import get_symbol, load_plugins, register_flows


def register_all_flows() -> None:
    load_plugins()
    register_flows()


def __getattr__(name: str):
    load_plugins()
    symbol = get_symbol(name)
    if symbol is None:
        raise AttributeError(name)
    return symbol
