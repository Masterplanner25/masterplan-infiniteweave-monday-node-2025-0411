"""Generic agent capability definitions."""

from __future__ import annotations


def _capability_bundle() -> dict:
    return {
        "definitions": {
            "execute_flow": {
                "description": "Start and continue a scoped workflow execution.",
                "risk_level": "low",
            },
            "read_memory": {
                "description": "Read memory and recall prior context.",
                "risk_level": "low",
            },
            "write_memory": {
                "description": "Create or update durable memory.",
                "risk_level": "low",
            },
        },
        "tool_capabilities": {
            "memory.recall": ["read_memory"],
            "memory.write": ["write_memory"],
        },
        "agent_capabilities": {
            "default": ["execute_flow"],
        },
    }


def register() -> None:
    from AINDY.platform_layer.registry import register_capability_definition_provider

    register_capability_definition_provider(_capability_bundle)
