---
title: "A.I.N.D.Y. Internals"
last_verified: "2026-04-19"
api_version: "1.0"
status: current
owner: "platform-team"
---
# A.I.N.D.Y. Internals

Developer reference for the AINDY/ directory — structure, runtime notes, and
Nodus host function inventory. For the public-facing platform description see
the root [README.md](../../README.md). For architecture decisions see
[docs/architecture/SYSTEM_SPEC.md](SYSTEM_SPEC.md).

## Overview

A.I.N.D.Y. is a FastAPI-based backend that combines:
- task execution and scoring
- memory persistence and retrieval
- identity boot activation after auth
- agent execution (GPT-4o planner, trust gate, deterministic Nodus-backed executor)
- Genesis/masterplan planning flows
- ARM analysis/generation
- RippleTrace analytics and graph endpoints
- social/network bridge integrations
- **Nodus language runtime** — scripts execute via `POST /platform/nodus/run`; full memory/event/flow access; cron scheduling; per-call trace capture

The system is a modular monolith, not a microservice fleet.

**Classification (2026-04-06):** OS-LIKE — PRODUCTION READY. A.I.N.D.Y. is a language-executing OS-like runtime. Every request enters a shared execution pipeline, creates an ExecutionUnit, delegates all DB work to domain services, and receives an auto-injected execution envelope. The ExecutionDispatcher is the sole authority for async decisions. Nodus scripts can read/write memory, emit events, trigger flows, schedule themselves, and be called from the CLI or any external system via the Platform API.

## Current Structure

```text
AINDY/
├── main.py                         # FastAPI bootstrap, lifespan, middleware, root route
├── cli.py                          # Standalone Nodus CLI (nodus run/trace/upload → API)
├── routes/                         # Active API surface
│   ├── legacy_surface_router.py    # Restored compatibility endpoints
│   ├── task_router.py
│   ├── memory_router.py
│   ├── genesis_router.py
│   ├── watcher_router.py
│   ├── agent_router.py
│   ├── platform_router.py          # Platform API keys, Nodus run/flow/schedule/trace/upload
│   └── ...
├── services/                       # Domain services, orchestration, scheduler, flow engine
│   ├── nodus_runtime_adapter.py    # PersistentFlowRunner, _make_traced, host-function wiring
│   ├── nodus_memory_builtins.py    # memory.recall/write/search namespace
│   ├── nodus_event_builtins.py     # event.emit/wait namespace, NodusWaitSignal
│   ├── nodus_flow_compiler.py      # flow.step() DSL, NodusFlowGraph, compile_nodus_flow
│   ├── nodus_schedule_service.py   # Cron job CRUD + run_due_jobs (leader-gated)
│   ├── nodus_trace_service.py      # query_nodus_trace, build_trace_summary
│   ├── syscall_dispatcher.py       # SyscallDispatcher — single entry point for all sys.v*.* calls
│   ├── syscall_registry.py         # VersionedSyscallRegistry, SyscallEntry, register_syscall
│   ├── syscall_versioning.py       # SyscallSpec, parse_syscall_name, validate_payload, resolve_version
│   ├── syscall_handlers.py         # All 20+ domain syscall handlers; register_all_domain_handlers()
│   ├── memory_address_space.py     # MAS path utilities: normalize, parse, build, tree ops, legacy compat
│   ├── os_layer.py                 # TenantContext, OS isolation primitives
│   ├── resource_manager.py         # ResourceManager — quota check + usage recording
│   ├── scheduler_engine.py         # SchedulerEngine — priority scheduling, WAIT/RESUME
│   └── ...
├── runtime/                        # Memory/runtime execution components
├── db/                             # Models, DAO layer, database setup, migrations
│   └── models/
│       ├── nodus_trace_event.py    # Per-host-call trace record
│       ├── nodus_scheduled_job.py  # Cron-scheduled Nodus jobs
│       └── ...
├── bridge/                         # Active memory/Nodus bridge runtime code
│   ├── bridge.py
│   ├── nodus_memory_bridge.py
│   └── memory_bridge_rs/
├── legacy/                         # Archived prototypes and bridge tools
│   ├── prototypes/
│   └── bridge_tools/
├── client/                         # React frontend
└── docs/                           # Architecture, interfaces, roadmap, governance
```

## Runtime Notes

- `main.py` no longer owns a pile of direct domain endpoints.
- Domain routes are registered from `routes/__init__.py`.
- Legacy frontend/API compatibility routes were moved out of `main.py` and restored in `routes/legacy_surface_router.py`.
- Background work is lease-gated and APScheduler-backed, not daemon-thread driven.
- Canonical execution now centers on the flow engine and orchestrators.
- `SystemEvent` is the canonical durable activity ledger for execution and observability.
- Request-scoped `trace_id` is propagated through execution, loops, agent runs, memory writes, logs, and events.
- Outbound OpenAI/HTTP/watcher interactions are instrumented through `services/external_call_service.py` with required lifecycle events.
- Authenticated app activation now uses `GET /identity/boot` to hydrate memory, agent runs, metrics, and active flows immediately after JWT login.
- `identity.boot` is a required fail-closed `SystemEvent`.
- All Nodus script execution runs through `PersistentFlowRunner(NODUS_SCRIPT_FLOW)` — same path for API, CLI, scheduled, and agent-triggered runs.
- Nodus host functions (11 total: recall, recall_tool, recall_from, recall_all, suggest, remember, record_outcome, share, emit, set_state, get_state) are wrapped by `_make_traced()` at runtime; every call produces a `NodusTraceEvent` row.
- Trace ID = `context.execution_unit_id`; query via `GET /platform/nodus/trace/{trace_id}`.
- Platform API keys (scoped capabilities) gate all `/platform/*` endpoints; managed via `POST/GET/DELETE /platform/keys`.
- Dynamic registry (flows/nodes/webhooks) is persisted to DB and restored on startup by `platform_loader.py`.
- All cross-boundary calls from Nodus scripts route through `SyscallDispatcher` — the single gated interface for memory, flow, and event operations. See [docs/runtime/SYSCALL_SYSTEM.md](../runtime/SYSCALL_SYSTEM.md).
- Syscalls are versioned (`sys.v1.*`, `sys.v2.*`); every call declares an ABI contract (input/output schema, deprecation status). Introspect via `GET /platform/syscalls`.
- Memory nodes are path-addressable via the Memory Address Space (MAS): `/memory/{tenant}/{namespace}/{addr_type}/{node_id}`. MAS endpoints: `GET /platform/memory`, `GET /platform/memory/tree`, `GET /platform/memory/trace`. See [docs/runtime/MEMORY_ADDRESS_SPACE.md](../runtime/MEMORY_ADDRESS_SPACE.md).
- The OS Isolation Layer enforces tenant isolation and resource quotas on every syscall dispatch. See [docs/runtime/OS_ISOLATION_LAYER.md](../runtime/OS_ISOLATION_LAYER.md).

## Development

Typical startup:

```bash
alembic upgrade head
uvicorn main:app --reload
```

Optional additional processes:

```bash
node server.js
cd client && npm run dev
```

## Documentation

Key current docs:

| Doc | Path |
|---|---|
| System Spec | [docs/architecture/SYSTEM_SPEC.md](SYSTEM_SPEC.md) |
| Plugin Registry Pattern | [docs/architecture/PLUGIN_REGISTRY_PATTERN.md](PLUGIN_REGISTRY_PATTERN.md) |
| Cross-Domain Coupling | [docs/architecture/CROSS_DOMAIN_COUPLING.md](CROSS_DOMAIN_COUPLING.md) |
| Runtime Behavior | [docs/runtime/RUNTIME_BEHAVIOR.md](../runtime/RUNTIME_BEHAVIOR.md) |
| Execution Contract | [docs/runtime/EXECUTION_CONTRACT.md](../runtime/EXECUTION_CONTRACT.md) |
| Execution Audit | [docs/runtime/EXECUTION_AUDIT.md](../runtime/EXECUTION_AUDIT.md) |
| Syscall System | [docs/runtime/SYSCALL_SYSTEM.md](../runtime/SYSCALL_SYSTEM.md) |
| Memory Address Space | [docs/runtime/MEMORY_ADDRESS_SPACE.md](../runtime/MEMORY_ADDRESS_SPACE.md) |
| OS Isolation Layer | [docs/runtime/OS_ISOLATION_LAYER.md](../runtime/OS_ISOLATION_LAYER.md) |
| Agent Runtime | [docs/runtime/AGENT_RUNTIME.md](../runtime/AGENT_RUNTIME.md) |
| API Contracts | [docs/platform/interfaces/API_CONTRACTS.md](../platform/interfaces/API_CONTRACTS.md) |
| Deployment Model | [docs/deployment/DEPLOYMENT_MODEL.md](../deployment/DEPLOYMENT_MODEL.md) |
