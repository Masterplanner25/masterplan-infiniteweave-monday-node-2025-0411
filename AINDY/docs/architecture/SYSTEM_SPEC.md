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
  - ~30 routers by default, plus optional legacy surface routing
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
- Route execution pipeline: `core/execution_pipeline.py`, `core/execution_helper.py`
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

Standard execution output shape for canonical execution surfaces:
```json
{
  "status": "...",
  "data": "...",
  "result": "...",
  "events": [...],
  "next_action": "...",
  "trace_id": "..."
}
```

System-wide activity ledger:
- `SystemEvent` is the canonical durable record for core execution and observability activity, while some subsystems still retain domain-specific durable records such as agent events, flow history, and automation logs.
- `SystemEvent` now carries `trace_id`, `parent_event_id`, and `source`, allowing causal reconstruction across core execution paths.
- RippleTrace now structures execution causality on top of `SystemEvent` through `ripple_edges`, including event-to-event and event-to-memory links.
- Core execution paths emit required lifecycle events. Route-layer execution is now split between the newer fail-open route pipeline in `core/execution_pipeline.py` and older service-level wrappers/canonical envelopes, so execution normalization is stronger but still not perfectly single-path across the repo.
- Successful health, auth, and async heavy-execution paths now emit durable success events in addition to core flow execution paths.
- External interactions now also emit required lifecycle events through `services/external_call_service.py`.
- Required outbound event types:
  - `external.call.started`
  - `external.call.completed`
  - `external.call.failed`
  - `error.external_call`

## 7. Memory and Agentics
- Memory APIs are split between legacy bridge compatibility (`/bridge/*`) and canonical memory APIs (`/memory/*`).
- Memory nodes can now store causal execution context (`source_event_id`, `root_event_id`, `causal_depth`, `impact_score`, `memory_type`) in addition to content, embeddings, and feedback metadata.
- High-impact execution outcomes (`execution.completed`, `execution.failed`, `capability.denied`) can now auto-materialize into Memory Bridge records through the `SystemEvent` path.
- Agent execution is implemented, persisted, and observable; it is no longer a future-only concept.
- Flow runs, agent runs, steps, and events are persisted and replayable to a meaningful degree.
- Agent execution is now fail-closed on missing scoped capability tokens; an approved run without `capability_token` does not execute.
- `/memory/nodus/execute` is no longer an unrestricted host embedding path. It is now route-gated by source validation, operation allowlists, and optional scoped capability enforcement for write-capable operations.
- Agent execution now receives pre-run memory context shaped into `similar_past_outcomes`, `relevant_failures`, and `successful_patterns`.

## 8. RippleTrace
- RippleTrace includes both canonical `/rippletrace/*` routes and a restored compatibility surface for older dashboard/graph endpoints.
- Graph and narrative endpoints such as `/influence_graph`, `/causal_graph`, and `/narrative/{drop_point_id}` are now served through `routes/legacy_surface_router.py`.
- Execution-side RippleTrace is now also represented in `routes/observability_router.py` via trace-graph APIs backed by `SystemEvent` + `ripple_edges`.

## 9. Invariants
- PostgreSQL is required for primary app state.
- JWT/API-key guards remain mandatory on protected routes.
- Schema drift can block startup.
- Scheduler leadership is single-instance.
- Background lease timestamps are compared and persisted as timezone-aware UTC values in the lease path.
- Canonical execution responses should be traceable and structured.
- A `trace_id` should be present on all major route responses. Auth, analytics, ARM, main-calculation, and memory routes now also enter the shared route execution pipeline, though some non-target route groups still return raw JSON outside that path.
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
