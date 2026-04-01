"""
Memory Address Space (MAS) — A.I.N.D.Y. Filesystem-Like Memory Layer

Transforms MemoryNode access from tag/semantic-only to a hierarchical,
path-addressable namespace system.

Path structure
--------------
    /memory/{tenant_id}/{namespace}/{addr_type}/{node_id}

    tenant_id  — user ID (tenant isolation boundary)
    namespace  — logical domain: "tasks", "insights", "decisions", "goals", …
    addr_type  — sub-category: "pending", "completed", "architectural", …
    node_id    — UUID of the memory node (generated on write)

Query patterns
--------------
    /memory/user-123/tasks/pending/abc      → exact match (one node)
    /memory/user-123/tasks/*               → all nodes one level under tasks
    /memory/user-123/tasks/**              → recursive — all nodes under tasks
    /memory/user-123/tasks/pending/*       → all nodes of type "pending"

Hybrid query
------------
    path + query + tags + causal_depth can all be combined:
    {
        "path":  "/memory/user-123/tasks/*",
        "query": "failed with timeout",
        "tags":  ["error"],
        "limit": 10
    }

Backward compatibility
----------------------
Legacy MemoryNodes that predate MAS have path == NULL.  Their canonical
address is DERIVED on-the-fly using derive_legacy_path(node) — no DB
backfill is required.  derive_legacy_path returns a stable path based on
user_id + memory_type + node_id so legacy nodes are addressable but are
not stored back to DB.
"""
from __future__ import annotations

import re
import uuid
import logging
from typing import Any

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

MAS_ROOT = "/memory"
# Maximum depth of a well-formed MAS path:  /memory/tenant/ns/type/id = 5 segs
MAX_PATH_DEPTH = 6
# Placeholder namespace for legacy nodes that lack a real namespace
LEGACY_NAMESPACE = "_legacy"

_DOUBLE_SLASH = re.compile(r"/+")
_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9_\-\.]+$")


# ── Path normalization ────────────────────────────────────────────────────────

def normalize_path(path: str) -> str:
    """Return a canonical MAS path.

    Rules
    -----
    * Always starts with /memory/
    * Trailing slash removed
    * Consecutive slashes collapsed
    * Wildcards (* and **) preserved as-is

    Raises:
        ValueError: If path does not start with /memory/.
    """
    if not path:
        raise ValueError("MAS path must not be empty")

    # Collapse duplicate slashes (but not in **)
    cleaned = _DOUBLE_SLASH.sub("/", path.strip())

    if not cleaned.startswith(MAS_ROOT):
        raise ValueError(
            f"MAS path must start with {MAS_ROOT!r}; got {path!r}"
        )

    # Remove trailing slash (but not the root itself)
    if cleaned != MAS_ROOT and cleaned.endswith("/"):
        cleaned = cleaned.rstrip("/")

    return cleaned


def validate_tenant_path(path: str, tenant_id: str) -> None:
    """Raise PermissionError if *path* is not under the tenant's namespace.

    Args:
        path:      Normalized MAS path.
        tenant_id: Expected tenant prefix.

    Raises:
        PermissionError: TENANT_VIOLATION — path belongs to another tenant.
    """
    expected_prefix = f"{MAS_ROOT}/{tenant_id}/"
    exact = f"{MAS_ROOT}/{tenant_id}"
    if not (path.startswith(expected_prefix) or path == exact):
        from services.tenant_context import TENANT_VIOLATION
        raise PermissionError(
            f"{TENANT_VIOLATION}: path {path!r} is not under tenant "
            f"namespace {expected_prefix!r}"
        )


# ── Path parsing + building ───────────────────────────────────────────────────

def parse_path(path: str) -> dict[str, str | None]:
    """Decompose a MAS path into its components.

    Returns a dict with keys:
        tenant_id   str | None
        namespace   str | None
        addr_type   str | None   (the "type" segment)
        node_id     str | None

    Wildcard segments are returned as "*" / "**".
    """
    p = normalize_path(path)
    segs = p.split("/")
    # segs[0] == '', segs[1] == 'memory', segs[2] == tenant_id, …
    result: dict[str, str | None] = {
        "tenant_id": None,
        "namespace": None,
        "addr_type": None,
        "node_id": None,
    }
    if len(segs) > 2:
        result["tenant_id"] = segs[2] or None
    if len(segs) > 3:
        result["namespace"] = segs[3] or None
    if len(segs) > 4:
        result["addr_type"] = segs[4] or None
    if len(segs) > 5:
        result["node_id"] = segs[5] or None
    return result


def build_path(
    tenant_id: str,
    namespace: str | None = None,
    addr_type: str | None = None,
    node_id: str | None = None,
) -> str:
    """Assemble a MAS path from components.

    Args:
        tenant_id:  Required.  Must be non-empty.
        namespace:  Optional namespace segment.
        addr_type:  Optional type sub-segment.
        node_id:    Optional leaf node UUID.

    Returns:
        Normalized MAS path string.

    Raises:
        ValueError: If tenant_id is empty.
    """
    if not tenant_id:
        raise ValueError("MAS build_path: tenant_id is required")

    parts = [MAS_ROOT, tenant_id]
    if namespace:
        parts.append(namespace)
    if addr_type:
        if not namespace:
            raise ValueError("MAS build_path: addr_type requires namespace")
        parts.append(addr_type)
    if node_id:
        if not (namespace and addr_type):
            raise ValueError("MAS build_path: node_id requires namespace and addr_type")
        parts.append(str(node_id))

    return "/".join(parts)


def generate_node_path(tenant_id: str, namespace: str, addr_type: str) -> tuple[str, str]:
    """Generate a new path + node_id for a write operation.

    Returns:
        (full_path, node_id) where full_path is
        /memory/{tenant_id}/{namespace}/{addr_type}/{node_id}
    """
    node_id = str(uuid.uuid4())
    full_path = build_path(tenant_id, namespace, addr_type, node_id)
    return full_path, node_id


def derive_legacy_path(node_dict: dict) -> str:
    """Derive a stable path for a legacy node (path == NULL).

    The derived path is:
        /memory/{user_id}/_legacy/{memory_type}/{node_id}

    This is computed on-the-fly and NOT stored back to DB.
    """
    user_id = node_dict.get("user_id") or "unknown"
    memory_type = node_dict.get("memory_type") or node_dict.get("node_type") or "insight"
    node_id = node_dict.get("id") or str(uuid.uuid4())
    return build_path(user_id, LEGACY_NAMESPACE, memory_type, node_id)


def parent_path_of(path: str) -> str:
    """Return the parent path (strips the last segment).

    /memory/user/ns/type/id → /memory/user/ns/type
    /memory/user/ns/type    → /memory/user/ns
    /memory/user/ns         → /memory/user
    /memory/user            → /memory
    """
    p = normalize_path(path)
    idx = p.rfind("/")
    if idx <= len(MAS_ROOT):
        return MAS_ROOT
    return p[:idx]


# ── Pattern classification ────────────────────────────────────────────────────

def is_exact(path: str) -> bool:
    """True if path contains no wildcards."""
    return "*" not in path and "**" not in path


def is_wildcard(path: str) -> bool:
    """True if path ends with /* (one level) but not /**."""
    p = normalize_path(path)
    return p.endswith("/*") and not p.endswith("/**")


def is_recursive(path: str) -> bool:
    """True if path ends with /** (all descendants)."""
    p = normalize_path(path)
    return p.endswith("/**")


def wildcard_prefix(path: str) -> str:
    """Return the prefix before the wildcard segment.

    /memory/user/tasks/*  → /memory/user/tasks
    /memory/user/tasks/** → /memory/user/tasks
    """
    p = normalize_path(path)
    if p.endswith("/**"):
        return p[:-3]
    if p.endswith("/*"):
        return p[:-2]
    return parent_path_of(p)


# ── Path extraction from namespace/type ──────────────────────────────────────

def path_from_write_payload(payload: dict, tenant_id: str) -> tuple[str, str, str]:
    """Extract or construct a full path from a write payload.

    The payload may supply:
    1. A pre-built path: ``{"path": "/memory/user/tasks/pending"}``
    2. Namespace + addr_type: ``{"namespace": "tasks", "addr_type": "pending"}``
    3. Neither (fall back to defaults: namespace="general", addr_type=node_type)

    Returns:
        (full_path, namespace, addr_type)

    Raises:
        ValueError: If path is supplied but violates tenant isolation.
        PermissionError: If path crosses tenant boundary.
    """
    node_type = payload.get("node_type", "general")

    if payload.get("path"):
        raw = normalize_path(payload["path"])
        validate_tenant_path(raw, tenant_id)
        parsed = parse_path(raw)
        ns = parsed["namespace"] or "general"
        at = parsed["addr_type"] or node_type
        # If path already has a node_id, use it as-is; otherwise generate
        if parsed["node_id"]:
            return raw, ns, at
        full_path, _ = generate_node_path(tenant_id, ns, at)
        return full_path, ns, at

    ns = payload.get("namespace") or "general"
    at = payload.get("addr_type") or node_type
    full_path, _ = generate_node_path(tenant_id, ns, at)
    return full_path, ns, at


# ── Tree building ─────────────────────────────────────────────────────────────

def build_tree(nodes: list[dict]) -> dict:
    """Assemble a list of node dicts into a hierarchical tree structure.

    Each node must have a ``path`` key.  Nodes are organized as children
    under their parent_path.

    Returns:
        Tree dict — {path → {"node": ..., "children": [...]}}
        The root entry is keyed by the common prefix.
    """
    by_path: dict[str, dict] = {}
    children_map: dict[str, list] = {}

    for n in nodes:
        path = n.get("path") or derive_legacy_path(n)
        by_path[path] = {"node": n, "children": []}
        parent = parent_path_of(path)
        if parent not in children_map:
            children_map[parent] = []
        children_map[parent].append(path)

    for parent, child_paths in children_map.items():
        if parent in by_path:
            by_path[parent]["children"] = child_paths

    return by_path


def flatten_tree(tree: dict) -> list[dict]:
    """Return nodes from a build_tree() result in depth-first order."""
    if not tree:
        return []
    roots = set(tree.keys()) - {
        parent_path_of(p) for p in tree if parent_path_of(p) in tree
    }
    result = []

    def _walk(path: str) -> None:
        entry = tree.get(path)
        if entry:
            result.append(entry["node"])
            for child_path in entry.get("children", []):
                _walk(child_path)

    for root in sorted(roots):
        _walk(root)
    return result


# ── Summary helpers ───────────────────────────────────────────────────────────

def enrich_node_with_path(node_dict: dict) -> dict:
    """Add a ``path`` field to a node dict if missing (legacy support).

    Mutates and returns the dict.
    """
    if not node_dict.get("path"):
        node_dict["path"] = derive_legacy_path(node_dict)
    return node_dict
