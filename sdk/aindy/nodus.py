"""
aindy.nodus — Nodus script execution helpers.

Provides a clean interface for running inline Nodus scripts and uploading
named scripts via the platform API.

Example::

    # Run an inline script
    result = client.nodus.run_script(
        '''
        let nodes = sys("sys.v1.memory.read", {query: "sprint goals", limit: 5})
        set_state("goals", nodes.data.nodes)
        emit("goals.loaded", {count: nodes.data.nodes.length})
        ''',
        input={"context": "weekly review"},
    )
    print(result["output_state"])

    # Upload and run a named script
    client.nodus.upload_script("weekly_review", script_source)
    result = client.nodus.run_script(script_name="weekly_review")
"""
from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from aindy.client import AINDYClient

__all__ = ["NodusAPI"]

_NODUS_RUN = "/platform/nodus/run"
_NODUS_UPLOAD = "/platform/nodus/upload"
_NODUS_SCRIPTS = "/platform/nodus/scripts"


class NodusAPI:
    """Nodus script execution and management.

    Args:
        client: The ``AINDYClient`` instance that owns this sub-API.
    """

    def __init__(self, client: "AINDYClient") -> None:
        self._client = client

    def run_script(
        self,
        script: str | None = None,
        script_name: str | None = None,
        input: dict[str, Any] | None = None,  # noqa: A002
        error_policy: str = "fail",
    ) -> dict[str, Any]:
        """Execute a Nodus script (inline source or pre-uploaded name).

        Exactly one of ``script`` or ``script_name`` must be provided.

        Args:
            script:       Inline Nodus source code string.
            script_name:  Name of a previously uploaded script (see ``upload_script``).
            input:        Initial state dict passed into the script.
            error_policy: ``"fail"`` (default) or ``"continue"`` — controls
                          whether a node error halts execution.

        Returns:
            Nodus execution result::

                {
                    "status":              "SUCCESS" | "FAILED",
                    "trace_id":            str,
                    "run_id":              str,
                    "nodus_status":        "success" | "error",
                    "output_state":        dict,
                    "events":              [...],
                    "memory_writes":       [...],
                    "events_emitted":      int,
                    "memory_writes_count": int,
                    "error":               str | None,
                }

        Raises:
            ValueError: If neither ``script`` nor ``script_name`` is provided.

        Example::

            result = client.nodus.run_script(
                'set_state("answer", 42)',
                input={},
            )
            assert result["output_state"]["answer"] == 42
        """
        if script is None and script_name is None:
            raise ValueError("Either 'script' or 'script_name' must be provided.")
        body: dict[str, Any] = {"error_policy": error_policy, "input": input or {}}
        if script is not None:
            body["script"] = script
        else:
            body["script_name"] = script_name
        return self._client.post(_NODUS_RUN, body)

    def upload_script(
        self,
        name: str,
        source: str,
        overwrite: bool = False,
    ) -> dict[str, Any]:
        """Upload a named Nodus script for later execution.

        Args:
            name:      Unique script name. Used in ``run_script(script_name=...)``.
            source:    Nodus source code.
            overwrite: Replace an existing script with the same name.

        Returns:
            ``{"name": str, "size_bytes": int, "created_at": str}``
        """
        return self._client.post(_NODUS_UPLOAD, {
            "name": name,
            "source": source,
            "overwrite": overwrite,
        })

    def list_scripts(self) -> dict[str, Any]:
        """List all uploaded Nodus scripts for the authenticated user.

        Returns:
            ``{"scripts": [{name, size_bytes, created_at}, ...], "count": int}``
        """
        return self._client.get(_NODUS_SCRIPTS)
