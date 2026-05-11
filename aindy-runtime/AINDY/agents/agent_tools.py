"""Compatibility exports for the generic agent tool registry."""

from AINDY.agents.tool_registry import (
    TOOL_REGISTRY,
    execute_tool,
    get_tool_risk,
    register_tool,
    register_tool_suggestion_provider,
    suggest_tools,
)

try:
    from AINDY.platform_layer.registry import load_plugins

    load_plugins()
except Exception:
    pass

__all__ = [
    "TOOL_REGISTRY",
    "execute_tool",
    "get_tool_risk",
    "register_tool",
    "register_tool_suggestion_provider",
    "suggest_tools",
]
