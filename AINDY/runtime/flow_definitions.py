"""Runtime-owned registration for platform flow definitions."""

from __future__ import annotations

from typing import Any

from AINDY.platform_layer.registry import get_symbol


def register_all_flows() -> None:
    from AINDY.runtime import (
        flow_definitions_engine,
        flow_definitions_memory,
        flow_definitions_observability,
    )

    flow_definitions_memory.register()
    flow_definitions_engine.register()
    flow_definitions_observability.register()


def __getattr__(name: str) -> Any:
    symbol = get_symbol(name)
    if symbol is None:
        raise AttributeError(name)
    return symbol
