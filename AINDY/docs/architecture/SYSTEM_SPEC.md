# SYSTEM_SPEC

This document is the current architectural specification for the A.I.N.D.Y. repository.

## 1. System Purpose
- A.I.N.D.Y. is a FastAPI-based backend for task execution, planning, memory persistence, scoring, agent execution, ARM analysis, RippleTrace analytics, and social/network integrations.
- The system is a monolith with multiple domains sharing one runtime and one deployment unit.
- Primary backend entry point: `AINDY/main.py`.

## 2. Top-Level Architecture
```text
React/Vite client (client/)
        |
        v
Node gateway (server.js) [optional]
        |
        v
FastAPI app (main.py)
  - lifespan startup/shutdown
  - 31 routers
  - JWT auth, API key auth, rate limiting
  - request metrics + structured error handlers
        |
        +--> routes/*
        |     - task
        |     - memory
        |     - genesis
        |     - watcher
        |     - ARM
        |     - analytics / rippletrace / dashboard
        |     - legacy compatibility surface
        |
        +--> services/*
        |     - flow engine
        |     - infinity orchestrator
        |     - agent runtime
        |     - scheduler / automation
        |     - memory services
        |
        +--> data layer
              - PostgreSQL via SQLAlchemy/Alembic
              - MongoDB for social-layer documents
              - optional Redis cache
```

## 3. Runtime Model
- `main.py` owns app bootstrapping, middleware, lifespan, and root route only.
- Routers are registered from `routes/__init__.py`.
- Background scheduling is lease-gated and APScheduler-backed.
- Canonical execution flows are registered at startup via `services.flow_definitions.register_all_flows()`.
- Compatibility routes that used to live directly in `main.py` now live in `routes/legacy_surface_router.py`.

## 4. Core Execution Layers
- API layer: `routes/*`
- Service/orchestration layer: `services/*`
- Flow execution layer: `services/flow_engine.py`
- Agent runtime: `services/agent_runtime.py`, `services/nodus_adapter.py`
- Memory runtime: `runtime/memory/*`
- Data layer: `db/models/*`, `db/dao/*`, Alembic migrations

## 5. Data Systems
- Primary DB: PostgreSQL
- Social/document DB: MongoDB
- Cache: in-memory by default, Redis optionally
- User ownership is now UUID-based and enforced across normalized tables.

## 6. Execution Contract
Canonical execution shape:

`Input -> Execution -> Persist -> Orchestrator -> Observability`

The codebase now documents this contract in:
- `docs/architecture/EXECUTION_CONTRACT.md`
- `docs/architecture/EXECUTION_AUDIT.md`

Standard execution output shape:
```json
{
  "status": "...",
  "result": "...",
  "events": [...],
  "next_action": "...",
  "trace_id": "..."
}
```

System-wide activity ledger:
- `SystemEvent` is the canonical durable record of execution and observability activity.
- Core execution paths emit required lifecycle events.
- Successful health, auth, and async heavy-execution paths now emit durable success events in addition to core flow execution paths.
- External interactions now also emit required lifecycle events through `services/external_call_service.py`.
- Required outbound event types:
  - `external.call.started`
  - `external.call.completed`
  - `external.call.failed`
  - `error.external_call`

## 7. Memory and Agentics
- Memory APIs are split between legacy bridge compatibility (`/bridge/*`) and canonical memory APIs (`/memory/*`).
- Agent execution is implemented, persisted, and observable; it is no longer a future-only concept.
- Flow runs, agent runs, steps, and events are persisted and replayable to a meaningful degree.
- Agent execution is now fail-closed on missing scoped capability tokens; an approved run without `capability_token` does not execute.
- `/memory/nodus/execute` is no longer an unrestricted host embedding path. It is now route-gated by source validation, operation allowlists, and optional scoped capability enforcement for write-capable operations.

## 8. RippleTrace
- RippleTrace includes both canonical `/rippletrace/*` routes and a restored compatibility surface for older dashboard/graph endpoints.
- Graph and narrative endpoints such as `/influence_graph`, `/causal_graph`, and `/narrative/{drop_point_id}` are now served through `routes/legacy_surface_router.py`.

## 9. Invariants
- PostgreSQL is required for primary app state.
- JWT/API-key guards remain mandatory on protected routes.
- Schema drift can block startup.
- Scheduler leadership is single-instance.
- Background lease timestamps are compared and persisted as timezone-aware UTC values in the lease path.
- Execution responses should be traceable and structured.
- Agent/tool execution must be capability-scoped.
- Silent `except ...: pass` behavior is not allowed in production execution paths.
- External calls are not allowed to bypass `SystemEvent` emission.
- Failure to emit a required `SystemEvent` is execution-fatal for the calling external interaction.

## 10. Known Architectural Constraints
- The backend remains a monolith.
- Some domains still rely on synchronous external model calls.
- Mongo side effects are not coordinated with Postgres through an outbox/event bus.
- Legacy compatibility routes preserve old clients, but they also preserve historical surface area.
- Watcher signal delivery is background-threaded and retrying; required outbound event emission fails the send attempt, but the emitter still follows its retry/drop policy instead of crashing the producer path.
