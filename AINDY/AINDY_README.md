# A.I.N.D.Y.

Core backend for the Masterplan Infinite Weave project.

## Overview

A.I.N.D.Y. is a FastAPI-based backend that combines:
- task execution and scoring
- memory persistence and retrieval
- agent execution
- Genesis/masterplan planning flows
- ARM analysis/generation
- RippleTrace analytics and graph endpoints
- social/network bridge integrations

The system is a modular monolith, not a microservice fleet.

## Current Structure

```text
AINDY/
├── main.py                         # FastAPI bootstrap, lifespan, middleware, root route
├── routes/                         # Active API surface
│   ├── legacy_surface_router.py    # Restored compatibility endpoints
│   ├── task_router.py
│   ├── memory_router.py
│   ├── genesis_router.py
│   ├── watcher_router.py
│   ├── agent_router.py
│   └── ...
├── services/                       # Domain services, orchestration, scheduler, flow engine
├── runtime/                        # Memory/runtime execution components
├── db/                             # Models, DAO layer, database setup, migrations
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
- `docs/architecture/SYSTEM_SPEC.md`
- `docs/architecture/RUNTIME_BEHAVIOR.md`
- `docs/architecture/EXECUTION_CONTRACT.md`
- `docs/architecture/EXECUTION_AUDIT.md`
- `docs/interfaces/API_CONTRACTS.md`
- `docs/engineering/DEPLOYMENT_MODEL.md`
