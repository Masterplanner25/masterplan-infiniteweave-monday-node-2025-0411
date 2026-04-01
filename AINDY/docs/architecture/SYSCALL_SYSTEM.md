# Syscall System

A.I.N.D.Y. syscalls are the single gated interface between Nodus scripts and host services. All cross-boundary calls — memory reads, flow executions, event emissions — route through the syscall dispatcher. No Nodus code touches a DB session or a service function directly.

---

## 1. Overview

```
Nodus script
    │  sys("sys.v1.memory.read", {"query": "auth"})
    ▼
SyscallDispatcher.dispatch()
    │  parse version · check capability · validate input · execute handler
    ▼
Registered handler
    │  e.g. _handle_memory_read(payload, ctx) → dict
    ▼
Standard response envelope
    { status, data, version, warning, trace_id, duration_ms, error }
```

The dispatcher **never raises**. Every code path returns the envelope.

---

## 2. Syscall Name Convention

```
sys.{version}.{domain}.{action}
```

Examples:
- `sys.v1.memory.read`
- `sys.v1.flow.run`
- `sys.v2.memory.read`  ← v2 evolution with added `filters` param

`parse_syscall_name("sys.v1.memory.read")` → `("v1", "memory.read")`

---

## 3. Response Envelope

All calls return the same shape:

```json
{
    "status":            "success" | "error",
    "data":              {},
    "trace_id":          "run-123",
    "execution_unit_id": "run-123",
    "syscall":           "sys.v1.memory.read",
    "version":           "v1",
    "duration_ms":       42,
    "error":             null,
    "warning":           null
}
```

- `version` — always present; the parsed ABI version string.
- `warning` — set when the syscall is deprecated; null otherwise.
- `error` — set on failure; null on success.
- `data` — handler output on success; `{}` on error.

---

## 4. Dispatcher Pipeline

Steps executed in order for every call:

| Step | Action | Fatal? |
|------|--------|--------|
| 1 | Parse `sys.{version}.{action}` from name | error if malformed |
| 2 | Resolve version; optional fallback (`SYSCALL_VERSION_FALLBACK`) | error if unresolvable |
| 3 | Look up entry in `SYSCALL_REGISTRY` | error if not found |
| 4 | Enforce capability from `SyscallContext.capabilities` | error if denied |
| 5 | Enforce non-empty `user_id` (tenant isolation) | error if absent |
| 6 | Resource quota check via `ResourceManager` | error if over quota |
| 7 | Input validation against `entry.input_schema` | error if invalid |
| 8 | Deprecation check — set `warning` in envelope | non-fatal, continues |
| 9 | Execute handler | error if handler raises |
| 10 | Output validation against `entry.output_schema` | non-fatal, logs warning |
| 11 | Record syscall usage in `ResourceManager` | non-fatal |
| 12 | Emit `SYSCALL_EXECUTED` system event | non-fatal |
| 13 | Return success envelope | — |

---

## 5. Registry

### SyscallEntry

Defined in `services/syscall_registry.py`.

```python
class SyscallEntry:
    handler:        Callable[[dict, SyscallContext], dict]
    capability:     str          # required capability name
    description:    str
    input_schema:   dict | None  # JSON schema for input validation
    output_schema:  dict | None  # JSON schema for output validation (non-fatal)
    stable:         bool         # False = experimental
    deprecated:     bool
    deprecated_since: str | None # e.g. "v2"
    replacement:    str | None   # e.g. "sys.v2.memory.read"
```

### VersionedSyscallRegistry

`SYSCALL_REGISTRY` is a `VersionedSyscallRegistry(MutableMapping)` that supports two access patterns simultaneously:

```python
# Flat access (backward-compatible)
entry = SYSCALL_REGISTRY["sys.v1.memory.read"]

# Versioned view
all_v1 = SYSCALL_REGISTRY.get_version("v1")  # {"memory.read": SyscallEntry, ...}
available = SYSCALL_REGISTRY.versions()       # ["v1", "v2"]
versioned = SYSCALL_REGISTRY.versioned        # {"v1": {...}, "v2": {...}}
```

### Registering a Syscall

```python
from services.syscall_registry import register_syscall

register_syscall(
    name="sys.v1.myservice.dostuff",
    handler=my_handler,
    capability="myservice.dostuff",
    description="Does the stuff",
    input_schema={
        "required": ["target"],
        "properties": {
            "target": {"type": "string"},
            "options": {"type": "object"},
        },
    },
    output_schema={
        "required": ["result"],
        "properties": {"result": {"type": "string"}},
    },
    stable=True,
    deprecated=False,
)
```

---

## 6. ABI Versioning

### Version Rules

- Every syscall declares a version in its name: `sys.v{N}.{domain}.{action}`.
- `v1` is the current stable baseline. `v2` exists as an example evolution (`sys.v2.memory.read`).
- Breaking changes **must** use a new version prefix. Adding optional params is non-breaking.
- Removing a field, changing a type, or changing semantics = breaking = new version.

### Version Fallback

`SYSCALL_VERSION_FALLBACK = False` (default).

- `False` — unknown version returns error immediately.
- `True` — unknown version falls back to `LATEST_STABLE_VERSION` (`v1`) and logs a warning.

Override via env variable or test fixture.

### Deprecation

Set `deprecated=True` + `deprecated_since` + `replacement` when retiring:

```python
register_syscall(
    name="sys.v1.memory.read",
    ...
    deprecated=True,
    deprecated_since="v2",
    replacement="sys.v2.memory.read",
)
```

Deprecated syscalls still execute. The dispatcher sets `warning` in the response envelope and logs a warning. Clients should migrate to the replacement.

---

## 7. Input / Output Validation

Defined in `services/syscall_versioning.py`.

### Schema Format

```python
schema = {
    "required": ["field_a"],       # list of required field names
    "properties": {
        "field_a": {"type": "string"},
        "field_b": {"type": "integer"},
        "field_c": {"type": "boolean"},
        "field_d": {"type": "list"},
        "field_e": {"type": "dict"},
    },
}
```

Supported types: `string`, `integer`, `float`, `boolean`, `list`, `dict`.

### Input Validation (fatal)

Called before the handler. Missing required fields or wrong types → error envelope returned, handler never runs.

### Output Validation (non-fatal)

Called after the handler. Schema mismatch → warning logged, result still returned.

---

## 8. SyscallContext

```python
@dataclass
class SyscallContext:
    execution_unit_id: str          # AgentRun/flow run ID
    user_id:           str          # authenticated tenant identity
    capabilities:      list[str]    # granted capability names
    trace_id:          str          # for observability correlation
    metadata:          dict         # optional — workflow_type, flow_name, etc.
```

Helper builders (from `services/syscall_dispatcher.py`):

```python
# From a flow node context dict
ctx = make_syscall_ctx_from_flow(context, capabilities=["memory.read"])

# From an agent tool call
ctx = make_syscall_ctx_from_tool(user_id="user-123", run_id="run-456")
```

---

## 9. Built-in Syscalls (v1)

All registered in `services/syscall_registry.py` and `services/syscall_handlers.py`.

| Syscall | Capability | Description |
|---------|-----------|-------------|
| `sys.v1.memory.read` | `memory.read` | Recall memory nodes by query/tags/path |
| `sys.v1.memory.write` | `memory.write` | Persist a new memory node with optional path |
| `sys.v1.memory.search` | `memory.read` | Semantic similarity search |
| `sys.v1.memory.list` | `memory.read` | List nodes at a MAS path (one level) |
| `sys.v1.memory.tree` | `memory.read` | Hierarchical tree from a MAS path |
| `sys.v1.memory.trace` | `memory.read` | Causal chain from a node path |
| `sys.v1.flow.run` | `flow.run` | Execute a registered Nodus flow |
| `sys.v1.event.emit` | `event.emit` | Emit a system event |
| `sys.v2.memory.read` | `memory.read` | v2 evolution — adds `filters` dict (memory_type, node_type, min_impact) |

Domain handlers registered at startup via `register_all_domain_handlers()` in `services/syscall_handlers.py`.

---

## 10. Nodus Integration

Nodus scripts call syscalls via the `sys()` global:

```python
result = sys("sys.v1.memory.read", {"query": "authentication flow"})
if result["status"] == "success":
    nodes = result["data"]["nodes"]
```

The `sys` global is injected at runtime by `NodusInterpreter`. The syscall context is derived from the current flow's execution context.

---

## 11. Introspection API

```
GET /platform/syscalls?version=v1
```

Auth: JWT or Platform API key.

Response:
```json
{
    "versions": ["v1", "v2"],
    "syscalls": {
        "v1": {
            "memory.read": {
                "name": "sys.v1.memory.read",
                "capability": "memory.read",
                "description": "...",
                "stable": true,
                "deprecated": false,
                "input_schema": {...},
                "output_schema": {...}
            }
        }
    },
    "total_count": 9
}
```

---

## 12. Key Files

| File | Role |
|------|------|
| `services/syscall_versioning.py` | `SyscallSpec`, `parse_syscall_name`, `validate_payload`, `resolve_version`, `ABI_VERSIONS` |
| `services/syscall_registry.py` | `SyscallEntry`, `VersionedSyscallRegistry`, `SYSCALL_REGISTRY`, `register_syscall` |
| `services/syscall_dispatcher.py` | `SyscallDispatcher`, `get_dispatcher`, `SyscallContext`, context builder helpers |
| `services/syscall_handlers.py` | All 20+ domain handler functions; `register_all_domain_handlers()` |
| `routes/platform_router.py` | `GET /platform/syscalls` introspection endpoint |
| `tests/unit/test_syscall_versioning.py` | 64 versioning/ABI tests (Groups A–J) |
| `tests/unit/test_syscall_dispatcher.py` | Dispatcher unit tests |
