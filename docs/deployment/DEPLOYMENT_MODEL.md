# Deployment Model

This document describes the deployment shapes that A.I.N.D.Y. supports today, based on the current runtime code and startup guards.

This is an operator document. It does not describe aspirational architecture. If a topology is not listed here as supported, treat it as unsupported.

## Supported deployment model

### 1. Single-instance deployment

Supported today for:
- local development
- test and staging
- limited production use with one API instance

Shape:
- 1 FastAPI API process
- 0 separate worker processes when `EXECUTION_MODE=thread`
- PostgreSQL required
- MongoDB required only if your enabled product surface depends on Mongo-backed features
- Redis optional in development, optional in some single-instance production paths, but strongly recommended if you need distributed execution or shared cache semantics

This is the simplest and safest deployment shape if you do not need horizontal scaling.

### 2. Limited multi-instance deployment

Supported today with constraints for:
- multiple API instances behind a load balancer
- one or more separate worker processes
- Redis-backed queue/event-bus behavior
- single scheduler leader elected through the DB lease path

Shape:
- 2+ FastAPI API instances
- 1+ worker processes when `EXECUTION_MODE=distributed`
- PostgreSQL required
- Redis required
- MongoDB required only for Mongo-backed features

This mode is limited production-capable, not fully general horizontal scale. It is intended for controlled multi-instance operation, not arbitrary stateless scale-out of every subsystem.

## Unsupported or unsafe patterns

Do not treat these as supported today:

- Multi-instance deployment without Redis
  - Cross-instance WAIT/RESUME and event propagation become local-only.
- Production deployment with `EXECUTION_MODE=distributed` but no worker process
  - The API may accept work, but readiness should fail because async work cannot actually execute.
- Production deployment with Redis-required settings but `AINDY_EVENT_BUS_ENABLED=false`
  - Startup is guarded against this because it is unsafe for distributed resume behavior.
- Production deployment with per-process memory cache relied on for shared semantics
  - In production, cache must be Redis-backed or explicitly disabled.
- Multiple scheduler leaders
  - Only one lease leader is intended to run APScheduler jobs.
- Treating degraded peripheral domains as invisible
  - Degraded startup is intentional for some peripheral domains, but it is surfaced in health/readiness and should be monitored.
- Assuming every runtime invariant is globally distributed
  - Some state is still process-local by design or by current limitation.

## Required infrastructure by environment

### Production minimum

Required:
- PostgreSQL
- Alembic migrations applied to head
- Strong `SECRET_KEY`
- Explicit `ALLOWED_ORIGINS`

Required when using distributed execution or limited multi-instance deployment:
- Redis
- `EXECUTION_MODE=distributed`
- one or more worker processes
- event bus enabled

Required when your enabled features use Mongo-backed functionality:
- MongoDB

Recommended:
- dedicated API and worker process supervision
- readiness checks on `/ready`
- scheduler status monitoring
- durable log and metric collection

### Development minimum

Required:
- PostgreSQL
- `SECRET_KEY`

Optional in local bring-up:
- Redis
- worker process
- MongoDB, if you are not exercising Mongo-backed features

Development is intentionally more permissive. The runtime allows local bring-up paths that production startup will reject.

## Process model

### API process

Entrypoint:

```bash
uvicorn AINDY.main:app
```

What the API process does at startup:
- validates `SECRET_KEY`
- enforces Redis/event-bus production guards where required
- validates queue backend availability when applicable
- enforces schema drift checks when enabled
- initializes cache backend
- initializes Mongo connectivity when required
- registers runtime flows and nodes
- restores dynamic platform registry state from the DB
- starts the event-bus subscriber
- rehydrates waiting execution state
- acquires background-task lease and starts APScheduler only on the leader

What can fail startup:
- missing required Redis in production-style deployments
- event bus disabled in Redis-required deployments
- schema drift
- missing required flow nodes in production
- required event-bus subscriber startup failure
- insecure production secret configuration

### Worker process

Entrypoint:

```bash
python -m AINDY.worker.__main__
```

Worker contract:
- intended only for `EXECUTION_MODE=distributed`
- requires queue backend readiness
- requires background-task schema readiness
- writes worker heartbeat to Redis
- performs immediate stale-job recovery on startup
- continues periodic stale-job recovery while running

Operational expectation:
- if the API is in distributed execution mode, at least one healthy worker must be running
- worker absence is a readiness problem, not just an observability issue

## Data stores and supporting services

### PostgreSQL

PostgreSQL is the primary required system of record.

It currently backs:
- auth and ownership data
- flow and execution state
- scheduler lease state
- dynamic platform registry persistence
- health and observability records

Operational rule:
- run `alembic upgrade head` before exposing the API in production

### MongoDB

MongoDB is optional only if you are not using the Mongo-backed feature set.

Treat MongoDB as required when your deployment includes:
- social-layer features
- Mongo-backed identity/profile features
- any route or flow path that depends on Mongo documents rather than solely PostgreSQL-backed state

Current runtime behavior is fail-fast when Mongo is required and unavailable.

### Redis

Redis is required for:
- limited multi-instance deployments
- distributed execution mode
- shared cache semantics in production
- distributed event bus behavior
- worker heartbeat visibility

Redis is optional for:
- local development
- single-instance thread-mode API bring-up

Operational rule:
- if you need shared runtime behavior across instances, configure Redis explicitly and treat it as part of the core production stack

## Scheduler behavior

Scheduler behavior today:
- APScheduler is started only on the DB lease leader
- follower API instances still serve traffic but do not run scheduled jobs
- scheduler leadership is visible through observability and readiness surfaces

This is the supported pattern for multi-instance API deployment:
- many API instances may exist
- exactly one should be the active scheduler leader at a time

## Degraded-mode expectations

Degraded startup is intentional for some peripheral domains.

Current contract:
- core domain bootstrap failure is startup-fatal
- peripheral domain bootstrap failure may be tolerated
- tolerated failures are published as degraded domains through runtime-owned state
- `/health` and `/ready` expose degraded-domain information

Operator meaning:
- degraded peripheral domains do not automatically mean the platform is down
- they do mean part of the product surface is unavailable or reduced
- production rollout should treat repeated degraded domains as an incident signal, not normal background noise

## Environment variables with operational impact

The following settings matter for deployment behavior:

- `ENV`
- `DATABASE_URL`
- `SECRET_KEY`
- `ALLOWED_ORIGINS`
- `AINDY_ENFORCE_SCHEMA`
- `AINDY_ENABLE_BACKGROUND_TASKS`
- `EXECUTION_MODE`
- `REDIS_URL`
- `AINDY_REQUIRE_REDIS`
- `AINDY_EVENT_BUS_ENABLED`
- `AINDY_CACHE_BACKEND`
- `MONGO_URL`
- `MONGO_DB_NAME`
- `WORKER_CONCURRENCY`
- `WORKER_MAX_CONCURRENT_JOBS`
- `WORKER_VISIBILITY_TIMEOUT_SECS`
- `WORKER_STALE_CHECK_INTERVAL_SECS`

## Startup order

Recommended production order:

1. Start PostgreSQL.
2. Start MongoDB if your enabled features require it.
3. Start Redis if using multi-instance or distributed execution.
4. Run `alembic upgrade head`.
5. Start API instances.
6. Start worker processes if `EXECUTION_MODE=distributed`.
7. Verify `/ready` and scheduler status before exposing traffic broadly.

## Health and readiness interpretation

Use:
- `/health` for liveness and dependency visibility
- `/ready` for deployment readiness

Readiness reflects:
- startup completion
- required Postgres/Redis/queue/schema conditions
- scheduler expectations for the current role
- event-bus readiness when required
- worker heartbeat when distributed execution is required
- degraded peripheral domains as surfaced context

Do not route production traffic based only on process liveness.

## Known limitations and caveats

Current known limitations:
- multi-instance support is limited, not fully elastic
- some operational state remains process-local by design
- Mongo is not a universal readiness gate for every deployment, so feature selection still matters
- collective restart windows remain less robust than a fully durable event-stream design
- not every subsystem is globally coordinated through Redis-backed state
- per-instance limits and local caches still exist in some areas and should not be assumed to be globally consistent

For deeper runtime details, see:
- [Runtime Behavior](../runtime/RUNTIME_BEHAVIOR.md)
- [OS Isolation Layer](../runtime/OS_ISOLATION_LAYER.md)
- [Multi-Instance Resume](../architecture/MULTI_INSTANCE_RESUME.md)
- [Migration Policy](./MIGRATION_POLICY.md)

## Practical recommendation

If you need the most predictable production operation today, use one of these:

1. Single API instance, `EXECUTION_MODE=thread`, PostgreSQL, Mongo only if needed, Redis optional.
2. Multiple API instances plus separate workers, with PostgreSQL and Redis, and with the understanding that this is a limited multi-instance deployment model rather than a fully general horizontally scalable control plane.
