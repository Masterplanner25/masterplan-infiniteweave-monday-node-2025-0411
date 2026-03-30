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
- `SystemEvent` is the canonical durable ledger for core execution and observability, but some subsystems still retain parallel domain-specific durable records such as `AgentEvent`, `FlowHistory`, and async automation logs.
- `SystemEvent` propagation now carries `trace_id`, `parent_event_id`, and `source`, allowing parent -> child reconstruction across core execution paths.
- `RippleEdge` rows are now created from `SystemEvent` parentage and can additionally link source events to stored memory nodes.
- Required execution lifecycle events are emitted on core execution paths.
- Research, LeadGen, Freelance, Agent, Automation, Task, Goals, and Genesis route executions now share the centralized execution wrapper (`services/execution_service.py`) or pass through canonical execution envelopes that standardize `trace_id`, lifecycle events, and response shape.
- Auth, Analytics, ARM, Main-calculation, and Memory routes now also pass through the lighter route-layer execution pipeline in `core/execution_pipeline.py` / `core/execution_helper.py`, which preserves existing route response shapes while adding request-level trace/event handling.
- Required outbound lifecycle events are emitted for instrumented external interactions through `services/external_call_service.py`.
- Successful non-flow operational paths now also emit durable events where implemented, including:
  - `health.liveness.completed`
  - `health.readiness.completed`
  - `identity.created`
  - `auth.register.completed`
  - `auth.login.completed`
- `POST /auth/register` also performs synchronous signup initialization before returning:
  - creates the user row
  - seeds the first identity memory node
  - creates a baseline score row
  - creates an initialized execution placeholder
  - emits required signup lifecycle events
- Async heavy-execution jobs now emit:
  - `execution.started` immediately on submission
  - `async_job.started` when the worker begins queued execution
  - `async_job.completed` or `async_job.failed` for queued worker outcome
  - `execution.completed` or `execution.failed` as the canonical execution ledger events
- High-impact execution outcomes can now auto-create Memory Bridge records with causal metadata (`source_event_id`, `root_event_id`, `causal_depth`, `impact_score`, `memory_type`).
- Embedding generation for newly captured memory is now asynchronous. Request paths persist the memory first with `embedding_status=pending`, enqueue background embedding work, and retrieval can fall back to non-embedding search while vectors are unavailable.
- Agent execution now performs pre-run memory recall and injects categorized context (`similar_past_outcomes`, `relevant_failures`, `successful_patterns`) before deterministic execution begins.
- Required `SystemEvent` persistence failures now attempt a fallback `error.system_event_failure` record and then raise fail-closed.
- Infinity loop decisions can now be memory-weighted in addition to KPI- and feedback-weighted, using ranked memory signals built before `run_loop()`.
- Execution-envelope normalization is still incomplete across `SystemEvent`, agent runs, flow runs, async jobs, and some remaining route groups. The major execution-facing routes now use either the service-level wrapper, the route-layer execution pipeline, or canonical execution envelopes, but not every route in the repo goes through the same centralized implementation.
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
- MongoDB is now a startup requirement. Missing or unreachable `MONGO_URL` fails fast during lifespan initialization instead of surfacing later during execution.
- Request metrics persistence is best-effort; failures are logged and swallowed.
- The app is still a monolith: API, scheduler leadership, orchestration, and some execution logic share the same process.
- Memory auto-link enrichment is now cross-dialect aware: PostgreSQL uses native tag containment, while SQLite/non-PostgreSQL verification falls back to Python-side tag filtering.
- Not every domain has a first-class execution-record model yet, even though trace propagation and `SystemEvent` coverage are much stronger.
