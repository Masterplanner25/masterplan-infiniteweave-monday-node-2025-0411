# SYSTEM_SPEC

This document is the current high-level architectural specification for the repository.

It is intentionally conservative. It describes what the codebase is today, not what it may become after further boundary cleanup.

## 1. System purpose

- A.I.N.D.Y. is a FastAPI-based runtime and application platform.
- It provides memory operations, flow execution, Nodus execution, scheduling, agent execution, observability, and domain application orchestration.
- The repository is a modular monolith: multiple domain apps share one runtime and one deployment unit.
- Primary backend entry point: `AINDY/main.py`.

## 2. Top-level repository shape

```text
client/              React/Vite frontend
server.js            Optional Node gateway/bridge

AINDY/               Runtime, platform, routes, worker, memory, agents
apps/                Domain apps registered into the runtime
alembic/             PostgreSQL schema migrations
tests/               Unit, API, and system coverage
docs/                Engineering and operator documentation
```

## 3. Runtime shape

```text
React/Vite client
        |
        v
FastAPI app (AINDY/main.py)
  - lifespan startup/shutdown
  - router registration
  - auth, rate limiting, health/readiness
        |
        +--> AINDY/platform_layer/*
        |     runtime-owned interfaces, registry, health, scheduler services
        |
        +--> AINDY/runtime/*, AINDY/kernel/*, AINDY/core/*
        |     flow engine, execution, event bus, waits, retries, worker queue
        |
        +--> apps/*
        |     domain apps bootstrapped into the runtime
        |
        +--> AINDY/db/*
              PostgreSQL models/DAO/migrations integration
              Mongo integration for Mongo-backed features
```

Notes:
- `server.js` is optional and not the core backend entry point.
- `apps/` is not a separate deployment layer; it is domain code inside the monolith.
- Runtime/platform boundaries have been tightened in several areas, but the system is still in transition rather than fully "clean platform / clean apps".

## 4. App/platform relationship

Current contract:
- `AINDY/` owns runtime and platform concerns.
- `apps/` owns domain behavior and registers routers, jobs, flows, handlers, and bootstrap metadata into runtime-owned interfaces.
- `apps/bootstrap.py` resolves app bootstrap order and publishes degraded-domain state into runtime-owned registry state.

This means:
- domains are modular in code organization
- they are not independently deployable services
- cross-domain interaction still exists and is allowed inside the monolith, but it should go through explicit contracts where possible

## 5. Core execution layers

- API layer: `AINDY/routes/*`
- Route execution pipeline: `AINDY/core/execution_pipeline.py`, `AINDY/core/execution_helper.py`
- Runtime/platform layer: `AINDY/platform_layer/*`
- Flow execution layer: `AINDY/runtime/*`, `AINDY/kernel/*`
- Agent runtime: `AINDY/agents/*`
- Domain applications: `apps/*`
- Data layer: `AINDY/db/*`, Alembic migrations

## 6. Data systems

- Primary system of record: PostgreSQL
- Secondary document store: MongoDB for Mongo-backed feature surfaces
- Redis: required for distributed execution, event-bus behavior, shared production cache semantics, and limited multi-instance deployment
- Some caches and operational state remain process-local unless explicitly backed by Redis or DB persistence

## 7. Startup and runtime behavior

Current startup behavior includes:
- runtime state reset and startup contract publication
- secret/config guards
- Redis/event-bus production guards where required
- schema enforcement
- queue backend validation
- scheduler lease/leadership behavior
- flow and node registration
- dynamic registry restore
- event-bus subscriber startup
- waiting execution rehydration
- degraded peripheral-domain reporting

See:
- [Runtime Behavior](../runtime/RUNTIME_BEHAVIOR.md)
- [Deployment Model](../deployment/DEPLOYMENT_MODEL.md)

## 8. Deployment model

Supported today:
- single-instance deployment
- limited multi-instance deployment with Redis and explicit worker processes

Not supported as a clean service mesh or microservice platform:
- independently deployed domain apps
- arbitrary multi-instance scale without Redis-backed coordination
- assuming every runtime invariant is globally coordinated across instances

## 9. Current architectural invariants

- PostgreSQL is required for primary runtime/app state.
- Scheduler leadership is single-instance through the lease path.
- Distributed execution requires Redis and healthy workers.
- Readiness is expected to reflect required runtime dependencies, not just process liveness.
- Peripheral-domain degraded startup is allowed in some cases; core-domain bootstrap failure is not.
- Runtime-owned code should not depend directly on app-private bootstrap state.
- New client and backend surfaces should prefer explicit ownership boundaries over compatibility shortcuts.

## 10. Current constraints and transitional areas

- The backend remains one monolith.
- Some legacy routes and mixed ownership surfaces still exist for compatibility.
- Some process-local state remains acceptable today but is not ideal for full horizontal scale.
- Some external-provider and mixed-datastore behaviors remain operationally constrained.
- Frontend API ownership is clearer than before, but some backend route ownership is still historically mixed.

Those are transitional constraints, not reasons to describe the system as cleaner than it is.
