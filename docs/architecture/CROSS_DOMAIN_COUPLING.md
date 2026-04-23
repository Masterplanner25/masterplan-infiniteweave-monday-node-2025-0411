# Cross-Domain Coupling

This document describes the two largest cross-domain coupling sites in the
`apps/` layer: the Infinity Algorithm service cluster and the automation flow
layer. Both are intentional architectural choices given the current monolith
reality. Both carry specific risks that engineers must understand before
modifying either area.

---

## 1. What Cross-Domain Coupling Means Here

The `apps/` directory contains domain modules that are not yet fully
independent services. They share a database, a plugin registry, and in some
cases each other's models and services. Cross-domain coupling is when one
domain module imports from another domain module's internal implementation —
services, models, or schemas — rather than going through the syscall layer
or an event.

Cross-domain coupling is **not automatically wrong** in a monolith in
transition. It becomes a structural risk when:

- It creates cascading import failures at startup
- It creates circular dependency chains
- It prevents a domain from being separated later without major rewrites
- It couples unrelated failure modes (a bug in domain A crashes domain B)

The two sites documented here meet at least one of these criteria.

---

## 2. The Infinity Algorithm Cluster

### 2.1 What It Is

The Infinity Algorithm is the feedback core of AINDY. It runs when a
significant event fires (task completed, agent completed, manual trigger) and
produces a `next_action` recommendation by synthesising the user's current
KPI state, recent task history, goal alignment, memory signals, system state,
and social performance.

It is implemented across three files in `apps/analytics/services/`:

| File | Role |
|---|---|
| `infinity_service.py` | KPI snapshot calculation, score context |
| `infinity_loop.py` | Decision engine — `_decide()`, weighting functions, loop evaluation |
| `infinity_orchestrator.py` | Entrypoint — acquires execution lease, gathers inputs, calls loop |

### 2.2 The Dependency Map

`infinity_orchestrator.execute()` is the single external entry point.
It gathers data from six domains before calling the loop:

```
infinity_orchestrator.execute(user_id, trigger_event, db)
│
├─ apps.identity.services.identity_boot_service
│   └─ get_recent_memory(user_id, db)   ← user's recent memory nodes
│   └─ get_user_metrics(user_id, db)    ← identity-level metrics
│
├─ apps.masterplan.services.goal_service
│   └─ rank_goals(db, user_id, system_state)  ← ranked goal list
│
├─ apps.tasks.services.task_service
│   └─ get_task_graph_context(db, user_id)    ← task dependency graph
│
├─ apps.social.services.social_performance_service
│   └─ get_social_performance_signals(user_id)  ← LinkedIn/social signals
│
├─ AINDY.memory.memory_scoring_service
│   └─ get_relevant_memories(query, db)       ← memory retrieval (AINDY runtime)
│
├─ AINDY.platform_layer.system_state_service
│   └─ compute_current_state(db)              ← system load, queue depth
│
└─ infinity_loop.run_loop(loop_context, db)
    │
    ├─ apps.tasks.services.task_service
    │   └─ get_next_ready_task(user_id, db)   ← highest-priority ready task
    │
    ├─ apps.masterplan.services.goal_service
    │   └─ calculate_goal_alignment(...)      ← goal-task alignment score
    │
    └─ apps.automation.models
        └─ LoopAdjustment, UserFeedback       ← reads prior decisions
```

### 2.3 Why It Crosses Domains

The algorithm is architecturally an aggregator. Its job is to synthesise
signals from every domain into a single recommendation. That is not a design
flaw — it is the feature. An analytics scoring engine that only looked at
analytics data would produce poor recommendations.

The correct mental model: **the Infinity Algorithm is a read-only cross-domain
query engine**. It reads from tasks, masterplan, identity, social, and memory.
It writes only to the analytics domain (LoopAdjustment, UserScore). It does
not mutate task state, goal state, or identity state.

### 2.4 The Cascade Import Risk

`infinity_loop.py` has two module-level cross-domain imports:

```python
# Line 7 — module level
from apps.tasks.services.task_service import get_next_ready_task

# Line 10 — module level
from apps.masterplan.services.goal_service import calculate_goal_alignment
```

`infinity_orchestrator.py` has four module-level cross-domain imports:

```python
# Lines 14–22 — module level
from apps.identity.services.identity_boot_service import get_recent_memory, get_user_metrics
from apps.masterplan.services.goal_service import rank_goals
from apps.social.services.social_performance_service import get_social_performance_signals
from apps.tasks.services.task_service import get_task_graph_context
```

**The risk**: if any of these target modules fails to import at startup
(circular import, missing dependency, syntax error, migration failure), the
entire `infinity_orchestrator` module fails to import. This cascades:

```
infinity_orchestrator fails to import
    → infinity_orchestrator cannot be imported by analytics_flows.py
        → analytics_flows.py fails
            → flow_definitions_extended.register_extended_flows() fails
                → apps.bootstrap._register_flows() fails
                    → apps.bootstrap.bootstrap() fails
                        → load_plugins() raises
                            → main.py lifespan() aborts
                                → server fails to start
```

A bug in `apps/tasks/services/task_service.py` can prevent the entire
platform from starting. This is the primary structural risk.

**The fix** (tracked in Prompt 11): convert all cross-domain module-level
imports in `infinity_loop.py` and `infinity_orchestrator.py` to deferred
imports inside the function bodies that use them. The algorithm's logic does
not change; only the import timing changes.

### 2.5 The Bidirectional analytics ↔ identity Coupling

`infinity_orchestrator.py` imports from `apps.identity`:
```python
from apps.identity.services.identity_boot_service import get_recent_memory, get_user_metrics
```

`apps/identity/services/identity_boot_service.py` no longer imports from
`apps.analytics`. It resolves the score snapshot at runtime through the
platform registry:
```python
from AINDY.platform_layer.registry import get_job

get_snapshot = get_job("analytics.kpi_snapshot")
```

The remaining runtime direction is analytics → identity via deferred imports
inside the analytics dependency adapter. That is still coupling, but it is now
one-way and no longer creates a bidirectional import hazard between the two
domains.

**Rule**: identity must not import analytics internals. Cross-domain score
reads must go through registry-job dispatch (`get_job("analytics.kpi_snapshot")`)
or another platform-owned boundary.

### 2.6 Safe Modification Rules

When working in `infinity_loop.py` or `infinity_orchestrator.py`:

1. **Do not add new module-level cross-domain imports.** All cross-domain
   imports must be inside the function body that uses them.
2. **The cross-domain reads are all non-mutating.** Do not add writes to
   tasks, masterplan, identity, or social from within the loop.
3. **Each data source call is individually try/except wrapped** in
   `infinity_orchestrator.execute()`. Keeping this wrapper is mandatory —
   a failed social signal lookup must not abort the entire score update.
4. **The execution lease** (`acquire_execution_lease`) prevents concurrent
   runs for the same user and trigger_event. Do not remove or bypass it.
5. **LoopAdjustment** is the canonical write target. Every `execute()` call
   must persist a LoopAdjustment row or return an explicit `skipped` reason.

---

## 3. The Automation Flow Layer

### 3.1 What It Is

`apps/automation/flows/` is the cross-domain flow orchestration layer. It
registers every node function and flow graph that domain apps expose through
the AINDY Flow Engine. When a route handler calls `run_flow("task_complete",
state, db)`, the flow engine looks up the flow graph and node functions that
were registered here.

The layer is structured as:

```
apps/automation/flows/
├─ _flow_registration.py       helper: register_nodes(), register_single_node_flows()
├─ flow_definitions.py         platform flow nodes (ARM, task, memory entry points)
├─ flow_definitions_extended.py  coordinator: imports all domain flow files,
│                                calls register() on each, exposes register_extended_flows()
│
├─ analytics_flows.py          score, KPI, infinity loop nodes
├─ arm_flows.py                ARM analysis and suggestion nodes
├─ automation_flows.py         agent runs, memory CRUD, flow engine state,
│                              observability, watcher, dashboard, autonomy nodes
├─ freelance_flows.py          freelance delivery and invoice nodes
├─ masterplan_flows.py         plan, goal, genesis, score nodes
├─ search_flows.py             lead gen, SEO, research nodes
└─ tasks_flows.py              task lifecycle nodes
```

### 3.2 How Registration Works

Each domain flow file defines node functions and a `register()` function:

```python
# apps/automation/flows/tasks_flows.py
def task_create_node(state, context):
    from apps.tasks.services.task_service import create_task
    db = context.get("db")
    result = create_task(db, ...)
    return {"status": "SUCCESS", "output_patch": {"task": result}}

def register() -> None:
    register_nodes({"task_create_node": task_create_node})
    register_single_node_flows({"task_create": "task_create_node"})
```

`flow_definitions_extended.register_extended_flows()` calls `register()` on
every domain flow file. This is called from `apps/bootstrap._register_flows()`
which runs during `load_plugins()` at startup.

### 3.3 The Cross-Domain Nature of automation_flows.py

`automation_flows.py` is the largest file in the layer (1,530 lines, 59 node
functions). It is cross-domain by design because it serves as a **generic
adapter layer**: it exposes flow nodes for capabilities that don't belong to
a single domain — agent runtime operations, memory operations, observability,
and system-level flow management.

Its imports inside node functions cross into:

```
apps.agent          ← AINDY.agents.agent_runtime (approved public API)
apps.analytics      ← analytics_router KPI snapshot
AINDY.runtime       ← flow_engine run_flow, MemoryOrchestrator
AINDY.agents        ← agent_runtime, agent_tools, capability_service
```

The problematic import in this file:

```python
# apps/automation/flows/automation_flows.py — inside agent_run_approve_node
from AINDY.agents.agent_runtime import _run_to_dict  # private function
```

`_run_to_dict` is prefixed `_` indicating it is private to `agent_runtime`.
This coupling means any refactor of `agent_runtime`'s internal serialization
format can silently break `agent_run_approve_node` and related nodes. The fix
is tracked in Prompt 3: expose `run_to_dict` as a public alias and update
all callers.

### 3.4 Node Function Contract

Every node function in every flow file must follow this contract:

```python
def my_node(state: dict, context: dict) -> dict:
    """
    state   — mutable flow state; read inputs, return output_patch to merge in
    context — execution context: db, user_id, trace_id, flow_run_id, etc.

    Returns one of:
      {"status": "SUCCESS", "output_patch": {...}}
      {"status": "RETRY", "error": "reason"}
      {"status": "FAILURE", "error": "reason"}
      {"status": "WAIT", "wait_for": "event.name", "correlation_id": "..."}
    """
```

All domain imports inside node functions must be deferred (inside the function
body). Node functions must never import at module level from other domains —
a module-level import failure in a domain would prevent all 59+ nodes in the
file from registering.

### 3.5 flow_definitions_extended.py — The Coordinator

`flow_definitions_extended.py` uses star-imports (`from ... import *`) from
each domain flow file. This is intentional: it creates a single namespace
where any node function can be referenced by name. The star-imports are the
mechanism by which `register_extended_flows()` has access to all node
functions from all domains.

This pattern means that adding a new node function to any domain flow file
automatically makes it available to `register_extended_flows()` without
modifying the coordinator. The trade-off is that the coordinator's namespace
contains every node function from every domain, which makes static analysis
harder.

The star-imports do NOT cause circular imports because all cross-domain calls
within node functions are deferred (inside function bodies, not at module
level).

### 3.6 The Separation Constraint

The automation flow layer **cannot be separated from any domain app** without
moving the node functions for that domain into the domain app itself. Currently
`automation_flows.py` owns agent run nodes, memory nodes, observability nodes,
and watcher nodes even though those belong conceptually to `apps/agent`,
`AINDY/memory`, and `AINDY/watcher`.

The correct long-term direction is:
- `apps/agent/flows/` owns agent run nodes
- `AINDY/memory` nodes move into a platform flow file
- `automation_flows.py` shrinks to system-level orchestration only

This migration is tracked in Prompt 10, which splits `automation_flows.py`
into domain-grouped files as a first step.

### 3.7 Safe Modification Rules

When working in `apps/automation/flows/`:

1. **All domain imports must be inside function bodies.** Adding a module-level
   import from any `apps.*` module in a flow file is forbidden — it creates a
   startup cascade risk.

2. **Do not call private functions from AINDY.** If you need a function that
   is prefixed `_`, either request it be made public or implement the logic
   directly in the node function.

3. **Node names are part of the public API.** They are stored in `FlowRun`
   state and `AgentEvent` records in the database. Renaming a node name is
   a migration-level change that requires updating existing DB records.

4. **Flow graph edges are static.** Flow graphs (the dicts passed to
   `register_flow()`) are registered once at startup. To change an edge, you
   must restart the server. Dynamic edge selection uses the `condition` lambda
   pattern already established in `watcher_evaluate_trigger`.

5. **Each node must be independently testable.** Nodes receive `state` and
   `context` dicts. Tests should pass mock values directly rather than running
   the full flow engine.

---

## 4. Coupling Direction Summary

The table below shows which domains import from which others, across both
coupling sites.

| Source | Imports from | Type | Risk |
|---|---|---|---|
| `analytics/infinity_orchestrator` | `identity`, `masterplan`, `tasks`, `social` | module-level | CASCADE (Prompt 11) |
| `analytics/infinity_loop` | `tasks`, `masterplan`, `automation.models` | module-level + deferred | CASCADE for module-level |
| `analytics/routes` | `masterplan.services` | deferred in handler | router_guard violation |
| `identity/identity_boot_service` | `analytics.kpi_snapshot` job | registry-job dispatch | none |
| `masterplan/services` | `tasks.models`, `tasks.services` | deferred | acceptable |
| `masterplan/services` | `automation.models` (AutomationLog) | deferred | acceptable |
| `automation/flows/automation_flows` | `AINDY.agents.agent_runtime._run_to_dict` | deferred | private API (Prompt 3) |
| `automation/flows/analytics_flows` | `analytics.services` | deferred | acceptable |

**Acceptable**: deferred, read-only, one direction, no private API.  
**Risk**: module-level (cascade), bidirectional, or private API call.

---

## 5. The Correct Boundary for New Work

When adding new cross-domain reads:

- **Preferred**: expose as a syscall (`sys.v1.<domain>.<operation>`), dispatch
  via `SyscallDispatcher`. This keeps the caller domain independent of the
  target domain's import tree.
- **Acceptable in monolith**: deferred import inside a node function or
  service function. Never at module level.
- **Not acceptable**: module-level imports from another domain's services or
  models in any file that is imported at startup.
- **Never**: bidirectional module-level imports between two domains.
