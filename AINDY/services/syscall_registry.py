"""
Syscall Registry — A.I.N.D.Y. system call table.

Maps sys.v{N}.{domain}.{action} names to handler functions, required
capabilities, and ABI contracts.  Handlers are plain callables — no HTTP,
no FastAPI dependencies.

Registry structure
------------------
``SYSCALL_REGISTRY`` is a ``VersionedSyscallRegistry`` that supports both:

Flat key access (backward compatible)::

    entry = SYSCALL_REGISTRY["sys.v1.memory.read"]
    SYSCALL_REGISTRY["sys.v2.memory.read"] = SyscallEntry(...)

Versioned view::

    view = SYSCALL_REGISTRY.versioned        # {"v1": {"memory.read": entry}, …}
    v1   = SYSCALL_REGISTRY.get_version("v1")

Handler contract
----------------
Every handler must accept (payload: dict, context: SyscallContext) -> dict.
Handlers may raise — the dispatcher catches and wraps all exceptions.
Handlers must open their own DB sessions (never receive one as an argument)
so they remain safe across execution contexts and tests.

ABI contract
------------
Each SyscallEntry carries:
  input_schema  — lightweight schema validated before execution
  output_schema — shape validated after execution (non-fatal)
  stable        — False marks the syscall as experimental
  deprecated    — True causes the dispatcher to emit a warning
  replacement   — full syscall name callers should migrate to
"""
from __future__ import annotations

import logging
from collections.abc import MutableMapping
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator

logger = logging.getLogger(__name__)


# ── Execution context ─────────────────────────────────────────────────────────

@dataclass
class SyscallContext:
    """Immutable execution context passed into every syscall handler.

    Built by the dispatcher caller (e.g. NodusRuntimeAdapter) before
    dispatching. Handlers must not mutate this object.

    Attributes:
        execution_unit_id: Correlates to the active ExecutionUnit / FlowRun.
        user_id:           Authenticated caller; used for ownership enforcement.
        capabilities:      Explicit set of granted syscall capabilities.
        trace_id:          Propagated trace ID (equals execution_unit_id in
                           standard PersistentFlowRunner runs).
        memory_context:    Pre-loaded memory nodes available to the script.
        metadata:          Arbitrary caller-supplied key/value pairs.
    """
    execution_unit_id: str
    user_id: str
    capabilities: list[str]
    trace_id: str
    memory_context: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


# ── Capability constants ──────────────────────────────────────────────────────

# Default capability set granted to all Nodus script executions.
DEFAULT_NODUS_CAPABILITIES: list[str] = [
    "memory.read",
    "memory.write",
    "memory.search",
    "event.emit",
]


# ── Registry entry ────────────────────────────────────────────────────────────

class SyscallEntry:
    """Binds a handler callable to its required capability and ABI contract.

    All parameters after *description* are optional and default to safe values
    so existing code that constructs ``SyscallEntry(handler, capability)``
    continues to work without any changes.
    """

    __slots__ = (
        "handler", "capability", "description",
        "input_schema", "output_schema",
        "stable", "deprecated", "deprecated_since", "replacement",
    )

    def __init__(
        self,
        handler: Callable[[dict, SyscallContext], dict],
        capability: str,
        description: str = "",
        input_schema: dict | None = None,
        output_schema: dict | None = None,
        stable: bool = True,
        deprecated: bool = False,
        deprecated_since: str | None = None,
        replacement: str | None = None,
    ) -> None:
        self.handler = handler
        self.capability = capability
        self.description = description
        self.input_schema: dict = input_schema or {}
        self.output_schema: dict = output_schema or {}
        self.stable = stable
        self.deprecated = deprecated
        self.deprecated_since = deprecated_since
        self.replacement = replacement

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"SyscallEntry(capability={self.capability!r}, "
            f"handler={self.handler.__name__!r}, "
            f"deprecated={self.deprecated!r})"
        )


# ── Versioned registry ────────────────────────────────────────────────────────

class VersionedSyscallRegistry(MutableMapping):
    """MutableMapping that supports BOTH flat and versioned access patterns.

    **Flat access (backward compatible)**::

        registry["sys.v1.memory.read"]       # → SyscallEntry
        registry["sys.v1.memory.read"] = e   # write
        del registry["sys.v1.memory.read"]   # delete
        registry.get("sys.v1.memory.read")   # get-with-default
        "sys.v1.memory.read" in registry     # containment
        list(registry.keys())                # all registered full names

    **Versioned access**::

        registry.versioned                   # {"v1": {"memory.read": e}, …}
        registry.get_version("v1")           # {"memory.read": entry, …}
        registry.versions()                  # ["v1", "v2", …]

    Write operations (``__setitem__``, ``__delitem__``, ``pop``) keep
    both views in sync automatically.
    """

    def __init__(self) -> None:
        self._flat: dict[str, SyscallEntry] = {}
        self._versioned: dict[str, dict[str, SyscallEntry]] = {}

    # ── dict-like interface ────────────────────────────────────────────────

    @staticmethod
    def _split(key: str) -> tuple[str | None, str | None]:
        """Return (version, action) from 'sys.v1.memory.read', or (None, None)."""
        if not key.startswith("sys."):
            return None, None
        rest = key[4:]
        dot = rest.find(".")
        if dot == -1:
            return None, None
        return rest[:dot], rest[dot + 1:]

    def __getitem__(self, key: str) -> SyscallEntry:
        return self._flat[key]

    def __setitem__(self, key: str, value: SyscallEntry) -> None:
        self._flat[key] = value
        version, action = self._split(key)
        if version and action:
            if version not in self._versioned:
                self._versioned[version] = {}
            self._versioned[version][action] = value

    def __delitem__(self, key: str) -> None:
        del self._flat[key]
        version, action = self._split(key)
        if version and action and version in self._versioned:
            self._versioned[version].pop(action, None)
            if not self._versioned[version]:
                del self._versioned[version]

    def __iter__(self) -> Iterator[str]:
        return iter(self._flat)

    def __len__(self) -> int:
        return len(self._flat)

    def __contains__(self, key: object) -> bool:
        return key in self._flat

    def pop(self, key: str, *args) -> SyscallEntry:  # type: ignore[override]
        val = self._flat.pop(key, *args)
        version, action = self._split(key)
        if version and action and version in self._versioned:
            self._versioned[version].pop(action, None)
            if not self._versioned[version]:
                del self._versioned[version]
        return val

    # ── Versioned views ────────────────────────────────────────────────────

    @property
    def versioned(self) -> dict[str, dict[str, SyscallEntry]]:
        """Return a shallow copy of the versioned registry."""
        return {v: dict(actions) for v, actions in self._versioned.items()}

    def get_version(self, version: str) -> dict[str, SyscallEntry]:
        """Return all entries registered under *version*."""
        return dict(self._versioned.get(version, {}))

    def versions(self) -> list[str]:
        """Return a sorted list of registered version strings."""
        return sorted(self._versioned.keys())


# ── Handlers ──────────────────────────────────────────────────────────────────
# Each handler:
#   - Accepts (payload: dict, context: SyscallContext)
#   - Returns a plain dict (becomes the "data" field in the response envelope)
#   - Opens its own SessionLocal — never receives a DB session as an argument
#   - May raise ValueError for bad payload; other exceptions = handler failure


def _handle_memory_read(payload: dict, context: SyscallContext) -> dict:
    """sys.v1.memory.read — recall memory nodes for the calling user.

    Payload keys (all optional):
        path      (str)        — MAS path or wildcard expression (overrides tag/query if exact)
        query     (str)        — semantic search string
        tags      (list[str])  — tag filter
        limit     (int)        — max results, default 5
        node_type (str)        — filter by node_type
    """
    from db.database import SessionLocal
    from db.dao.memory_node_dao import MemoryNodeDAO

    path: str | None = payload.get("path")
    query: str | None = payload.get("query")
    tags: list | None = payload.get("tags")
    limit: int = int(payload.get("limit", 5))
    node_type: str | None = payload.get("node_type")

    db = SessionLocal()
    try:
        dao = MemoryNodeDAO(db)
        if path:
            nodes = dao.query_path(
                path_expr=path,
                query=query,
                tags=tags,
                user_id=context.user_id,
                limit=limit,
            )
        else:
            nodes = dao.recall(
                query=query,
                tags=tags,
                limit=limit,
                user_id=context.user_id,
                node_type=node_type,
            )
        return {"nodes": nodes, "count": len(nodes)}
    finally:
        db.close()


def _handle_memory_write(payload: dict, context: SyscallContext) -> dict:
    """sys.v1.memory.write — persist a new memory node for the calling user.

    Payload keys:
        content      (str)        — required; node text
        tags         (list[str])  — optional; classification tags
        node_type    (str)        — default "execution"
        significance (float)      — relevance weight 0.0-1.0, default 0.5
        path         (str)        — optional MAS path; auto-generated if omitted
        namespace    (str)        — optional namespace segment
        addr_type    (str)        — optional sub-category segment
    """
    from db.database import SessionLocal
    from db.dao.memory_node_dao import MemoryNodeDAO
    from services.memory_address_space import path_from_write_payload

    content: str = payload.get("content", "")
    if not content:
        raise ValueError("sys.v1.memory.write requires non-empty 'content'")

    tags: list = payload.get("tags") or []
    node_type: str = payload.get("node_type", "execution")
    source: str = payload.get("source", "syscall")

    full_path, namespace, addr_type = path_from_write_payload(
        {**payload, "node_type": node_type},
        tenant_id=str(context.user_id),
    )
    from services.memory_address_space import parent_path_of
    parent_path = parent_path_of(full_path)

    db = SessionLocal()
    try:
        dao = MemoryNodeDAO(db)
        node = dao.save(
            content=content,
            tags=tags,
            user_id=context.user_id,
            node_type=node_type,
            source=source,
            source_agent="syscall_dispatcher",
            extra={"execution_unit_id": context.execution_unit_id},
            path=full_path,
            namespace=namespace,
            addr_type=addr_type,
            parent_path=parent_path,
        )
        return {"node": node, "path": full_path}
    finally:
        db.close()


def _handle_memory_search(payload: dict, context: SyscallContext) -> dict:
    """sys.v1.memory.search — semantic search over the user's memory nodes.

    Payload keys:
        query  (str) — required; search string
        limit  (int) — max results, default 5
        path   (str) — optional MAS path prefix to scope the search
    """
    from db.database import SessionLocal
    from db.dao.memory_node_dao import MemoryNodeDAO

    query: str = payload.get("query", "")
    if not query:
        raise ValueError("sys.v1.memory.search requires non-empty 'query'")
    limit: int = int(payload.get("limit", 5))
    path: str | None = payload.get("path")

    db = SessionLocal()
    try:
        dao = MemoryNodeDAO(db)
        if path:
            nodes = dao.query_path(
                path_expr=path,
                query=query,
                user_id=context.user_id,
                limit=limit,
            )
        else:
            nodes = dao.recall(
                query=query,
                limit=limit,
                user_id=context.user_id,
            )
        return {"nodes": nodes, "count": len(nodes)}
    finally:
        db.close()


def _handle_memory_list(payload: dict, context: SyscallContext) -> dict:
    """sys.v1.memory.list — list nodes at a MAS path (one level or recursive).

    Payload keys:
        path      (str) — required; MAS prefix (use /* for one level, /** for recursive)
        limit     (int) — max results, default 50
    """
    from db.database import SessionLocal
    from db.dao.memory_node_dao import MemoryNodeDAO

    path: str = payload.get("path", "")
    if not path:
        raise ValueError("sys.v1.memory.list requires 'path'")
    limit: int = int(payload.get("limit", 50))

    db = SessionLocal()
    try:
        dao = MemoryNodeDAO(db)
        nodes = dao.query_path(path_expr=path, user_id=context.user_id, limit=limit)
        return {"nodes": nodes, "count": len(nodes), "path": path}
    finally:
        db.close()


def _handle_memory_tree(payload: dict, context: SyscallContext) -> dict:
    """sys.v1.memory.tree — return a hierarchical tree of nodes under a path.

    Payload keys:
        path  (str) — required; MAS prefix
        limit (int) — max nodes to fetch before building tree, default 200
    """
    from db.database import SessionLocal
    from db.dao.memory_node_dao import MemoryNodeDAO
    from services.memory_address_space import build_tree, wildcard_prefix, is_exact, normalize_path

    path: str = payload.get("path", "")
    if not path:
        raise ValueError("sys.v1.memory.tree requires 'path'")
    limit: int = int(payload.get("limit", 200))

    db = SessionLocal()
    try:
        dao = MemoryNodeDAO(db)
        if is_exact(path):
            nodes = dao.walk_path(normalize_path(path), user_id=context.user_id, limit=limit)
        else:
            nodes = dao.walk_path(wildcard_prefix(path), user_id=context.user_id, limit=limit)
        tree = build_tree(nodes)
        return {"tree": tree, "node_count": len(nodes), "path": path}
    finally:
        db.close()


def _handle_memory_trace(payload: dict, context: SyscallContext) -> dict:
    """sys.v1.memory.trace — follow the causal chain from a node at a path.

    Payload keys:
        path   (str) — required; exact MAS path to start from
        depth  (int) — max hops to follow, default 5
    """
    from db.database import SessionLocal
    from db.dao.memory_node_dao import MemoryNodeDAO

    path: str = payload.get("path", "")
    if not path:
        raise ValueError("sys.v1.memory.trace requires 'path'")
    depth: int = int(payload.get("depth", 5))

    db = SessionLocal()
    try:
        dao = MemoryNodeDAO(db)
        chain = dao.causal_trace(path=path, depth=depth, user_id=context.user_id)
        return {"chain": chain, "depth": len(chain), "path": path}
    finally:
        db.close()


def _handle_flow_run(payload: dict, context: SyscallContext) -> dict:
    """sys.v1.flow.run — execute a registered flow by name.

    Payload keys:
        flow_name     (str)  — required; must exist in FLOW_REGISTRY
        initial_state (dict) — optional; passed to PersistentFlowRunner.start()
        workflow_type (str)  — optional; default "syscall"
    """
    from db.database import SessionLocal
    from services.flow_engine import FLOW_REGISTRY, PersistentFlowRunner

    flow_name: str = payload.get("flow_name", "")
    if not flow_name:
        raise ValueError("sys.v1.flow.run requires 'flow_name'")

    flow = FLOW_REGISTRY.get(flow_name)
    if flow is None:
        raise ValueError(f"sys.v1.flow.run: unknown flow '{flow_name}'")

    initial_state: dict = payload.get("initial_state") or {}
    workflow_type: str = payload.get("workflow_type", "syscall")

    db = SessionLocal()
    try:
        runner = PersistentFlowRunner(
            flow=flow,
            db=db,
            user_id=context.user_id,
            workflow_type=workflow_type,
        )
        result = runner.start(initial_state, flow_name=flow_name)
        return {"flow_result": result}
    finally:
        db.close()


def _handle_event_emit(payload: dict, context: SyscallContext) -> dict:
    """sys.v1.event.emit — emit a SystemEvent on the A.I.N.D.Y. event bus.

    Payload keys:
        event_type (str)  — required; e.g. "task.completed"
        payload    (dict) — optional; merged into the event payload
    """
    from db.database import SessionLocal
    from services.system_event_service import emit_system_event

    event_type: str = payload.get("event_type", "")
    if not event_type:
        raise ValueError("sys.v1.event.emit requires 'event_type'")

    event_payload: dict = payload.get("payload") or {}

    db = SessionLocal()
    try:
        event_id = emit_system_event(
            db=db,
            event_type=event_type,
            user_id=context.user_id,
            trace_id=context.trace_id,
            source="syscall_dispatcher",
            payload={
                **event_payload,
                "execution_unit_id": context.execution_unit_id,
            },
        )
        db.commit()
        return {"event_id": str(event_id) if event_id else None}
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# ── Example v2 handler ────────────────────────────────────────────────────────
# Demonstrates ABI evolution: v2.memory.read adds structured ``filters``
# without breaking the v1 interface.

def _handle_memory_read_v2(payload: dict, context: SyscallContext) -> dict:
    """sys.v2.memory.read — enhanced recall with structured field filters.

    Extends v1 with:
        filters (dict) — optional; key/value field filters applied after recall.
            Supported keys: memory_type, node_type, min_impact (float).

    All v1 payload keys remain valid.  If *filters* is absent the response is
    identical to sys.v1.memory.read.
    """
    from db.database import SessionLocal
    from db.dao.memory_node_dao import MemoryNodeDAO

    path: str | None = payload.get("path")
    query: str | None = payload.get("query")
    tags: list | None = payload.get("tags")
    limit: int = int(payload.get("limit", 5))
    node_type: str | None = payload.get("node_type")
    filters: dict = payload.get("filters") or {}

    db = SessionLocal()
    try:
        dao = MemoryNodeDAO(db)
        if path:
            nodes = dao.query_path(path_expr=path, query=query, tags=tags,
                                   user_id=context.user_id, limit=limit)
        else:
            nodes = dao.recall(query=query, tags=tags, limit=limit * 2,
                               user_id=context.user_id, node_type=node_type)

        # Apply structured filters (v2 extension)
        if filters:
            if "memory_type" in filters:
                nodes = [n for n in nodes if n.get("memory_type") == filters["memory_type"]]
            if "node_type" in filters:
                nodes = [n for n in nodes if n.get("node_type") == filters["node_type"]]
            if "min_impact" in filters:
                min_imp = float(filters["min_impact"])
                nodes = [n for n in nodes if (n.get("impact_score") or 0.0) >= min_imp]

        return {"nodes": nodes[:limit], "count": min(len(nodes), limit), "version": "v2"}
    finally:
        db.close()


# ── Registry ──────────────────────────────────────────────────────────────────

SYSCALL_REGISTRY: VersionedSyscallRegistry = VersionedSyscallRegistry()

# ── v1 built-in syscalls ──────────────────────────────────────────────────────

SYSCALL_REGISTRY["sys.v1.memory.read"] = SyscallEntry(
    handler=_handle_memory_read,
    capability="memory.read",
    description="Recall memory nodes for the calling user.",
    input_schema={
        "properties": {
            "query": {"type": "string"},
            "tags": {"type": "list"},
            "limit": {"type": "int"},
            "node_type": {"type": "string"},
            "path": {"type": "string"},
        }
    },
    output_schema={
        "required": ["nodes", "count"],
        "properties": {"nodes": {"type": "list"}, "count": {"type": "int"}},
    },
)
SYSCALL_REGISTRY["sys.v1.memory.write"] = SyscallEntry(
    handler=_handle_memory_write,
    capability="memory.write",
    description="Persist a new memory node.",
    input_schema={
        "required": ["content"],
        "properties": {
            "content": {"type": "string"},
            "tags": {"type": "list"},
            "node_type": {"type": "string"},
            "path": {"type": "string"},
        },
    },
    output_schema={
        "required": ["node"],
        "properties": {"node": {"type": "dict"}, "path": {"type": "string"}},
    },
)
SYSCALL_REGISTRY["sys.v1.memory.search"] = SyscallEntry(
    handler=_handle_memory_search,
    capability="memory.search",
    description="Semantic search over user memory nodes.",
    input_schema={
        "required": ["query"],
        "properties": {
            "query": {"type": "string"},
            "limit": {"type": "int"},
            "path": {"type": "string"},
        },
    },
    output_schema={
        "required": ["nodes", "count"],
        "properties": {"nodes": {"type": "list"}, "count": {"type": "int"}},
    },
)
SYSCALL_REGISTRY["sys.v1.memory.list"] = SyscallEntry(
    handler=_handle_memory_list,
    capability="memory.list",
    description="List nodes at a MAS path prefix.",
    input_schema={
        "required": ["path"],
        "properties": {"path": {"type": "string"}, "limit": {"type": "int"}},
    },
    output_schema={
        "required": ["nodes", "count"],
        "properties": {"nodes": {"type": "list"}, "count": {"type": "int"}},
    },
)
SYSCALL_REGISTRY["sys.v1.memory.tree"] = SyscallEntry(
    handler=_handle_memory_tree,
    capability="memory.tree",
    description="Return a hierarchical tree of nodes under a path.",
    input_schema={
        "required": ["path"],
        "properties": {"path": {"type": "string"}, "limit": {"type": "int"}},
    },
    output_schema={
        "required": ["tree", "node_count"],
        "properties": {"tree": {"type": "dict"}, "node_count": {"type": "int"}},
    },
)
SYSCALL_REGISTRY["sys.v1.memory.trace"] = SyscallEntry(
    handler=_handle_memory_trace,
    capability="memory.trace",
    description="Follow the causal chain from a node at a path.",
    input_schema={
        "required": ["path"],
        "properties": {"path": {"type": "string"}, "depth": {"type": "int"}},
    },
    output_schema={
        "required": ["chain", "depth"],
        "properties": {"chain": {"type": "list"}, "depth": {"type": "int"}},
    },
)
SYSCALL_REGISTRY["sys.v1.flow.run"] = SyscallEntry(
    handler=_handle_flow_run,
    capability="flow.run",
    description="Execute a registered flow by name.",
    input_schema={
        "required": ["flow_name"],
        "properties": {
            "flow_name": {"type": "string"},
            "initial_state": {"type": "dict"},
        },
    },
)
SYSCALL_REGISTRY["sys.v1.event.emit"] = SyscallEntry(
    handler=_handle_event_emit,
    capability="event.emit",
    description="Emit a SystemEvent on the A.I.N.D.Y. event bus.",
    input_schema={
        "required": ["event_type"],
        "properties": {
            "event_type": {"type": "string"},
            "payload": {"type": "dict"},
        },
    },
)

# ── v2 syscalls ───────────────────────────────────────────────────────────────
# v2 extends v1 capabilities without removing or changing existing fields.

SYSCALL_REGISTRY["sys.v2.memory.read"] = SyscallEntry(
    handler=_handle_memory_read_v2,
    capability="memory.read",
    description="Enhanced memory recall with structured field filters (v2).",
    input_schema={
        "properties": {
            "query": {"type": "string"},
            "tags": {"type": "list"},
            "limit": {"type": "int"},
            "node_type": {"type": "string"},
            "path": {"type": "string"},
            "filters": {"type": "dict"},   # v2 extension — optional
        }
    },
    output_schema={
        "required": ["nodes", "count"],
        "properties": {
            "nodes": {"type": "list"},
            "count": {"type": "int"},
            "version": {"type": "string"},
        },
    },
)


def register_syscall(
    name: str,
    handler: Callable[[dict, SyscallContext], dict],
    capability: str,
    description: str = "",
    input_schema: dict | None = None,
    output_schema: dict | None = None,
    stable: bool = True,
    deprecated: bool = False,
    deprecated_since: str | None = None,
    replacement: str | None = None,
) -> None:
    """Register a syscall at runtime.

    Idempotent — registering the same name twice overwrites the entry.
    Not thread-safe for concurrent writes (startup-only use case).

    Args:
        name:             Fully-qualified name (must start with ``"sys."``).
        handler:          Callable(payload, context) → dict.
        capability:       Required capability string.
        description:      Human-readable description.
        input_schema:     Optional input validation schema.
        output_schema:    Optional output validation schema.
        stable:           False marks the syscall as experimental.
        deprecated:       True causes the dispatcher to emit a warning.
        deprecated_since: Version string when deprecation was introduced.
        replacement:      Full name of the replacement syscall.

    Raises:
        ValueError: If name does not start with ``"sys."``.
    """
    if not name.startswith("sys."):
        raise ValueError(
            f"Syscall name must start with 'sys.', got: {name!r}"
        )
    SYSCALL_REGISTRY[name] = SyscallEntry(
        handler=handler,
        capability=capability,
        description=description,
        input_schema=input_schema,
        output_schema=output_schema,
        stable=stable,
        deprecated=deprecated,
        deprecated_since=deprecated_since,
        replacement=replacement,
    )
    logger.debug(
        "[syscall_registry] registered '%s' (capability=%s, deprecated=%s)",
        name, capability, deprecated,
    )
