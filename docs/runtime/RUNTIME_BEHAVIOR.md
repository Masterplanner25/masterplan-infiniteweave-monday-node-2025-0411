# Runtime Behavior

This document describes the current runtime behavior of the FastAPI backend as implemented in `AINDY/main.py`.

## 1. Application Startup Flow
- Entry point is `AINDY/main.py`.
- The FastAPI app is created with a single `lifespan` context manager. Deprecated `@app.on_event("startup")` handlers are no longer used.
- Startup sequence:
  1. Reset runtime state and publish initial startup status.
  2. Enforce `SECRET_KEY`, Redis, and event-bus deployment guards where required.
  3. Initialize cache backend via `AINDY_CACHE_BACKEND`.
  4. Verify Mongo connectivity when Mongo-backed features require it.
  5. Validate queue backend and worker expectations when distributed execution is configured.
  6. Enforce schema drift guard when `AINDY_ENFORCE_SCHEMA=true`.
  7. Acquire background-task leadership through the startup event path and start APScheduler only on the leader.
  8. Register syscall handlers, canonical flow nodes, and flows.
  9. Restore dynamic platform registrations from the DB.
  10. Start the event-bus subscriber.
  11. Rehydrate waiting execution state.
  12. Publish final startup-complete state.
- Router registration occurs through the route modules under `AINDY/routes/` and the runtime registry wiring.
- `main.py` now serves only the root route directly; domain endpoints are router-backed.

## 2. Background Task Lifecycle
- Background execution is no longer driven by daemon threads in `main.py`.
- Background leadership is determined through the startup event path plus the DB lease used by the scheduler/background task services.
- Leader election is backed by the `background_task_leases` database table.
- Only the lease leader starts APScheduler jobs; a missing APScheduler dependency means background jobs are disabled but the API remains responsive for tests or constrained environments.
- Lease timestamps are normalized to timezone-aware UTC in Python before comparison or persistence.
- Scheduler lifecycle:
  - startup: `emit_event("system.startup")` -> determine leader/follower role -> `scheduler_service.start()` on leader only
  - shutdown: `emit_event("system.shutdown")` -> `scheduler_service.stop()`
- This prevents follower instances from starting duplicate background schedulers.

## 3. Database Session Lifecycle
- Per-request SQLAlchemy sessions are provided by `get_db()` in `AINDY/db/database.py`.
- Startup and shutdown logic in `main.py` uses explicit `SessionLocal()` blocks with `try/finally`.
- Request metrics middleware creates its own short-lived session to persist `RequestMetric` rows.
- MongoDB uses a process-level client singleton in `AINDY/db/mongo_setup.py`; shutdown now attempts to close the client in the lifespan shutdown path.

## 4. Execution Registration
- Canonical flow execution is registered during startup from `runtime.flow_definitions`.
- The flow engine is a first-class runtime component and is not a side utility.
- Current execution-facing domains route through flows and/or orchestrators rather than ad hoc route logic:
  - task
  - memory execution
  - genesis message handling
  - watcher ingest
  - agent runtime

## 4.1 Unified Retry Policy
- All retry decisions across flow, agent, async-job, and Nodus scheduled execution are now resolved through `core/retry_policy.py`.
- `RetryPolicy` is a frozen dataclass: `max_attempts`, `backoff_ms`, `exponential_backoff`, `high_risk_immediate_fail`.
- `resolve_retry_policy(execution_type, ...)` is the single resolver. Hardcoded values in `flow_engine`, `nodus_adapter`, and `async_job_service` have been replaced with calls to the resolver.
- Per-run node overrides: `run_nodus_script_via_flow(node_max_retries=N)` injects `flow["node_configs"]["nodus.execute"]["max_retries"] = N`. The flow engine reads this at the retry gate via `resolve_retry_policy(node_max_retries=...)`. The shared `NODUS_SCRIPT_FLOW` constant is never mutated.
- Every `ExecutionUnit` carries `extra["retry_policy"]` (JSONB) populated by `require_execution_unit()` at gate time, making the policy observable without importing `RetryPolicy` at the read site.
- Current defaults (all `backoff_ms=0` - no sleep between retries anywhere in the execution layer):
  - Flow nodes: `max_attempts=3`
  - Agent low/medium risk: `max_attempts=3`
  - Agent high risk: `max_attempts=1`, `high_risk_immediate_fail=True`
  - Async jobs: `max_attempts=1` (no retry by default)
  - Nodus scheduled: `max_attempts=3`, overridable per `NodusScheduledJob.max_retries`
- See `docs/runtime/RETRY_POLICY.md` for full data-flow diagrams and per-path behavior.

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
- Research, LeadGen, Freelance, Agent, Automation, Task, Goals, and Genesis route executions now share the centralized execution wrapper (`core/execution_service.py`) or pass through canonical execution envelopes that standardize `trace_id`, lifecycle events, and response shape.
- Auth, Analytics, ARM, Main-calculation, and Memory routes now also pass through the lighter route-layer execution pipeline in `core/execution_pipeline.py` / `core/execution_helper.py`, which preserves existing route response shapes while adding request-level trace/event handling.
- Required outbound lifecycle events are emitted for instrumented external interactions through `platform_layer/external_call_service.py`.
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
- Async execution has two transport modes, selected by `EXECUTION_MODE`:
  - `thread` (default) - `ExecutionDispatcher` submits to an in-process `ThreadPoolExecutor`; no external dependencies.
  - `distributed` - `ExecutionDispatcher` enqueues a `QueueJobPayload` to `core/distributed_queue.py`; one or more `worker/worker_loop.py` processes consume the queue. Trace context (`trace_id`, `eu_id`) is serialised into the payload and restored in the worker before execution, preserving the full syscall trace chain across the process boundary. Retry backoff, visibility timeout recovery, and a Dead Letter Queue are included; see `docs/deployment/DEPLOYMENT_MODEL.md`.
- High-impact execution outcomes can now auto-create Memory Bridge records with causal metadata (`source_event_id`, `root_event_id`, `causal_depth`, `impact_score`, `memory_type`).
- Embedding generation for newly captured memory is now asynchronous. Request paths persist the memory first with `embedding_status=pending`, enqueue background embedding work, and retrieval can fall back to non-embedding search while vectors are unavailable.
- Agent execution now performs pre-run memory recall and injects categorized context (`similar_past_outcomes`, `relevant_failures`, `successful_patterns`) before deterministic execution begins.
- Required `SystemEvent` persistence failures now attempt a fallback `error.system_event_failure` record and then raise fail-closed.
- Infinity loop decisions can now be memory-weighted in addition to KPI- and feedback-weighted, using ranked memory signals built before `run_loop()`.
- A canonical execution-envelope unification layer now exists at `core/execution_gate.py`. `require_execution_unit()` gates execution before dispatch at route entry points (non-fatal, idempotent). `to_envelope()` produces the shared `{eu_id, trace_id, status, output, error, duration_ms, attempt_count}` shape. Agent, automation, flow, and platform routes now embed `execution_envelope` in responses. Execution-envelope normalization remains incomplete for Task, Genesis, Watcher, and ARM domain routes, which still return domain-only payloads.
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
- MongoDB is a startup requirement in the normal runtime path. Missing or unreachable `MONGO_URL` fails fast during lifespan initialization unless the explicit skip flag (`AINDY_SKIP_MONGO_PING` / `SKIP_MONGO_PING`) is enabled for tests or constrained local runs.
- Request metrics persistence is best-effort; failures are logged and swallowed.
- The app is still a monolith: API, scheduler leadership, orchestration, and some execution logic share the same process.
- Memory auto-link enrichment is now cross-dialect aware: PostgreSQL uses native tag containment, while SQLite/non-PostgreSQL verification falls back to Python-side tag filtering.
- Not every domain has a first-class execution-record model yet, even though trace propagation and `SystemEvent` coverage are much stronger.
