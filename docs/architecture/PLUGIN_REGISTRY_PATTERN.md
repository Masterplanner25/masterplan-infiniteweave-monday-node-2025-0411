# Plugin Registry Pattern

This document describes the actual integration mechanism between the AINDY
runtime and domain apps. It is the most important architectural pattern in
the codebase and is referenced by every domain app, the startup sequence,
the flow engine, the scheduler, and the agent runtime.

---

## 1. The Problem It Solves

AINDY is split into two layers:

- **Runtime** (`AINDY/`) — execution engine, flow engine, memory, kernel,
  scheduler, syscall dispatcher. Domain-agnostic. Must not import apps.
- **Apps** (`apps/`) — domain modules (tasks, analytics, masterplan, etc.).
  Must register their behaviour into the runtime without the runtime
  knowing they exist.

The plugin registry is the boundary contract between them. The runtime
exposes a registration surface. Apps call it at startup. Neither layer
holds a compile-time import of the other.

---

## 2. The Three Components

```
aindy_plugins.json          ← manifest: which Python modules to load
AINDY/platform_layer/registry.py  ← in-process registry: all registration functions
apps/bootstrap.py           ← domain plugin: calls registry on startup
```

### 2.1 The Manifest — `aindy_plugins.json`

```json
{
  "plugins": [
    "apps.bootstrap"
  ]
}
```

This is the only place in the runtime that names a domain module. Adding a
new top-level plugin means adding a line here. The runtime reads this at
startup and imports each module by name.

### 2.2 The Registry — `AINDY/platform_layer/registry.py`

A module of pure registration and lookup functions backed by in-process dicts.
No domain logic, no database, no imports from `apps/`.

The registry holds:

| Dict | Populated by | Consumed by |
|---|---|---|
| `_routers` | `register_router()` | `main.py` → `app.include_router()` |
| `_jobs` | `register_job()` | `execution_dispatcher`, scheduled jobs |
| `_scheduled_jobs` | `register_scheduled_job()` | `scheduler_service` on startup |
| `_flows` | `register_flow()` | `flow_engine.register_all_flows()` |
| `_event_handlers` | `register_event_handler()` | `emit_event()` |
| `_event_types` | `register_event_type()` | validation, observability |
| `_syscalls` | `register_syscall()` | `SyscallDispatcher.dispatch()` |
| `_startup_hooks` | `register_startup_hook()` | `run_startup_hooks()` in lifespan |
| `_capture_rules` | `register_capture_rule()` | `memory_capture_engine` |
| `_memory_policies` | `register_memory_policy()` | memory significance scoring |
| `_agent_tools` | `register_agent_tool()` | `TOOL_REGISTRY`, agent planner |
| `_agent_planner_contexts` | `register_agent_planner_context()` | agent plan generation |
| `_agent_run_tools` | `register_agent_run_tools()` | agent execution |
| `_response_adapters` | `register_response_adapter()` | `execution_pipeline` response shaping |
| `_route_prefixes` | `register_route_prefix()` | EU type routing |
| `_symbols` | `register_symbol()` | `get_symbol()` — arbitrary cross-module publication |
| `_agent_ranking_strategy` | `register_agent_ranking_strategy()` | agent run ordering |
| `_trigger_evaluators` | `register_trigger_evaluator()` | autonomous trigger evaluation |
| `_flow_strategies` | `register_flow_strategy()` | dynamic flow plan selection |

### 2.3 The Domain Plugin — `apps/bootstrap.py`

The single Python module named in `aindy_plugins.json`. Its `bootstrap()`
function is called once at startup via `load_plugins()`. It is idempotent
(guarded by `_BOOTSTRAPPED` flag).

`bootstrap()` calls 18 internal `_register_*` functions, each responsible for
one category of registration. All domain imports are deferred inside these
functions — nothing is imported at module level except the standard library.

---

## 3. Boot Sequence

```
main.py  lifespan()
│
├─ load_plugins()                      # reads aindy_plugins.json
│   └─ importlib.import_module("apps.bootstrap")
│       └─ apps.bootstrap.bootstrap()
│           ├─ _register_models()      # domain SQLAlchemy models → Base.metadata
│           ├─ _register_routers()     # 24+ FastAPI routers → _routers dict
│           ├─ _register_route_prefixes()
│           ├─ _register_response_adapters()
│           ├─ _register_execution_adapters()
│           ├─ _register_startup_hooks()
│           ├─ _register_events()      # event types + handlers
│           ├─ _register_jobs()        # 20+ named callable jobs
│           ├─ _register_scheduled_jobs()  # 6 APScheduler jobs
│           ├─ _register_agent_capabilities()
│           ├─ _register_agent_tools()
│           ├─ _register_agent_ranking()
│           ├─ _register_trigger_evaluators()
│           ├─ _register_flow_strategy()
│           ├─ _register_agent_runtime_extensions()
│           ├─ _register_async_jobs()
│           ├─ _register_capture_rules()
│           ├─ _register_flows()       # calls flow_definitions_extended.register_extended_flows()
│           ├─ _register_flow_results()
│           └─ _register_flow_plans()
│
├─ register_all_domain_handlers()      # syscall handlers registered via registry facade
├─ register_all_flows()                # calls registry.register_flows() → all flow fns run
├─ load_dynamic_registry()             # DB-persisted flows/nodes/webhooks restored
├─ validate_router_boundary()          # AST check: no router imports domain services
├─ scan_and_recover_stuck_runs()       # recover crashed agent/flow runs
├─ get_event_bus().start_subscriber()  # Redis pub/sub for cross-instance events
├─ rehydrate_waiting_eus()             # restore EU WAIT callbacks
├─ rehydrate_waiting_flow_runs()       # restore FlowRun WAIT callbacks
└─ run_startup_hooks()                 # calls all registered startup hooks
```

After `lifespan()` completes, `main.py` mounts routers from the registry:

```python
for route in get_routers():
    app.include_router(route, prefix="/apps", ...)
```

The runtime never held a reference to any router before `load_plugins()` ran.

---

## 4. How Apps Use the Registry

Every registration call follows the same shape: import the registration
function from `AINDY/platform_layer/registry.py`, call it with a handler or
value. All domain imports are deferred inside the function body.

### Registering a router

```python
# apps/bootstrap.py  _register_routers()
def _register_routers() -> None:
    from AINDY.platform_layer.registry import register_router
    from apps.tasks.routes.task_router import router as task_router

    register_router(task_router)          # mounted at /apps/tasks/...
```

### Registering a syscall handler

```python
# apps/masterplan/syscalls/syscall_handlers.py
from AINDY.kernel.syscall_registry import get_registry
from AINDY.kernel.syscall_versioning import SyscallSpec

def register_masterplan_syscall_handlers() -> None:
    registry = get_registry()
    registry.register(SyscallSpec(
        name="sys.v1.masterplan.assert_owned",
        version="v1",
        handler=_handle_assert_masterplan_owned,
        capability_required="masterplan.read",
    ))
```

### Registering a scheduled job

```python
# apps/bootstrap.py  _register_scheduled_jobs()
def _register_scheduled_jobs() -> None:
    from AINDY.platform_layer.registry import register_scheduled_job

    register_scheduled_job(
        "task_reminder_check",
        _scheduler_check_reminders,
        trigger="interval",
        trigger_kwargs={"minutes": 1},
    )
```

### Registering a flow

Domain flow files (e.g. `apps/automation/flows/tasks_flows.py`) define node
functions and call `register_nodes()` / `register_single_node_flows()` from
`apps/automation/flows/_flow_registration.py`. The flow registration helper
calls `AINDY.runtime.flow_engine.register_node` and `register_flow`.

Flow files expose a `register()` function. The coordinator
`flow_definitions_extended.register_extended_flows()` calls `register()` on
each domain flow file. This function is itself called from
`apps/bootstrap.py _register_flows()`.

### Registering an event handler

```python
# apps/bootstrap.py  _register_events()
def _register_events() -> None:
    from AINDY.platform_layer.registry import register_event_handler
    register_event_handler("auth.register.completed", _handle_auth_register_completed)
```

When `emit_event("auth.register.completed", {...})` is called anywhere in the
runtime, the registry dispatches to `_handle_auth_register_completed`.

---

## 5. How the Runtime Consumes Registrations

The runtime calls registry lookups — it never imports domain code directly.

```python
# AINDY/main.py — router mounting
from AINDY.platform_layer.registry import get_routers
for route in get_routers():
    app.include_router(route, prefix="/apps", ...)

# AINDY/core/execution_pipeline.py — response adapter
from AINDY.platform_layer.registry import get_response_adapter
adapter = get_response_adapter(route_prefix)

# AINDY/kernel/scheduler_engine.py — scheduled jobs
from AINDY.platform_layer.registry import get_scheduled_jobs
for job in get_scheduled_jobs():
    scheduler.add_job(job["handler"], ...)

# AINDY/platform_layer/registry.py — event dispatch
def emit_event(event_type, context):
    for handler in _event_handlers.get(event_type, []):
        handler(context)
```

The runtime has zero knowledge of which apps are loaded. The registry is the
only shared surface.

---

## 6. Adding a New Domain App

To add a new domain app `apps/newdomain/`:

1. Create `apps/newdomain/__init__.py`, `routes/`, `models.py`, `services/`,
   `bootstrap.py`.

2. In `apps/newdomain/bootstrap.py`, implement a `register()` function:
   ```python
   def register() -> None:
       _register_models()
       _register_router()
       _register_flows()
       # etc.
   ```

3. In `apps/bootstrap.py`, import and call `newdomain.bootstrap.register()`
   inside the appropriate `_register_*` functions. (After Prompt 2 is
   implemented, this means creating `apps/newdomain/bootstrap.py` with
   a `register()` function and adding one line to the aggregator.)

4. No changes to `AINDY/` are required. The plugin manifest
   (`aindy_plugins.json`) does not need updating unless `newdomain` is a
   separate top-level plugin rather than part of `apps.bootstrap`.

---

## 7. load_plugins() and Idempotency

`load_plugins()` is safe to call multiple times. It tracks loaded modules in
`_loaded_plugins: set[str]` and skips already-loaded modules. This means
registry functions can be called early (e.g. in tests) without re-running
the full bootstrap.

`apps/bootstrap.py bootstrap()` is also guarded by `_BOOTSTRAPPED` flag.
Calling `bootstrap()` twice is a no-op after the first call.

---

## 8. What Is NOT in the Registry

The registry holds registration metadata and handler references only. It does
not hold:

- Database sessions or connections
- ORM model instances
- Request/response state
- Configuration values (those live in `AINDY/config.py`)
- Syscall versioning schema (that lives in `AINDY/kernel/syscall_registry.py`)

The syscall dispatcher has its own registry (`SyscallRegistry`) separate from
the platform registry. The platform registry's `register_syscall()` is a
compatibility shim; canonical syscall registration uses `SyscallSpec` via
`get_registry()`.

---

## 9. Boundary Enforcement

`AINDY/core/router_guard.py` enforces that files in `AINDY/routes/` and
`AINDY/db/dao/` do not import from `apps.*.services` or `apps.*.models` at
module level. This is checked at startup via `validate_router_boundary()` in
`main.py lifespan()`. Violations raise `RouterBoundaryViolation` and prevent
startup.

The converse boundary — apps must not import from AINDY private internals —
is enforced by convention and the audit process, not by automated checks.
The public AINDY surface for apps is:

```
AINDY.db.*                  # database session, models, DAOs
AINDY.platform_layer.*      # registry, async jobs, metrics, trace context
AINDY.core.*                # execution signals, system events
AINDY.agents.*              # agent runtime (use public functions only)
AINDY.runtime.flow_engine   # run_flow(), register_flow(), register_node()
AINDY.kernel.syscall_dispatcher  # get_dispatcher(), SyscallContext
AINDY.utils.*               # text, uuid utilities
AINDY.config                # settings
```

Apps must not call private functions (prefixed `_`) from any AINDY module.
