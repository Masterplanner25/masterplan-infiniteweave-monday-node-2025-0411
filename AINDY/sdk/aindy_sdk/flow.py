"""
aindy.flow — Flow execution API.

Runs registered Nodus flows by name via the ``sys.v1.flow.run`` syscall.

Example::

    result = client.flow.run(
        "analyze_entities",
        {"nodes": memory_nodes, "mode": "deep"},
    )
    if result["status"] == "success":
        print(result["data"]["output"])
"""
from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from AINDY.sdk.aindy_sdk.syscalls import Syscalls

__all__ = ["FlowAPI"]


class FlowAPI:
    """Flow execution operations.

    Args:
        syscalls: The ``Syscalls`` instance injected by ``AINDYClient``.
    """

    def __init__(self, syscalls: "Syscalls") -> None:
        self._sys = syscalls

    def run(
        self,
        flow_name: str,
        input: dict[str, Any] | None = None,  # noqa: A002
    ) -> dict[str, Any]:
        """Execute a registered Nodus flow by name.

        The flow must be registered in the platform's dynamic flow registry
        (via ``POST /platform/flows``) or compiled at startup.

        Args:
            flow_name: Name of the registered flow to execute.
            input:     Initial state dict passed into the flow (default empty).

        Returns:
            Syscall envelope. ``result["data"]`` contains the flow's final output
            state and any emitted events.

        Example::

            result = client.flow.run("classify_memory", {"query": "sprint goals"})
            classification = result["data"]["classification"]
        """
        return self._sys.call(
            "sys.v1.flow.run",
            {"flow_name": flow_name, "input": input or {}},
        )
