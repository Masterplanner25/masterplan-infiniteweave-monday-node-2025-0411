# Memory Address Space (MAS)

The Memory Address Space transforms `MemoryNode` from a flat, tag/semantic-only store into a filesystem-like, path-addressable namespace. Every node can be located by a deterministic hierarchical path in addition to its UUID.

---

## 1. Path Structure

```
/memory/{tenant_id}/{namespace}/{addr_type}/{node_id}
```

| Segment | Description | Example |
|---------|-------------|---------|
| `/memory` | MAS root — always present | `/memory` |
| `{tenant_id}` | Authenticated user or agent identifier | `user-abc123` |
| `{namespace}` | Logical grouping within the tenant | `auth`, `decisions`, `_legacy` |
| `{addr_type}` | Classification within the namespace | `insight`, `outcome`, `decision` |
| `{node_id}` | UUID of the node | `4f9a...` |

Examples:
```
/memory/user-abc/auth/decision/4f9a...
/memory/user-abc/decisions/outcome/7c3b...
/memory/user-abc/_legacy/insight/1a2b...   ← auto-derived for old nodes
```

Constants (in `memory/memory_address_space.py`):
- `MAS_ROOT = "/memory"`
- `LEGACY_NAMESPACE = "_legacy"`
- `MAX_PATH_DEPTH = 6`

---

## 2. Wildcard Patterns

Two wildcard forms are supported for bulk access:

| Pattern | Meaning | Example |
|---------|---------|---------|
| `path/*` | One level (direct children only) | `/memory/user-abc/auth/*` |
| `path/**` | Recursive (all descendants) | `/memory/user-abc/**` |

Classifier helpers:
```python
is_exact(path)      # True if no wildcards
is_wildcard(path)   # True if ends with /*
is_recursive(path)  # True if ends with /**
wildcard_prefix(path)  # returns prefix without /* or /**
```

---

## 3. Path Functions

All defined in `memory/memory_address_space.py`.

### Building Paths

```python
build_path(tenant_id, namespace=None, addr_type=None, node_id=None) -> str
# /memory/user-abc
# /memory/user-abc/auth
# /memory/user-abc/auth/decision
# /memory/user-abc/auth/decision/4f9a...

generate_node_path(tenant_id, namespace, addr_type) -> (full_path, node_id)
# Generates a new UUID and returns the full path + node_id
```

### Parsing Paths

```python
parse_path("/memory/user-abc/auth/decision/4f9a...") -> {
    "tenant_id": "user-abc",
    "namespace": "auth",
    "addr_type": "decision",
    "node_id": "4f9a..."
}
```

### Normalization and Validation

```python
normalize_path(path)  # collapse //, enforce /memory/ prefix, strip trailing /
validate_tenant_path(path, tenant_id)  # raises PermissionError on cross-tenant access
parent_path_of(path)  # /memory/user-abc/auth/decision/4f9a... → /memory/user-abc/auth/decision
```

---

## 4. Legacy Compatibility

Nodes created before MAS (no `path` column) are never backfilled. Instead, a stable derived path is computed on-the-fly:

```python
derive_legacy_path(node_dict) -> "/memory/{user_id}/_legacy/{memory_type}/{node_id}"
```

`enrich_node_with_path(node_dict)` adds the derived path to any node dict that is missing one. This means all nodes, old and new, present a consistent path interface to callers.

---

## 5. Database Columns

Added to `MemoryNodeModel` in `memory/memory_persistence.py` (migration `g5h6i7j8k9l0`):

| Column | Type | Description |
|--------|------|-------------|
| `path` | `String(512)`, nullable, indexed | Full MAS path |
| `namespace` | `String(128)`, nullable, indexed | Namespace segment |
| `addr_type` | `String(128)`, nullable, indexed | Type segment (Python-safe name for `type`) |
| `parent_path` | `String(512)`, nullable, indexed | Parent path for tree queries |

Note: `addr_type` is used instead of `type` to avoid Python keyword collision.

---

## 6. DAO Path Methods

All added to `MemoryNodeDAO` in `db/dao/memory_node_dao.py`.

```python
# Write to an explicit path
dao.save_at_path(path, content, user_id, tags=None, node_type=None, ...) -> dict

# Exact lookup
dao.get_by_path(path, user_id=None) -> Optional[dict]

# One level (direct children of parent_path)
dao.list_path(parent_path, user_id=None, limit=100) -> List[dict]

# Recursive (LIKE prefix/%)
dao.walk_path(prefix, user_id=None, limit=200) -> List[dict]

# Hybrid dispatcher — exact / one-level / recursive based on path expression
dao.query_path(path_expr=None, query=None, tags=None, user_id=None, limit=20) -> List[dict]

# Causal chain — follows source_event_id links up to `depth` hops
dao.causal_trace(path, depth=5, user_id=None) -> List[dict]
```

`query_path` dispatches based on the path pattern:
- Exact path → `get_by_path`
- Ends with `/*` → `list_path`
- Ends with `/**` → `walk_path`
- No path → falls back to tag/text query

---

## 7. Tree Operations

```python
from memory.memory_address_space import build_tree, flatten_tree

tree = build_tree(nodes)   # {path → {"node": {...}, "children": [...]}}
flat = flatten_tree(tree)  # depth-first ordered list
```

`build_tree` assembles a nested tree from a flat list of node dicts. Each node's `parent_path` determines its position.

---

## 8. Write Path Integration

When writing via `sys.v1.memory.write`, the path is extracted from the payload or auto-generated:

```python
path_from_write_payload(payload, tenant_id) -> (full_path, namespace, addr_type)
```

Rules (in priority order):
1. If `payload["path"]` is set and valid → use it directly.
2. If `payload["namespace"]` + `payload["addr_type"]` are set → generate with `generate_node_path`.
3. If only `namespace` is set → generate with addr_type from `payload.get("node_type", "node")`.
4. Fallback → `_legacy` namespace with addr_type from `node_type`.

---

## 9. API Endpoints

All in `routes/platform_router.py`, prefix `/platform`.

### `GET /platform/memory`

Hybrid list — supports path expressions, tag filtering, and text search.

Query params:
- `path` — MAS path expression (exact, `/*`, or `/**`)
- `query` — free-text search
- `tags` — comma-separated tag filter
- `limit` — max results (default 20)

Response: `{ "nodes": [...], "count": int, "path": str|null }`

### `GET /platform/memory/tree`

Hierarchical tree from a path prefix.

Query params:
- `path` — required; prefix to walk (treated as `/**` if no wildcard)
- `limit` — max nodes to include (default 100)

Response: `{ "tree": {...}, "flat": [...], "count": int, "root": str }`

### `GET /platform/memory/trace`

Causal chain — follows `source_event_id` links backward from an exact node path.

Query params:
- `path` — required; exact path to a single node
- `depth` — how many hops to follow (default 5, max 10)

Response: `{ "chain": [...], "count": int, "root_path": str }`

---

## 10. Syscall Integration

MAS path methods are exposed as syscalls:

| Syscall | Method | Description |
|---------|--------|-------------|
| `sys.v1.memory.read` | `query_path` | Hybrid read; accepts `path` param |
| `sys.v1.memory.write` | `save_at_path` | Write with path; auto-generates if omitted |
| `sys.v1.memory.list` | `list_path` | One-level listing of a path |
| `sys.v1.memory.tree` | `build_tree(walk_path(...))` | Full tree from path prefix |
| `sys.v1.memory.trace` | `causal_trace` | Causal chain from node path |

---

## 11. Key Files

| File | Role |
|------|------|
| `memory/memory_address_space.py` | All path utilities: normalize, parse, build, generate, derive_legacy, wildcard helpers, tree ops |
| `memory/memory_persistence.py` | `MemoryNodeModel` with 4 new path columns |
| `db/dao/memory_node_dao.py` | 6 new path DAO methods |
| `alembic/versions/g5h6i7j8k9l0_add_memory_address_space_columns.py` | Migration adding path columns + indexes |
| `routes/platform_router.py` | 3 MAS API endpoints |
| `tests/unit/test_memory_address_space.py` | 61 tests (Groups A–K) |
