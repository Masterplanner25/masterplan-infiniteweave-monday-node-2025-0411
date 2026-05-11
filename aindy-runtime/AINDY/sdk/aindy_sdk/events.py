"""
aindy.events — System event emission API.

Emits ``SystemEvent`` entries via the ``sys.v1.event.emit`` syscall.
Events are durable (persisted to DB) and trigger any registered webhook
subscriptions for the matching event type.

Example::

    client.events.emit(
        "sprint.completed",
        {"sprint": "N+12", "tests": 1420, "coverage": 69.8},
    )
"""
from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from AINDY.sdk.aindy_sdk.syscalls import Syscalls

__all__ = ["EventAPI"]


class EventAPI:
    """System event emission.

    Args:
        syscalls: The ``Syscalls`` instance injected by ``AINDYClient``.
    """

    def __init__(self, syscalls: "Syscalls") -> None:
        self._sys = syscalls

    def emit(
        self,
        event_type: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Emit a system event.

        The event is persisted to the ``system_events`` table and delivered
        to any active webhook subscriptions matching ``event_type`` (exact,
        prefix wildcard ``"execution.*"``, or global wildcard ``"*"``).

        Args:
            event_type: Dot-namespaced event type string, e.g. ``"execution.completed"``.
            payload:    Arbitrary JSON-serialisable metadata (default empty dict).

        Returns:
            Syscall envelope. ``result["data"]["event_id"]`` is the persisted event ID.

        Example::

            client.events.emit(
                "memory.indexed",
                {"path": "/memory/shawn/insights/**", "count": 42},
            )
        """
        return self._sys.call(
            "sys.v1.event.emit",
            {"type": event_type, "payload": payload or {}},
        )
