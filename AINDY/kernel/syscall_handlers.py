"""Registry-backed compatibility facade for application syscall handlers."""

from __future__ import annotations

from AINDY.platform_layer.registry import get_symbol, load_plugins


def register_all_domain_handlers() -> None:
    load_plugins()
    register_fn = get_symbol("register_all_domain_handlers")
    if register_fn is None:
        return
    register_fn()


def __getattr__(name: str):
    load_plugins()
    symbol = get_symbol(name)
    if symbol is None:
        raise AttributeError(name)
    return symbol
