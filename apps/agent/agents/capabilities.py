"""Generic agent capability definitions."""

from __future__ import annotations


def register() -> None:
    from AINDY.platform_layer.registry import (
        register_agent_capabilities,
        register_capability_definition,
        register_tool_capabilities,
    )

    register_capability_definition(
        "execute_flow",
        {
            "description": "Start and continue a scoped workflow execution.",
            "risk_level": "low",
        },
    )
    register_capability_definition(
        "read_memory",
        {
            "description": "Read memory and recall prior context.",
            "risk_level": "low",
        },
    )
    register_capability_definition(
        "write_memory",
        {
            "description": "Create or update durable memory.",
            "risk_level": "low",
        },
    )
    register_agent_capabilities("default", ["execute_flow"])
    register_tool_capabilities("memory.recall", ["read_memory"])
    register_tool_capabilities("memory.write", ["write_memory"])
