# Syscall System

A.I.N.D.Y. syscalls are the single gated interface between Nodus scripts and host services. All cross-boundary calls — memory reads, flow executions, event emissions — route through the syscall dispatcher. No Nodus code touches a DB session or a service function directly.

---

## 1. Overview

**All execution in A.I.N.D.Y. routes through SyscallDispatcher.** Both Nodus scripts (via the `sys()` global) and host-layer entry points (routes, agents, schedulers) use the same syscall interface. Entry-point functions like `run_flow()` and `execute_intent()` are syscall proxies — thin wrappers that build a `SyscallContext` and call `get_dispatcher().dispatch(...)`.

```
Route / Agent / CLI / Scheduler
    │  run_flow() / execute_intent() / run_nodus_script_via_flow()
    │  [syscall proxy — lazy import of get_dispatcher()]
    ▼
SyscallDispatcher.dispatch()
    │  parse version · check capability · validate input · execute handler
    ▼
Registered handler
    │  e.g. _handle_flow_run(payload, ctx) → calls _run_flow_direct()
    ▼
PersistentFlowRunner → ExecutionPipeline → ExecutionDispatcher → Runtime
    ▼
Standard response envelope
    { status, data, version, warning, trace_id, duration_ms, error }

---

Nodus script
    │  sys("sys.v1.memory.read", {"query": "auth"})
    ▼
SyscallDispatcher.dispatch()
    │  (same pipeline as above)
    ▼
Standard response envelope
```

The dispatcher **never raises**. Every code path returns the envelope.

**Anonymous / system calls (`user_id=None`):** The dispatcher enforces tenant identity, so calls with no `user_id` skip the syscall layer and invoke the `_*_direct()` implementation directly. This preserves system-internal and test-harness execution paths. Logged at DEBUG.

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
| 0 | **Resolve trace context** — inherit or establish `trace_id` / `eu_id` via ContextVars | never fatal |
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
| 13 | Return success envelope; reset ContextVar tokens | — |

Step 0 is the trace propagation gate — see §12 for detail.

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
from kernel.syscall_registry import register_syscall

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
    trace_id:          str          # propagated observability trace ID
    memory_context:    list         # pre-loaded memory nodes (Nodus scripts)
    metadata:          dict         # optional — workflow_type, flow_name, etc.
```

`trace_id` and `execution_unit_id` are automatically propagated through nested
`dispatch()` calls via ContextVars (see §12). Callers never need to manually
thread them through handler code.

Helper builders (from `kernel/syscall_dispatcher.py`):

```python
# From a flow node context dict
ctx = make_syscall_ctx_from_flow(context, capabilities=["memory.read"])

# From an agent tool call
ctx = make_syscall_ctx_from_tool(user_id="user-123", run_id="run-456")

# From a parent context — explicit propagation with capability scoping
ctx = child_context(parent_context, capabilities=["memory.read"])
```

---

## 9. Built-in Syscalls (v1)

Core syscalls registered in `kernel/syscall_registry.py`; domain handlers registered at startup via `register_all_domain_handlers()` in `kernel/syscall_handlers.py`.

| Syscall | Capability | Description |
|---------|-----------|-------------|
| `sys.v1.memory.read` | `memory.read` | Recall memory nodes by query/tags/path |
| `sys.v1.memory.write` | `memory.write` | Persist a new memory node with optional path |
| `sys.v1.memory.search` | `memory.read` | Semantic similarity search |
| `sys.v1.memory.list` | `memory.read` | List nodes at a MAS path (one level) |
| `sys.v1.memory.tree` | `memory.read` | Hierarchical tree from a MAS path |
| `sys.v1.memory.trace` | `memory.read` | Causal chain from a node path |
| `sys.v1.flow.run` | `flow.run` | Execute a registered Nodus flow |
| `sys.v1.flow.execute_intent` | `flow.execute` | Intent-based flow execution — selects strategy, compiles plan, runs flow |
| `sys.v1.nodus.execute` | `nodus.execute` | Run a Nodus script via the standard `NODUS_SCRIPT_FLOW` pipeline |
| `sys.v1.job.submit` | `job.submit` | Submit an async job via `AsyncJobService` (wraps `submit_async_job()`) |
| `sys.v1.agent.execute` | `agent.execute` | Execute an agent run via `execute_run()` (external agent wrapper) |
| `sys.v1.event.emit` | `event.emit` | Emit a system event |
| `sys.v2.memory.read` | `memory.read` | v2 evolution — adds `filters` dict (memory_type, node_type, min_impact) |

Domain handlers registered at startup via `register_all_domain_handlers()` in `kernel/syscall_handlers.py`. Execution entry-point handlers (`flow.execute_intent`, `nodus.execute`, `job.submit`, `agent.execute`) are registered directly in `kernel/syscall_registry.py` alongside `flow.run`.

---

## 10. Execution Entry-Point Convergence

**All public execution functions are syscall proxies.** The real implementation lives in a `_*_direct()` private function. The proxy: (1) checks for `user_id`, (2) builds a `SyscallContext`, (3) calls `get_dispatcher().dispatch()`, (4) unwraps the envelope. The handler delegates back to `_direct()`.

### Proxy pattern

```python
# Public entry point — proxy
def run_flow(flow_name: str, state: dict, db: Session = None, user_id: str = None) -> dict:
    if not user_id:
        return _run_flow_direct(flow_name, state or {}, db, user_id)   # anonymous
    from kernel.syscall_dispatcher import _EU_ID_CTX, _TRACE_ID_CTX, get_dispatcher, SyscallContext
    # Inherit active trace when called from within a running syscall chain;
    # generate a fresh root trace when called from a route or scheduler.
    trace_id = _TRACE_ID_CTX.get() or str(uuid4())
    eu_id    = _EU_ID_CTX.get()    or trace_id
    ctx = SyscallContext(execution_unit_id=eu_id, user_id=str(user_id),
                         capabilities=["flow.run"], trace_id=trace_id,
                         metadata={"_db": db})
    result = get_dispatcher().dispatch("sys.v1.flow.run", {...}, ctx)
    if result["status"] == "error":
        raise RuntimeError(...)
    return result["data"]["flow_result"]

# Real implementation — called by the syscall handler
def _run_flow_direct(flow_name, state, db, user_id) -> dict:
    ...
    runner = PersistentFlowRunner(flow=flow, db=db, user_id=user_id, ...)
    return runner.start(initial_state=state, flow_name=flow_name)
```

### DB session threading

Routes pass a managed SQLAlchemy session to `run_flow()`. The proxy forwards it as `context.metadata["_db"]`. The handler reads `external_db = context.metadata.get("_db")` and uses it without closing. If absent, the handler opens and owns its own session. This preserves transaction boundaries across the syscall boundary.

### Converged entry points

| Public function | Syscall | `_direct()` impl |
|---|---|---|
| `run_flow()` | `sys.v1.flow.run` | `_run_flow_direct()` |
| `execute_intent()` | `sys.v1.flow.execute_intent` | `_execute_intent_direct()` |
| `run_nodus_script_via_flow()` | `sys.v1.nodus.execute` | `_run_nodus_via_flow_direct()` |
| `submit_async_job()` (external wrapper) | `sys.v1.job.submit` | routes to `AsyncJobService` |
| `execute_run()` (external wrapper) | `sys.v1.agent.execute` | routes to `agents.agent_runtime` |

`submit_async_job()` and `execute_run()` already routed through `ExecutionDispatcher` internally; the new syscalls wrap them externally for quota tracking and observability on non-Nodus callers.

### Adding a new entry point

1. Put real logic in `_my_service_direct()`.
2. Register as `sys.v1.myservice.action` with a handler that calls `_direct()`.
3. Make the public function a proxy (user_id check → SyscallContext → dispatch).

---

## 11. Nodus Integration

Nodus scripts call syscalls via the `sys()` global:

```python
result = sys("sys.v1.memory.read", {"query": "authentication flow"})
if result["status"] == "success":
    nodes = result["data"]["nodes"]
```

The `sys` global is injected at runtime by `NodusInterpreter`. The syscall context is derived from the current flow's execution context. Because context propagation is ContextVar-based, nested `sys()` calls inside a Nodus script automatically share the script's root `trace_id`.

---

## 12. Trace Propagation

### Problem

Nested syscall calls previously generated a fresh `trace_id` and `execution_unit_id` on every dispatch, producing fragmented observability graphs and broken RippleTrace lineage. A single agent run touching `flow.run → memory.read → event.emit` appeared as three unrelated execution units.

### Mechanism

`dispatch()` resolves trace context before doing any work via two module-level `ContextVar`s:

```python
_TRACE_ID_CTX: ContextVar[str]  # default ""
_EU_ID_CTX:    ContextVar[str]  # default ""
```

**Root call** (ContextVars empty — first dispatch in a thread/task):

1. Use `context.trace_id` and `context.execution_unit_id`; generate UUIDs if either is empty.
2. Set both ContextVars.
3. Execute handler.
4. **Reset** both ContextVars in `finally` — the slot is clean for the next root call.

**Nested call** (ContextVars already set — dispatch called from within a handler):

1. Override the incoming context's `trace_id` / `eu_id` with the ContextVar values.
2. Execute handler using the inherited IDs.
3. Return — no ContextVar tokens to reset.

The result: every syscall in a chain — however deep — shares one `trace_id` and one `execution_unit_id`, giving a single coherent execution unit in RippleTrace and `AgentEvent` logs.

### ContextVar scope

Python's `ContextVar` is thread-local and asyncio-task-local:

- **Sync handlers / threads**: each thread starts with a copy of the context from its spawning thread; `set()`/`reset()` are scoped to that thread.
- **Async handlers**: each `asyncio.Task` runs in its own `Context` copy; propagation is automatic within a task, isolated between tasks.
- **Thread pool (VM execution)**: the Nodus VM runs in a daemon thread seeded with the calling thread's `Context`, so ContextVar values are inherited — `sys()` calls inside a Nodus script propagate the root trace correctly.

### `child_context()` — explicit propagation

For handlers that need to dispatch a nested syscall with a **different capability set**, use `child_context()` to build an explicitly forwarded context:

```python
from kernel.syscall_dispatcher import child_context, get_dispatcher

def _handle_complex_flow(payload, context):
    # Inherit trace/eu; narrow capabilities for the sub-call
    ctx = child_context(context, capabilities=["memory.read"])
    result = get_dispatcher().dispatch("sys.v1.memory.read", {"query": "..."}, ctx)
    ...
```

`child_context()` always copies `trace_id` and `execution_unit_id` from the parent. It is optional — the ContextVar mechanism works transparently even without it. Use `child_context()` for **documentation clarity** or **capability narrowing**.

### Before / after

**Before** (broken — each nested call got a fresh trace):

```
dispatch("sys.v1.flow.run",      ctx_A)  → trace_id="trace-abc", eu="eu-1"
  └─ handler calls dispatch("sys.v1.memory.read", fresh_ctx)
        → trace_id="trace-xyz"  ← DIFFERENT — lineage broken
```

**After** (fixed — entire chain shares root trace):

```
dispatch("sys.v1.flow.run",      ctx_A)  → trace_id="trace-abc", eu="eu-1"
  └─ handler calls dispatch("sys.v1.memory.read", fresh_ctx)
        → trace_id="trace-abc"  ← INHERITED via ContextVar
```

---

## 13. Introspection API

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
    "total_count": 13
}
```

---

## 14. Key Files

| File | Role |
|------|------|
| `kernel/syscall_versioning.py` | `SyscallSpec`, `parse_syscall_name`, `validate_payload`, `resolve_version`, `ABI_VERSIONS` |
| `kernel/syscall_registry.py` | `SyscallEntry`, `VersionedSyscallRegistry`, `SYSCALL_REGISTRY`, `register_syscall`, `DEFAULT_NODUS_CAPABILITIES` |
| `kernel/syscall_dispatcher.py` | `SyscallDispatcher`, `get_dispatcher`, `SyscallContext`, `child_context`, `_TRACE_ID_CTX`, `_EU_ID_CTX`, context builder helpers |
| `kernel/syscall_handlers.py` | All 23 domain handler functions; `register_all_domain_handlers()` |
| `routes/platform_router.py` | `GET /platform/syscalls` introspection endpoint; `POST /platform/syscall` dispatch |
| `tests/unit/test_syscall_versioning.py` | 64 versioning/ABI tests (Groups A–J) |
| `tests/unit/test_syscall_dispatcher.py` | Dispatcher unit tests |
