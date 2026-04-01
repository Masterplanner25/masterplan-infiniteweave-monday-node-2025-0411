"""
aindy.memory — Memory Address Space (MAS) API.

All methods are thin wrappers over the corresponding ``sys.v1.memory.*``
syscalls. Paths follow the MAS structure::

    /memory/{tenant_id}/{namespace}/{addr_type}/{node_id}

Wildcard patterns:
    ``path/*``  — one level (direct children)
    ``path/**`` — recursive (all descendants)

Example::

    # Read all task nodes for the current user
    result = client.memory.read("/memory/shawn/tasks/**")
    for node in result["data"]["nodes"]:
        print(node["content"])

    # Write a new insight
    client.memory.write(
        "/memory/shawn/insights/outcome",
        "Completed sprint N+12 — SDK implemented",
        tags=["sprint", "completed"],
    )
"""
from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from aindy.syscalls import Syscalls

__all__ = ["MemoryAPI"]


class MemoryAPI:
    """Memory Address Space operations.

    Args:
        syscalls: The ``Syscalls`` instance injected by ``AINDYClient``.
    """

    def __init__(self, syscalls: "Syscalls") -> None:
        self._sys = syscalls

    # ── Core operations ───────────────────────────────────────────────────────

    def read(
        self,
        path: str,
        query: str | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        """Read memory nodes by path, optional text query, or both.

        Args:
            path:  MAS path expression. Exact, ``/*`` (one level), or ``/**``
                   (recursive). Pass ``"/memory/{tenant}/**"`` to read all.
            query: Optional free-text filter applied after path resolution.
            limit: Max nodes to return (default 10).

        Returns:
            Syscall envelope. ``result["data"]["nodes"]`` is the node list.
        """
        payload: dict[str, Any] = {"path": path, "limit": limit}
        if query is not None:
            payload["query"] = query
        return self._sys.call("sys.v1.memory.read", payload)

    def write(
        self,
        path: str,
        content: str,
        tags: list[str] | None = None,
        node_type: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Write a memory node at a MAS path.

        The server auto-generates a ``node_id`` if the path ends at
        ``addr_type`` level (no node_id segment). Pass a full path including
        a UUID to overwrite/upsert a specific node.

        Args:
            path:      Target MAS path, e.g. ``"/memory/shawn/insights/outcome"``.
            content:   Text content of the node.
            tags:      Optional list of tag strings.
            node_type: Optional node type (``"decision"``, ``"outcome"``,
                       ``"insight"``, ``"relationship"``). Defaults to ``"insight"``.
            extra:     Optional JSON-serialisable metadata dict.

        Returns:
            Syscall envelope. ``result["data"]["node"]`` is the created/updated node.
        """
        payload: dict[str, Any] = {
            "path": path,
            "content": content,
            "tags": tags or [],
        }
        if node_type is not None:
            payload["node_type"] = node_type
        if extra is not None:
            payload["extra"] = extra
        return self._sys.call("sys.v1.memory.write", payload)

    def search(
        self,
        query: str,
        limit: int = 10,
        node_type: str | None = None,
        min_similarity: float | None = None,
    ) -> dict[str, Any]:
        """Semantic similarity search over memory nodes.

        Args:
            query:          Natural-language search string.
            limit:          Max results (default 10).
            node_type:      Filter by node type.
            min_similarity: Minimum cosine similarity threshold (0.0–1.0).

        Returns:
            Syscall envelope. ``result["data"]["nodes"]`` is the ranked result list,
            each with a ``similarity`` field.
        """
        payload: dict[str, Any] = {"query": query, "limit": limit}
        if node_type is not None:
            payload["node_type"] = node_type
        if min_similarity is not None:
            payload["min_similarity"] = min_similarity
        return self._sys.call("sys.v1.memory.search", payload)

    # ── MAS tree / path operations ────────────────────────────────────────────

    def list(
        self,
        path: str,
        limit: int = 100,
    ) -> dict[str, Any]:
        """List direct children of a MAS path (one level, no recursion).

        Args:
            path:  Parent path, e.g. ``"/memory/shawn/tasks"``.
            limit: Max nodes (default 100).

        Returns:
            Syscall envelope. ``result["data"]["nodes"]`` is the list.
        """
        return self._sys.call("sys.v1.memory.list", {"path": path, "limit": limit})

    def tree(
        self,
        path: str,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Return a hierarchical tree from a MAS path prefix.

        Args:
            path:  Root path prefix to walk recursively.
            limit: Max nodes to include in tree (default 100).

        Returns:
            Syscall envelope. ``result["data"]["tree"]`` is the nested dict;
            ``result["data"]["flat"]`` is the depth-first ordered list.
        """
        return self._sys.call("sys.v1.memory.tree", {"path": path, "limit": limit})

    def trace(
        self,
        path: str,
        depth: int = 5,
    ) -> dict[str, Any]:
        """Follow causal ``source_event_id`` links backward from a node.

        Args:
            path:  Exact path to the starting node.
            depth: Number of hops to follow (default 5, max 10).

        Returns:
            Syscall envelope. ``result["data"]["chain"]`` is the ordered chain.
        """
        return self._sys.call("sys.v1.memory.trace", {"path": path, "depth": depth})
