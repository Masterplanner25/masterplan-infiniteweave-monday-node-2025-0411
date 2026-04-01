"""
aindy.execution — Execution unit introspection API.

Retrieves the status, resource usage, and metadata for an in-flight or
completed execution unit (AgentRun, flow run, Nodus execution).

Example::

    run = client.execution.get("run-abc123")
    print(run["data"]["status"])          # "success" | "running" | "failed"
    print(run["data"]["syscall_count"])   # number of syscalls dispatched
"""
from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from aindy.syscalls import Syscalls

__all__ = ["ExecutionAPI"]


class ExecutionAPI:
    """Execution unit introspection.

    Args:
        syscalls: The ``Syscalls`` instance injected by ``AINDYClient``.
    """

    def __init__(self, syscalls: "Syscalls") -> None:
        self._sys = syscalls

    def get(self, execution_id: str) -> dict[str, Any]:
        """Retrieve status and resource metrics for an execution unit.

        Args:
            execution_id: The ``execution_unit_id`` / ``run_id`` returned by
                          a prior ``flow.run()``, ``nodus.run_script()``, or
                          agent API call.

        Returns:
            Syscall envelope. ``result["data"]`` includes:

            - ``status``        — ``"running"`` | ``"success"`` | ``"failed"`` | ``"waiting"``
            - ``syscall_count`` — total syscalls dispatched
            - ``cpu_time_ms``   — accumulated CPU time
            - ``priority``      — scheduling priority
            - ``quota_group``   — quota tier

        Example::

            info = client.execution.get("run-abc123")
            if info["data"]["status"] == "waiting":
                print("Execution is paused waiting for a signal")
        """
        return self._sys.call(
            "sys.v1.execution.get",
            {"execution_id": execution_id},
        )
