# A.I.N.D.Y.

A.I.N.D.Y. is a Python/FastAPI runtime and application platform for memory operations, flow execution, Nodus script execution, agent runs, scheduling, and domain application orchestration.

The repository is a modular monolith in transition:
- one deployable backend/runtime
- multiple domain apps under `apps/`
- shared runtime/platform code under `AINDY/`
- one React client under `client/`

This README is intentionally engineering-focused. It describes the repository as it exists today, not the historical product pitch or an aspirational future architecture.

[![CI](https://github.com/Masterplanner25/masterplan-infiniteweave-monday-node-2025-0411/actions/workflows/ci.yml/badge.svg)](https://github.com/Masterplanner25/masterplan-infiniteweave-monday-node-2025-0411/actions/workflows/ci.yml)

## What this repository contains

Backend/runtime:
- [AINDY/](AINDY) - runtime, platform layer, routes, memory, scheduler, agents, worker entrypoints
- [apps/](apps) - domain apps registered into the runtime via bootstrap/registry wiring
- [alembic/](alembic) - SQL schema migrations
- [tests/](tests) - unit, API, and system coverage

Frontend:
- [client/](client) - React/Vite client

Operational/docs:
- [docs/](docs) - current documentation
- [docker-compose.yml](docker-compose.yml) - local/dev container stack
- [server.js](server.js) - optional Node gateway/bridge

## Current system shape

At a high level:

```text
React/Vite client
    |
    v
FastAPI app (AINDY/main.py)
    |
    +-- runtime/platform layers in AINDY/
    +-- domain apps in apps/
    +-- PostgreSQL primary state
    +-- MongoDB for Mongo-backed features
    +-- Redis for distributed execution / event bus / shared cache semantics
```

Important boundaries:
- `AINDY/` owns runtime and platform behavior.
- `apps/` owns domain behavior and registers into the runtime.
- The system is still one deployment unit, not a set of independently deployable services.

## Supported workflows today

Supported and actively implemented:
- authenticated API access with JWT and platform API keys
- memory read/write/recall operations
- flow registration and flow execution
- Nodus script execution, scheduling, and trace lookup
- agent runs and agent observability
- task, analytics, ARM, masterplan, search, social, identity, rippletrace, and other domain workflows through the monolith
- health, readiness, scheduler, and observability surfaces

Do not assume from this that every surface is equally mature or equally production-safe.

## Production-safe today vs transitional

### Production-safe today

Reasonably supported today:
- single-instance deployment with PostgreSQL and the required app configuration
- limited multi-instance deployment when Redis is configured and separate workers are used where required
- lease-gated scheduler leadership
- readiness checks that reflect required runtime expectations
- dynamic registry restore and restart rehydration paths
- degraded startup for explicitly peripheral domains

### Transitional or constrained

Still transitional:
- overall app/runtime boundary cleanup across the full repo
- some legacy or mixed route surfaces preserved for compatibility
- limited multi-instance behavior rather than fully general horizontal scale
- some process-local state and per-instance limits that are acceptable today but not globally coordinated
- mixed Postgres/Mongo operational behavior depending on the feature surface in use
- optional Node gateway path that is not the core backend entrypoint

For deployment guidance, use the deployment docs rather than inferring from old README text.

## Quick start

Prerequisites:
- Python 3.10+
- Node.js 18+
- PostgreSQL
- MongoDB if you need Mongo-backed features
- Redis if you need distributed execution, shared cache semantics, or limited multi-instance deployment

Docker quickstart:

```bash
docker compose up
```

This quickstart runs the API in `EXECUTION_MODE=thread`, so no worker is required. If you want distributed execution, Redis, and a worker process, use the full Compose profile and the production/deployment guidance in [docs/deployment/RUNNING_IN_PRODUCTION.md](docs/deployment/RUNNING_IN_PRODUCTION.md).

Backend:

```powershell
alembic upgrade head
uvicorn AINDY.main:app --reload
```

Frontend:

```powershell
cd client
npm run dev
```

Default local URLs:
- backend: `http://127.0.0.1:8000`
- frontend: `http://localhost:5173`

For production deployment, environment requirements, worker setup, and multi-instance checks, use [docs/deployment/RUNNING_IN_PRODUCTION.md](docs/deployment/RUNNING_IN_PRODUCTION.md).

## Repository layout

```text
AINDY/               Runtime, platform, routes, worker, memory, agents
apps/                Domain apps registered into the runtime
client/              React/Vite frontend
docs/                Engineering and operator documentation
alembic/             Database migrations
tests/               Unit, API, and system tests
server.js            Optional Node gateway
```

## Deployment expectations

Use [docs/deployment/DEPLOYMENT_MODEL.md](docs/deployment/DEPLOYMENT_MODEL.md) as the source of truth for:
- supported single-instance deployment
- limited multi-instance deployment
- API/worker process expectations
- Redis, PostgreSQL, and Mongo requirements
- scheduler leadership behavior
- degraded-mode expectations

## Documentation

| | |
|---|---|
| [Getting Started](docs/getting-started/index.md) | Local bring-up and first API usage |
| [Deployment Model](docs/deployment/DEPLOYMENT_MODEL.md) | Supported topologies, required infra, production caveats |
| [System Spec](docs/architecture/SYSTEM_SPEC.md) | Current architectural specification |
| [Runtime Behavior](docs/runtime/RUNTIME_BEHAVIOR.md) | Startup, scheduler, event bus, execution modes |
| [Execution Contract](docs/runtime/EXECUTION_CONTRACT.md) | Runtime execution guarantees |
| [Syscall System](docs/runtime/SYSCALL_SYSTEM.md) | Versioned syscall layer and scope |
| [OS Isolation Layer](docs/runtime/OS_ISOLATION_LAYER.md) | Resource management, waits, distributed resume caveats |
| [Plugin Registry Pattern](docs/architecture/PLUGIN_REGISTRY_PATTERN.md) | How apps integrate with runtime-owned surfaces |
| [API Contracts](docs/platform/interfaces/API_CONTRACTS.md) | Route and platform interface contracts |
| [Testing Strategy](docs/platform/engineering/TESTING_STRATEGY.md) | Test structure and reliability focus |
| [Full Docs Index](docs/index.md) | Complete docs entry point |

## Legacy context

This repository still contains historical product framing and compatibility surfaces from earlier A.I.N.D.Y. and Masterplan Infinite Weave iterations.

Treat that material as legacy context unless it is clearly referenced from the current docs index. The primary current system lives in:
- `AINDY/`
- `apps/`
- `client/`
- `docs/`
