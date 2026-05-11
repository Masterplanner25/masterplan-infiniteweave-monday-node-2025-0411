---
title: "AINDY Architecture Map"
last_verified: "2026-05-10"
api_version: "1.0"
status: current
owner: "platform-team"
---
# AINDY Architecture Map

## System Overview
AINDY is a modular-monolith runtime and application platform. The codebase is split into a runtime/platform layer in `AINDY/` and domain modules in `apps/`. `AINDY/` owns execution, scheduling, memory, syscalls, observability, and shared infrastructure; `apps/` owns domain behavior such as tasks, analytics, masterplan, social, and freelance.

The authoritative list of app-approved runtime imports lives in the separate
runtime repo's Public API Contract.

The authoritative runtime-vs-app database boundary lives in the separate
runtime repo's Database Ownership Contract.

Documentation ownership note:

- this document is currently shared because it maps both `AINDY/` and `apps/`
- runtime-only operating behavior is defined in the separate runtime repo
- the apps-side dependency boundary is documented in
  [Runtime Dependency](../apps/RUNTIME_DEPENDENCY.md)
- the future apps repo shape is defined in
  [Apps Monolith Repo Shape](../apps/APPS_MONOLITH_REPO_SHAPE.md)

## Boundary Status

The repo is in a transitional architecture state. Use these terms precisely:

- **Platform boot**: process startup can load the plugin manifest, resolve app bootstrap order, register routers/jobs/flows/syscalls, and mount runtime-owned surfaces.
- **Explicit no-app boot**: selecting `platform-only` starts the runtime with zero app plugins by design.
- **Runtime-only deployment contract**: the supported no-app surface is defined in the runtime repo and should not be confused with the default app profile.
- **Platform full operation**: many user-facing capabilities still require successfully registered apps because tools, flows, and some ORM models are still app-owned, even though some `/apps/*` HTTP surfaces are now runtime-owned.
- **Current transitional coupling**: most runtime-to-app integration is indirect through bootstrap and registries, but a small number of direct `AINDY/` -> `apps.*` imports still exist and are treated as temporary exceptions.
- **Target architecture**: runtime boot and shared infrastructure remain in `AINDY/`, while domain interaction happens through registries, syscalls, and public contracts rather than direct imports.

## Documentation Split

Use the following rule while this monolith still carries both doc sets:

- runtime contracts, deployment behavior, public import surfaces, and syscall
  ABI references belong in the separate `aindy-runtime` repo
- app feature docs and app-domain behavior belong under `docs/apps/`
- mixed architecture inventories under `docs/architecture/` should state
  explicitly when they are shared references rather than runtime-only docs

## Target Repo Shape

The intended split is two repos, not many repos:

- `aindy-runtime`
  owns `AINDY/`, runtime packaging, runtime-only entrypoints, runtime manifests,
  runtime docs, and runtime CI
- `aindy-apps-monolith`
  owns `apps/`, `client/`, app manifests, app bootstrap, app-profile tests,
  app docs, and app-facing deployment/config assets

Do not interpret the runtime split as a mandate to split `apps/agent`,
`apps/tasks`, `apps/analytics`, and the rest into separate packages or
repositories.

## Layer 1: Runtime / Platform (`AINDY/`)

### Execution Kernel
`AINDY/core/` contains the execution contract used by HTTP routes, flows, and background jobs. The main execution pipeline lives in `AINDY/core/execution_pipeline/pipeline.py`, with supporting context and wait handling in `AINDY/core/execution_pipeline/context.py`, `AINDY/core/execution_pipeline/waits.py`, and `AINDY/core/execution_pipeline/signals.py`.

Key files:
- `AINDY/core/execution_pipeline/pipeline.py`
- `AINDY/core/execution_helper.py`
- `AINDY/core/execution_dispatcher.py`
- `AINDY/core/router_guard.py`

### Flow Engine
The flow engine is implemented under `AINDY/runtime/flow_engine/` and the surrounding runtime package. Runtime-owned platform flows are registered from `AINDY/runtime/flow_definitions.py`, `AINDY/runtime/flow_definitions_memory.py`, `AINDY/runtime/flow_definitions_engine.py`, and `AINDY/runtime/flow_definitions_observability.py`. App/domain flows are not imported by `AINDY/runtime`; they register separately through app bootstrap callbacks and the platform registry.

Key files:
- `AINDY/runtime/flow_engine/runner.py`
- `AINDY/runtime/flow_engine/node_executor.py`
- `AINDY/runtime/flow_engine/registry.py`
- `AINDY/runtime/flow_registry.py`

### Memory Subsystem
The memory subsystem spans `AINDY/memory/`, `AINDY/db/dao/memory_node_dao.py`, and related routes. It handles node persistence, semantic recall, trace capture, ingest queuing, and deferred embedding generation.

Key files:
- `AINDY/memory/memory_persistence.py`
- `AINDY/memory/memory_ingest_service.py`
- `AINDY/memory/embedding_jobs.py`
- `AINDY/db/dao/memory_node_dao.py`
- `AINDY/routes/memory_router.py`

### Syscall Layer
Syscalls are the main cross-domain boundary. Calls are registered in `AINDY/kernel/syscall_registry.py`, versioned in `AINDY/kernel/syscall_versioning.py`, and executed through `AINDY/kernel/syscall_dispatcher.py`. Routes expose syscall dispatch through the platform surface in `AINDY/routes/platform/platform_ops_router.py`.

Key files:
- `AINDY/kernel/syscall_dispatcher.py`
- `AINDY/kernel/syscall_registry.py`
- `AINDY/kernel/syscall_versioning.py`
- `AINDY/routes/platform/platform_ops_router.py`

### Scheduler
There are two scheduler layers. `AINDY/platform_layer/scheduler_service.py` owns APScheduler lifecycle and recurring jobs. `AINDY/kernel/scheduler_engine.py` owns in-process scheduling, waits, and dispatch.

Key files:
- `AINDY/platform_layer/scheduler_service.py`
- `AINDY/kernel/scheduler_engine.py`
- `AINDY/kernel/event_bus.py`

### Platform Services
`AINDY/platform_layer/` is the integration layer for registry wiring, health, metrics, async jobs, deployment contracts, trace context, and startup helpers.

Key files:
- `AINDY/platform_layer/registry.py`
- `AINDY/platform_layer/health_service.py`
- `AINDY/platform_layer/async_job_service.py`
- `AINDY/platform_layer/metrics.py`
- `AINDY/platform_layer/bootstrap_graph.py`

### Agent Runtime
Agent runtime code lives under `AINDY/agents/`. It provides the runtime shell, tool registry, coordinator, stuck-run recovery, and the helper layer behind the runtime-owned `/apps/agent/*` HTTP surface.

Key files:
- `AINDY/agents/agent_runtime.py`
- `AINDY/agents/runtime_api.py`
- `AINDY/agents/agent_coordinator.py`
- `AINDY/agents/tool_registry.py`
- `AINDY/agents/stuck_run_service.py`
- `AINDY/routes/agent_router.py`

### Nodus Engine
Nodus support is split between runtime-facing adapters and the lightweight embedded runtime package. The execution adapters and schedule integration live in `AINDY/runtime/`, while the local runtime package under `AINDY/nodus/` contains the bundled embedding support used by Nodus execution.

Key files:
- `AINDY/runtime/nodus_execution_service.py`
- `AINDY/runtime/nodus_flow_compiler.py`
- `AINDY/runtime/nodus_schedule_service.py`
- `AINDY/runtime/nodus_runtime_adapter.py`
- `AINDY/nodus/runtime/embedding.py`

## Layer 2: Domain Modules (`apps/`)

### Module List
Boot classification comes from `apps/bootstrap.py`. Core domains are `tasks` and `identity`. All other registered apps, including `agent`, are peripheral and may fail into degraded mode after `apps/bootstrap.py` has been successfully loaded by the selected plugin profile.

| App | Primary Responsibility | Boot Classification |
|---|---|---|
| `agent` | Agent tools, async jobs, and runtime enrichment extensions | Peripheral |
| `analytics` | KPI scoring, Infinity orchestration, analytics routes and syscalls | Peripheral |
| `arm` | ARM runs, config, and DeepSeek-backed analysis workflows | Peripheral |
| `authorship` | Authorship domain models and routes | Peripheral |
| `automation` | Automation flows, logs, and syscall handlers | Peripheral |
| `autonomy` | Autonomy decisioning and related runtime surfaces | Peripheral |
| `bridge` | Bridge domain integrations | Peripheral |
| `dashboard` | Dashboard-facing routes and app wiring | Peripheral |
| `freelance` | Orders, payments, refunds, and revenue metrics | Peripheral |
| `identity` | Authentication, signup initialization, and identity bootstrap | Core |
| `masterplan` | Goals, masterplans, genesis sessions, and score reactions | Peripheral |
| `network_bridge` | Network bridge routes and service integrations | Peripheral |
| `rippletrace` | Ripple graphs, playbooks, predictions, and learning signals | Peripheral |
| `search` | Search, research, and lead generation workflows | Peripheral |
| `social` | Social profiles, feed, analytics, and Mongo-backed metrics | Peripheral |
| `tasks` | Task management, task routes, and task-centric flows | Core |

### Inter-Module Communication
The intended inter-module boundary is the syscall layer. A concrete example exists in `apps/tasks/services/analytics_bridge.py`, where tasks asks analytics for KPI snapshots by building a `SyscallContext` and dispatching `sys.v1.analytics.get_kpi_snapshot` through `AINDY/kernel/syscall_dispatcher.py`.

Example path:
- `apps/tasks/services/analytics_bridge.py`
- `AINDY/kernel/syscall_dispatcher.py`
- `apps/analytics/syscalls.py`

Cross-app communication now primarily flows through the syscall layer. The
major direct cross-app imports have been converted: analytics→automation
(`sys.v1.automation.list_feedback`), analytics→social
(`sys.v1.social.adapt_linkedin`), agent→analytics
(`sys.v1.analytics.get_kpi_snapshot`), identity→agent
(`sys.v1.agent.count_runs`, `sys.v1.agent.list_recent_runs`,
`sys.v1.agent.ensure_initial_run`), and automation's former boot-time
dependence on agent helper syscalls. These runtime/helper agent syscalls are
now kernel-owned in `AINDY/kernel/syscall_registry.py`, so identity,
platform, and automation bootstrap callers no longer depend on
`apps/agent` registration for them. Masterplan execution and ETA reads now
cross into tasks and automation through owner syscalls
(`sys.v1.task.count`, `sys.v1.task.count_completed_since`,
`sys.v1.task.list_for_masterplan`, `sys.v1.task.delete_by_ids`, and
`sys.v1.automation.list_logs`) instead of direct `apps.tasks.public` /
`apps.automation.public` imports.
Agent tool modules also dispatch directly to their owner syscalls with
explicit capabilities rather than routing through a generic agent-owned
tool-dispatch proxy.
The runtime-owned agent layer now exposes a generic baseline on its own:
generic planner context, runtime memory tools, default trigger evaluation, and
empty suggestion/completion enrichment unless app plugins register providers.
Analytics-aware suggestions, KPI-enriched planning, and Infinity post-run
behavior remain optional plugin-owned extensions. One current refactor target
remains: domain-agnostic memory-context planning and duplicated KPI suggestion
heuristics should be separated more cleanly from analytics-owned enrichment
without moving analytics policy into the runtime core.
Remaining deferred imports between apps
are declared in `APP_DEPENDS_ON` and validated by the V1-VAL-015 CI gate.

### Boot Order
Startup order is resolved by the app-owned plugin module `apps/bootstrap.py` using dependency metadata declared in each app bootstrap file as `BOOTSTRAP_DEPENDS_ON`. Ordering is resolved by `AINDY/platform_layer/bootstrap_graph.py` using Kahn's algorithm. The current core domains are `tasks` and `identity`. Core domains abort the entire startup when their bootstrap fails; all other domains, including `agent`, degrade gracefully once the selected app plugin profile has loaded `apps/bootstrap.py` successfully. A missing requested plugin module, import-time crash, or plugin bootstrap exception is not treated as degraded mode; startup fails instead unless the operator explicitly selected a zero-plugin profile such as `platform-only`. Each core app self-declares by including `IS_CORE_DOMAIN: bool = True` in its `bootstrap.py`. The platform reads this at startup via `apps/bootstrap._get_core_domains_from_metadata()`. The constant `CORE_DOMAINS` no longer exists in `AINDY/config.py` — the domain names are not hardcoded anywhere in the platform layer.

Representative dependency declarations in `apps/bootstrap.py`:
- `analytics` depends on `identity` and `tasks`
- `automation` has no cross-app `BOOTSTRAP_DEPENDS_ON`; its calls to `agent`, `analytics`, `arm`, `masterplan`, `tasks`, and `search` are runtime syscalls or automation-owned syscall registrations rather than boot-order edges
- `arm` depends on `analytics`
- `masterplan` depends on `automation`, `identity`, and `tasks`
- `network_bridge` depends on `authorship`

In addition to `BOOTSTRAP_DEPENDS_ON`, each app may declare
`APP_DEPENDS_ON` — a broader set of runtime import dependencies that do not
need to be boot-ordered but must be declared for governance.
`APP_DEPENDS_ON` is validated by the V1-VAL-015 CI gate and checked at
startup by `_check_app_depends_on_ordering()`. See
[Plugin Registry Pattern](PLUGIN_REGISTRY_PATTERN.md#dependency-declarations-bootstrap_depends_on-and-app_depends_on)
for the full semantics.

## Cross-Layer Boundaries

### What `AINDY/` Can See
`AINDY/` primarily imports from its own subpackages and shared libraries. Domain code is mostly loaded indirectly through app bootstrap and registry wiring, but the boundary is not fully clean today.

Current verified exceptions are narrow:
- agent lifecycle persistence is runtime-owned in `AINDY/db/models/agent_run.py` and `AINDY/db/models/agent_event.py`
- the `/apps/agent/*` HTTP surface is runtime-owned in `AINDY/routes/agent_router.py`
- `apps/agent/routes/agent_router.py` remains only as a transitional compatibility re-export to the runtime router
- the repo-root `routes` compatibility package is retained only for runtime-owned aliases that resolve back into `AINDY.routes.*`; app-owned route aliases no longer belong there
- agent tool registration, async jobs, and remaining app-specific runtime enrichment stay app-owned under `apps/agent/`
- plugin registration happens through runtime-owned registries and contracts in `AINDY/platform_layer/`
- platform flow registration is runtime-owned, while app flow registration is plugin-owned through app bootstrap

This means:
- platform boot is mostly indirect and registry-driven
- runtime-owned agent routing, persistence, helper syscalls, and defaults do not require `apps/agent` bootstrap to exist
- platform full operation still depends on app registration for non-baseline agent enrichment such as additional tools, async job handlers, KPI-aware planning, and post-run hooks
- new direct `AINDY/` -> `apps.*` imports are regressions

Hard rule:
- code under `AINDY/` must not directly import `apps.*`
- runtime/plugin interaction must go through explicit runtime-owned contracts, registries, or published symbols

Important boundary files:
- `AINDY/main.py`
- `AINDY/platform_layer/registry.py`
- `AINDY/platform_layer/platform_loader.py`

### What `apps/` Can See
Apps import `AINDY.*` runtime and platform services freely. Cross-app
communication is supposed to happen through syscalls, registered jobs, and
public facade modules. Some deferred app-to-app imports still exist in the
monolith, but they are declared in `APP_DEPENDS_ON`, validated by V1-VAL-015,
and checked at startup for ordering drift by
`_check_app_depends_on_ordering()`.

Future extraction expectation:

- app code moves together as one repo rooted around `apps/`
- runtime code becomes an installed dependency rather than a sibling source tree
- the concrete target layout is documented in
  [Apps Monolith Repo Shape](../apps/APPS_MONOLITH_REPO_SHAPE.md)

### The Syscall Contract
The syscall dispatcher enforces capability checks, payload validation, version parsing, tenant context, and standardized envelopes. Version compatibility rules are defined in `AINDY/kernel/syscall_versioning.py`; runtime dispatch is implemented in `AINDY/kernel/syscall_dispatcher.py`.

## Data Layer

### PostgreSQL (Primary)
PostgreSQL is the primary persistence layer. System models live in `AINDY/db/models/`, while app-specific ORM models live under each app and are registered through the app-owned plugin entrypoint `apps.bootstrap.bootstrap_models()` during startup and migration loading. Use the runtime repo's Database Ownership Contract as the authoritative ownership map for runtime-owned vs app-owned tables and migration expectations.

Key files:
- `AINDY/db/models/`
- `AINDY/db/database.py`
- `apps/bootstrap.py`
- `alembic/versions/`

### MongoDB (Social App Only)
MongoDB is isolated to the social domain. The client lifecycle and timeout configuration live in `AINDY/db/mongo_setup.py`, while the main Mongo-backed service code is in `apps/social/services/social_performance_service.py` and `apps/social/routes/social_router.py`. MongoDB degradation affects social features and platform health status, but it is not a core platform dependency.

Key files:
- `AINDY/db/mongo_setup.py`
- `apps/social/services/social_performance_service.py`
- `apps/social/routes/social_router.py`

## Client Layer
The frontend is a React/Vite client under `client/`. It belongs with the
future `aindy-apps-monolith` repo, even though it now understands
runtime-only mode. Today it is still one apps-hosted SPA rather than a
separately deployable runtime console product. The main API client layer is
`client/src/api/`. UI components are grouped into `client/src/components/app`,
`client/src/components/platform`, and `client/src/components/shared`.

Key files and directories:
- `client/src/api/`
- `client/src/components/app/`
- `client/src/components/platform/`
- `client/src/components/shared/`
- `client/src/App.jsx`

Use [Client Ownership](../apps/CLIENT_OWNERSHIP.md) as the authoritative
repo-split decision for `client/`.

## System Diagrams

### Request Flow (HTTP -> Domain)
```text
HTTP request
  -> FastAPI app in AINDY/main.py
  -> middleware / execution contract / auth
  -> route handler in AINDY/routes/* or apps/*/routes/*
  -> domain service
  -> syscall dispatcher if crossing domain boundaries
  -> PostgreSQL or MongoDB
  -> normalized response
```

### Flow Execution Path
```text
trigger
  -> AINDY/runtime/flow_engine/runner.py
  -> node executor
  -> syscall dispatch if node crosses domains
  -> memory write via AINDY/db/dao/memory_node_dao.py
  -> deferred embedding via AINDY/memory/embedding_jobs.py
  -> result / events / next step
```

### App Boot Sequence
```text
config and DB setup
  -> plugin / registry load in AINDY/main.py
  -> apps/bootstrap.py
  -> AINDY/platform_layer/bootstrap_graph.py resolves order
  -> core apps boot first
  -> peripheral apps boot or degrade
  -> routers mounted
  -> scheduler, event bus, health surfaces ready
```

## Related Documentation
- Runtime syscall, memory, isolation, and execution contracts live in the separate `aindy-runtime` repo
- [Cross-Domain Coupling](./CROSS_DOMAIN_COUPLING.md)
- [Plugin Registry Pattern](./PLUGIN_REGISTRY_PATTERN.md)
- [Runtime Dependency](../apps/RUNTIME_DEPENDENCY.md)

## Last Verified
2026-05-02
