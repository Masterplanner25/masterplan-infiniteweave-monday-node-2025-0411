"""Task capability definitions."""

from __future__ import annotations


def register() -> None:
    from AINDY.platform_layer.registry import register_capability_definition, register_tool_capabilities

    register_capability_definition(
        "manage_tasks",
        {
            "description": "Create or update task state.",
            "risk_level": "low",
        },
    )
    register_tool_capabilities("task.create", ["manage_tasks"])
    register_tool_capabilities("task.complete", ["manage_tasks"])
