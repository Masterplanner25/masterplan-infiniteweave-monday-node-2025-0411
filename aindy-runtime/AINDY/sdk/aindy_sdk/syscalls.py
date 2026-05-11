"""
aindy.syscalls — raw syscall dispatch.

All higher-level APIs (memory, flow, events, execution) delegate to
``Syscalls.call()``. Use this directly only when you need a syscall that
has no higher-level wrapper yet.
"""
from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from AINDY.sdk.aindy_sdk.client import AINDYClient

__all__ = ["Syscalls"]

_SYSCALL_ENDPOINT = "/platform/syscall"


class Syscalls:
    """Raw syscall dispatcher.

    Args:
        client: The ``AINDYClient`` instance that owns this sub-API.

    Example::

        result = client.syscalls.call(
            "sys.v1.memory.read",
            {"query": "authentication flow", "limit": 5},
        )
        assert result["status"] == "success"
        nodes = result["data"]["nodes"]
    """

    def __init__(self, client: "AINDYClient") -> None:
        self._client = client

    def call(
        self,
        name: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Dispatch a syscall and return the standard response envelope.

        Args:
            name:    Fully-qualified syscall name — ``"sys.v{N}.{domain}.{action}"``.
            payload: Syscall-specific arguments.

        Returns:
            Standard response envelope::

                {
                    "status":            "success" | "error",
                    "data":              dict,
                    "version":           str,
                    "warning":           str | None,
                    "trace_id":          str,
                    "execution_unit_id": str,
                    "syscall":           str,
                    "duration_ms":       int,
                    "error":             str | None,
                }

        Raises:
            ValidationError:      The syscall name is malformed or the payload
                                  fails input schema validation.
            PermissionDeniedError: The API key lacks the required capability.
            ResourceLimitError:   Execution quota exceeded.
            AINDYError:           Any other error returned by the server.
        """
        return self._client.post(
            _SYSCALL_ENDPOINT,
            {"name": name, "payload": payload},
        )

    def list(self, version: str | None = None) -> dict[str, Any]:
        """Return available syscalls with their ABI schemas.

        Args:
            version: Optional version filter, e.g. ``"v1"``.

        Returns:
            ``{versions, syscalls, total_count}``
        """
        params = {"version": version} if version else None
        return self._client.get("/platform/syscalls", params=params)
