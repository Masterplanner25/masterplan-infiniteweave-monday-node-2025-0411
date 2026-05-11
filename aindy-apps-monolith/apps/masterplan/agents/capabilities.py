"""Masterplan capability definitions."""

from __future__ import annotations


def register() -> None:
    from AINDY.platform_layer.registry import (
        register_capability_definition,
        register_restricted_tool,
        register_tool_capabilities,
    )

    register_capability_definition(
        "strategic_planning",
        {
            "description": "Modify long-lived planning or genesis state.",
            "risk_level": "high",
        },
    )
    register_tool_capabilities("genesis.message", ["strategic_planning"])
    register_restricted_tool("genesis.message")
