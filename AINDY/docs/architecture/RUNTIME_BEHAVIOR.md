# Runtime Behavior

This document describes the current runtime behavior of the FastAPI backend as implemented in [`main.py`](/C:/dev/masterplan-infiniteweave-monday-node-2025-0411/AINDY/main.py).

## 1. Application Startup Flow
- Entry point is `AINDY/main.py`.
- The FastAPI app is created with a single `lifespan` context manager. Deprecated `@app.on_event("startup")` handlers are no longer used.
- Startup sequence:
  1. Initialize cache backend via `AINDY_CACHE_BACKEND` (`memory` by default, `redis` if configured).
  2. Enforce `SECRET_KEY` safety rules. Production startup fails if the placeholder secret is still configured.
  3. Enforce schema drift guard when `AINDY_ENFORCE_SCHEMA=true` by comparing the current Alembic revision to head.
  4. Attempt to acquire the background-task leadership lease via `task_services.start_background_tasks(...)`.
  5. Start APScheduler only on the lease-holder instance via `services.scheduler_service.start()`.
  6. Register canonical flow-engine nodes and flows via `services.flow_definitions.register_all_flows()`.
  7. Optionally scan and recover stuck flow/agent runs.
  8. Seed or refresh the internal `author-system` identity row.
- Router registration occurs by iterating `ROUTERS` from `AINDY/routes/__init__.py`.
- `main.py` now serves only the root route directly; domain endpoints are router-backed.

## 2. Background Task Lifecycle
- Background execution is no longer driven by daemon threads in `main.py`.
- Inter-instance coordination is handled by a DB lease in `services/task_services.py`.
- Only the lease leader starts APScheduler jobs.
- Lease timestamps are normalized to timezone-aware UTC in Python before comparison or persistence.
- Scheduler lifecycle:
  - startup: `task_services.start_background_tasks(...)` -> `scheduler_service.start()`
  - shutdown: `task_services.stop_background_tasks(...)` -> `scheduler_service.stop()`
- This prevents follower instances from starting duplicate background schedulers.

## 3. Database Session Lifecycle
- Per-request SQLAlchemy sessions are provided by `get_db()` in `AINDY/db/database.py`.
- Startup and shutdown logic in `main.py` uses explicit `SessionLocal()` blocks with `try/finally`.
- Request metrics middleware creates its own short-lived session to persist `RequestMetric` rows.
- MongoDB uses a process-level client singleton in `AINDY/db/mongo_setup.py`; there is still no explicit shutdown close.

## 4. Execution Registration
- Canonical flow execution is registered during startup from `services.flow_definitions`.
- The flow engine is a first-class runtime component and is not a side utility.
- Current execution-facing domains route through flows and/or orchestrators rather than ad hoc route logic:
  - task
  - memory execution
  - genesis message handling
  - watcher ingest
  - agent runtime

## 5. Middleware, Logging, and Error Handling
- Rate limiting is enabled via SlowAPI middleware.
- CORS is explicit-origin only via `ALLOWED_ORIGINS`; wildcard origins are not used.
- Request logging:
  - request-scoped `trace_id` and request IDs are generated per request
  - `X-Trace-ID` and `X-Request-ID` are added to every response
  - request completion is logged as JSON
  - `RequestMetric` rows are persisted for observability
- `SystemEvent` is the canonical durable activity ledger for execution and observability.
- Required execution lifecycle events are emitted on core execution paths.
- Required outbound lifecycle events are emitted for instrumented external interactions through `services/external_call_service.py`.
- Successful non-flow operational paths now also emit durable events where implemented, including:
  - `health.liveness.completed`
  - `health.readiness.completed`
  - `auth.register.completed`
  - `auth.login.completed`
- Async heavy-execution jobs now emit:
  - `execution.started` immediately on submission
  - `async_job.started` when the worker begins queued execution
  - `async_job.completed` or `async_job.failed` for queued worker outcome
  - `execution.completed` or `execution.failed` as the canonical execution ledger events
- Required `SystemEvent` persistence failures now attempt a fallback `error.system_event_failure` record and then raise fail-closed.
- Global exception handlers normalize responses for:
  - `HTTPException`
  - `RequestValidationError`
  - unhandled exceptions

## 6. Shutdown Behavior
- Shutdown is handled in the same `lifespan` context manager.
- Current shutdown actions:
  - stop background task leadership/heartbeat
  - stop APScheduler
- This is materially different from the older daemon-thread model. The app now has an explicit shutdown path.

## 7. Runtime Risks That Still Exist
- External model calls are still synchronous in several request paths and can increase request latency.
- MongoDB remains late-bound and optional; failed Mongo writes are still not uniformly fatal.
- Request metrics persistence is best-effort; failures are logged and swallowed.
- The app is still a monolith: API, scheduler leadership, orchestration, and some execution logic share the same process.
- Not every domain has a first-class execution-record model yet, even though trace propagation and `SystemEvent` coverage are much stronger.
