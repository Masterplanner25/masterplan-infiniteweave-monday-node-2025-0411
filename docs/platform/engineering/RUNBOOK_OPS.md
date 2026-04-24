# A.I.N.D.Y. Production Operations Runbook

This document covers startup sequencing, instance drain, and Redis failover. For secret key rotation see `RUNBOOK_SECRET_ROTATION.md`. For schema migrations see `MIGRATION_POLICY.md`. For deployment shapes see `DEPLOYMENT_MODEL.md`.

This runbook is grounded in the current codebase as of 2026-04-23. Where earlier audit notes and the runtime diverge, this document follows the runtime.

---

## 1. Startup Sequence

### 1.1 Infrastructure prerequisites

| Dependency | Single-instance | Multi-instance |
|---|---|---|
| PostgreSQL | Required | Required |
| Redis | Optional in local/single-instance mode; required if `AINDY_REQUIRE_REDIS=true` or `EXECUTION_MODE=distributed` | Required |
| MongoDB | Required only if `MONGO_REQUIRED=true` | Required only if `MONGO_REQUIRED=true` |
| Worker process | Not needed when `EXECUTION_MODE=thread` | Required when `EXECUTION_MODE=distributed` |

### 1.2 Pre-start checklist

1. Check Alembic is at head.
   Command:
   ```bash
   alembic current
   alembic heads
   alembic check
   ```
   Passing result: `alembic current` matches `alembic heads`, and `alembic check` exits `0`.
   If it fails: run `alembic upgrade head`. The API enforces the same check at startup when `AINDY_ENFORCE_SCHEMA=true` (the runtime default in `AINDY/main.py`).

2. Check PostgreSQL reachability.
   Command:
   ```bash
   pg_isready -d "$DATABASE_URL"
   ```
   Passing result: server accepts connections.
   If it fails: fix `DATABASE_URL`, PostgreSQL availability, or network access before starting the API.

3. Check Redis reachability for distributed mode.
   Command:
   ```bash
   redis-cli -u "$REDIS_URL" ping
   ```
   Passing result: `PONG`.
   If it fails: do not start a distributed deployment. Fix `REDIS_URL` first. If you also use the event bus, verify `AINDY_REDIS_URL` if it is set separately.

4. Check MongoDB reachability if Mongo is required.
   Command:
   ```bash
   mongosh "$MONGO_URL" --eval "db.adminCommand({ ping: 1 })"
   ```
   Passing result: `{ ok: 1 }`.
   If it fails: fix `MONGO_URL`, MongoDB availability, or set `MONGO_REQUIRED=false` only if the deployment does not require Mongo-backed features.

5. Check `SECRET_KEY`.
   Command:
   ```bash
   python - <<'PY'
   import os
   key = os.getenv("SECRET_KEY", "")
   print(len(key), key == "dev-secret-change-in-production")
   PY
   ```
   Passing result: length is at least `32`, and the second value is `False`.
   If it fails: generate a new key and update the environment before starting any non-development deployment.

6. Check `EXECUTION_MODE` matches the deployment shape.
   Command:
   ```bash
   python - <<'PY'
   import os
   print(os.getenv("EXECUTION_MODE", "thread"))
   PY
   ```
   Passing result: `thread` for single-instance, `distributed` for multi-instance with workers.
   If it fails: correct the environment. `EXECUTION_MODE=distributed` without Redis is rejected by the queue backend.

### 1.3 Start order

1. Start PostgreSQL.
   Command:
   ```bash
   pg_isready -d "$DATABASE_URL"
   ```
   What it does internally: nothing in A.I.N.D.Y. starts until PostgreSQL is reachable because schema checks, router validation, dynamic registry restore, and recovery scans all depend on the SQL database.
   Verify before continuing: `pg_isready` reports ready.

2. Start MongoDB if `MONGO_REQUIRED=true`.
   Command:
   ```bash
   mongosh "$MONGO_URL" --eval "db.adminCommand({ ping: 1 })"
   ```
   What it does internally: `ensure_mongo_ready(required=settings.MONGO_REQUIRED)` runs during API startup and fails fast if Mongo is required but unreachable.
   Verify before continuing: ping succeeds.

3. Start Redis for distributed mode.
   Command:
   ```bash
   redis-cli -u "$REDIS_URL" ping
   ```
   What it does internally: startup guards, worker heartbeat checks, queue validation, health checks, and most multi-instance coordination expect Redis to be reachable. The event bus uses `AINDY_REDIS_URL` if that variable is set; otherwise it falls back to its own default.
   Verify before continuing: `PONG`.

4. Run migrations.
   Command:
   ```bash
   alembic upgrade head
   alembic check
   ```
   What it does internally: the API performs its own Alembic head check during startup and raises `RuntimeError("Schema drift detected. Run alembic upgrade head.")` if the DB is behind.
   Verify before continuing: `alembic check` exits `0`.

5. Start the API.
   Command:
   ```bash
   uvicorn AINDY.main:app --host 0.0.0.0 --port 8000
   ```
   What it does internally, in code order:
   1. Validates `SECRET_KEY`.
   2. Enforces the Redis startup guard when Redis is required.
   3. Enforces the event-bus guard when distributed contracts require it.
   4. Initializes the cache backend.
   5. Checks Mongo connectivity.
   6. Bootstraps the dev API key in `ENV=dev`.
   7. Validates the queue backend.
   8. Warns if `EXECUTION_MODE=distributed` and no worker heartbeat is present.
   9. Enforces Alembic head when `AINDY_ENFORCE_SCHEMA=true`.
   10. Starts background hooks and APScheduler leadership if this instance acquires the lease.
   11. Starts the request metric writer.
   12. Registers syscall handlers, flows, and nodes.
   13. Verifies required flow nodes.
   14. Restores dynamic registry entries from the DB.
   15. Validates router boundaries.
   16. Runs stuck-run recovery.
   17. Starts the event-bus subscriber.
   18. Rehydrates waiting EUs and waiting FlowRuns.
   19. Marks rehydration complete and drains buffered events.
   20. Runs startup hooks and publishes `startup_complete=True`.
   Verify before continuing:
   ```bash
   curl http://localhost:8000/ready
   ```
   Passing result: HTTP `200` with `"status":"ready"`.

6. Start worker processes in distributed mode.
   Command:
   ```bash
   python -m AINDY.worker
   ```
   What it does internally: validates the queue backend, starts the worker health server, waits for the background-task lease schema, optionally starts scheduler leadership, marks worker runtime state ready, starts stale-job recovery, writes the Redis heartbeat every `30` seconds, and begins dequeuing jobs.
   Verify before continuing:
   ```bash
   curl http://localhost:8000/health/deep
   ```
   Passing result: `.checks.worker.status == "ok"`.

7. Verify scheduler leadership.
   Command:
   ```bash
   curl -H "Authorization: Bearer <token>" \
     http://localhost:8000/observability/scheduler/status
   ```
   What it does internally: reports whether the instance currently holds the DB-backed background-task lease and whether APScheduler is running.
   Verify before continuing: exactly one instance reports `"is_leader": true`.

8. Verify flow registration.
   Command:
   ```bash
   curl http://localhost:8000/health/deep
   ```
   What it does internally: checks the in-memory flow and node registries populated during startup.
   Verify before continuing: `.checks.flow_registry.node_count > 0` and `.checks.flow_registry.flow_count > 0`.

### 1.4 Startup failure modes and responses

| Error message | Cause | Fix |
|---|---|---|
| `Schema drift detected. Run alembic upgrade head.` | Migrations not applied | Run `alembic upgrade head`, then restart |
| `SECRET_KEY is using the insecure default placeholder.` | `SECRET_KEY` left at the default placeholder | Generate and set a real key |
| `SECRET_KEY is too short (...)` | `SECRET_KEY` shorter than 32 chars outside test/dev | Set a key with at least 32 characters |
| `Redis is configured but not reachable at startup.` | `REDIS_URL` unreachable | Verify Redis is running and `REDIS_URL` is correct |
| `REDIS_URL is required in non-development deployments.` | Redis-required deployment started without `REDIS_URL` | Set `REDIS_URL` or explicitly use a supported single-instance shape |
| `Required flow nodes missing after bootstrap: [...]` | Flow/node registration failed during startup | Check startup logs, flow registration imports, and domain bootstrap |
| `Event bus subscriber failed to start: ...` | Event bus required but could not subscribe | Fix Redis or the event-bus configuration and restart |
| `APScheduler failed to start. Check apscheduler installation.` | Scheduler startup failed after this instance acquired leadership | Fix APScheduler installation/runtime error and restart |
| `Mongo is required but MONGO_URL is not configured` | `MONGO_REQUIRED=true` with no Mongo URL | Set `MONGO_URL` or disable Mongo requirement |
| `Mongo connection failed. Verify MONGO_URL and that the MongoDB server is reachable.` | Required Mongo was unreachable | Fix Mongo connectivity and restart |

### 1.5 Verifying a healthy start

```bash
# Readiness: do not route traffic until this is HTTP 200 and status=ready
curl http://localhost:8000/ready

# Scheduler role: run on each instance; exactly one should show is_leader=true
curl -H "Authorization: Bearer <token>" \
  http://localhost:8000/observability/scheduler/status

# Deep health: flow registry counts should be non-zero; worker should be ok in distributed mode
curl http://localhost:8000/health/deep

# Liveness: degraded_domains should normally be empty after a clean start
curl http://localhost:8000/health
```

Notes:
- `/ready` checks `startup_complete`, PostgreSQL, schema, Redis when required, queue backend when required, scheduler state, worker heartbeat when required, and event-bus readiness when required.
- `/health/deep` is where flow registry counts live. `/ready` does not include `flow_registry`.

---

## 2. Instance Drain Procedure

### 2.1 When to drain

- Rolling deployment to a new version
- Planned maintenance on one API or worker instance
- Scheduler leader hand-off

### 2.2 Draining an API instance

1. Remove the instance from the load balancer.
   Use `/ready` as the load-balancer readiness target. Stop routing new traffic before sending a signal.

2. Send `SIGTERM` to the `uvicorn` process.
   `uvicorn` finishes in-flight HTTP requests, then FastAPI runs the lifespan shutdown block. The shutdown sequence in `AINDY/main.py` is:
   1. `publish_api_runtime_state(startup_complete=False, event_bus_ready=False)`
   2. `emit_event("system.shutdown", ...)`
   3. `scheduler_service.stop()`
   4. `get_metric_writer().stop(timeout=10.0)`
   5. `shutdown_async_jobs(wait=True)`
   6. `close_mongo_client()`

3. Wait for the process to exit.
   Expected timing: bounded by `uvicorn` graceful shutdown plus any in-flight request, scheduler shutdown, metric-writer flush, and async-job drain.

4. Check for stranded runs.
   Running FlowRuns on the drained instance are not resumed automatically. The recovery jobs mark stale `status="running"` FlowRuns as `failed` after the threshold, rather than resuming them.
   Command:
   ```bash
   curl -H "Authorization: Bearer <token>" \
     "http://localhost:8000/flows/runs?status=running"
   ```
   Relevant thresholds:
   - `STUCK_RUN_THRESHOLD_MINUTES=15` in `AINDY/config.py` for periodic FlowRun recovery
   - Startup stuck-run scan also runs once on API start

5. If the drained instance was the scheduler leader, confirm lease hand-off.
   Lease timings from `apps/tasks/services/task_service.py`:
   - heartbeat interval: `60` seconds
   - lease TTL: `120` seconds
   Verify on another instance:
   ```bash
   curl -H "Authorization: Bearer <token>" \
     http://<other-instance>/observability/scheduler/status
   ```
   Passing result: `"is_leader": true`.

6. If a stranded execution is an AgentRun, use the manual recovery endpoint only after verifying it is truly stuck.
   Command:
   ```bash
   curl -X POST -H "Authorization: Bearer <token>" \
     "http://localhost:8000/apps/agent/runs/<run_id>/recover?force=true"
   ```
   Notes:
   - This endpoint exists for `AgentRun`, not for generic `FlowRun`.
   - It marks the stuck run failed; it does not resume it.
   - Without `force=true`, the handler enforces `AINDY_STUCK_RUN_THRESHOLD_MINUTES` with a default of `10`.

### 2.3 Draining a worker instance

1. Send `SIGTERM` to the worker process.
   The worker installs `_handle_signal()` for `SIGTERM` and `SIGINT`. That handler sets the module-level `_STOP` event.

2. Wait for the current job to finish.
   The worker checks `_STOP` between acquisitions. A job already executing when the signal arrives is allowed to complete. Shutdown time can therefore be as long as the current job runtime.

3. Wait for the process to exit.
   The worker joins its worker threads with `timeout=10`, stale-recovery thread with `timeout=5`, and heartbeat thread with `timeout=5`.

4. Verify stale-job recovery on the remaining or next worker.
   Jobs already dequeued but not acked are recovered by `requeue_stale_jobs(timeout_seconds)` on worker startup and every `WORKER_STALE_CHECK_INTERVAL_SECS` seconds.
   Current defaults in `AINDY/worker/worker_loop.py`:
   - `WORKER_VISIBILITY_TIMEOUT_SECS=300`
   - `WORKER_STALE_CHECK_INTERVAL_SECS=60`

5. If no workers remain in distributed mode, start another worker immediately.
   The API can still accept requests, but distributed async work will queue and not execute. Verify with:
   ```bash
   curl http://localhost:8000/health/deep
   ```
   Failure signal: `.checks.worker.status` becomes `no_heartbeat` or `error`.

---

## 3. Redis Failover

### 3.1 What fails automatically vs. what stays up

| Subsystem | Redis-down behavior | Auto-recovers? |
|---|---|---|
| Cache (`FastAPICache`) | In development/testing, Redis cache init falls back to in-memory. In production, Redis cache failure disables caching to avoid per-process divergence. | Yes on restart; not by live backend swapping |
| EventBus publisher | `publish()` returns `False`; after `3` consecutive failures the publisher disables itself and logs a warning | No automatic re-enable after disable; restart API instances to restore publish behavior |
| EventBus subscriber | Subscriber loop reconnects with exponential backoff (`1s` to `30s`) while the process stays enabled | Partially; subscriber reconnects, but a disabled publisher still needs restart |
| ResourceManager concurrency | Falls back to process-local counters when Redis is unreachable | Yes; connectivity is rechecked every `30` seconds |
| Redis queue backend | Retries Redis connection/timeout/busy errors `3` times with exponential backoff, then raises | Operations resume automatically when Redis is reachable again; degraded memory fallback can also reconnect via the scheduled health check |
| Redis wait registry | `register()` returns `False` if Redis is unavailable | Partial; waiting state in the SQL DB still exists, but cross-instance resume assistance is reduced |
| Worker heartbeat | Heartbeat writes fail; API deep health shows missing/error heartbeat | Yes once a worker can write to Redis again |
| Scheduler leadership visibility | Lease heartbeat and worker heartbeat checks that depend on shared state can appear stale | Lease leadership uses PostgreSQL, not Redis, so scheduler election itself stays up |

### 3.2 Automatic recovery behavior

`ResourceManager` rechecks Redis every `30.0` seconds. When Redis comes back, it logs:

```text
[resource_manager] Redis reconnected; using shared quota counters
```

`EventBus` behavior is different:

- the subscriber thread reconnects on its own while the bus remains enabled
- the publisher disables itself after `3` consecutive publish failures
- once disabled, the publisher does not automatically re-enable in the current process

Operationally, the safe recovery path after a Redis outage is a rolling restart of API instances after Redis is healthy again.

### 3.3 Operator procedure during a Redis outage

1. Identify the blast radius.
   Command:
   ```bash
   curl http://localhost:8000/health/deep
   ```
   Check:
   - `.checks.redis.status`
   - `.checks.worker.status` in distributed mode

2. Determine whether the event bus and queue are using the Redis endpoint you expect.
   The code uses both:
   - `REDIS_URL` for health checks, queue backend, worker heartbeat, and most runtime services
   - `AINDY_REDIS_URL` for the event bus if that variable is set

3. Restore Redis service.
   Verify:
   ```bash
   redis-cli -u "$REDIS_URL" ping
   ```
   If `AINDY_REDIS_URL` is set separately, verify that endpoint too.

4. Restart API instances in rolling order.
   For each instance:
   1. restart one instance
   2. wait for `/ready` to return HTTP `200`
   3. verify `/health/deep` shows `.checks.redis.status == "ok"`
   4. continue to the next instance

5. Check for waiting FlowRuns created during the outage.
   Command:
   ```bash
   curl -H "Authorization: Bearer <token>" \
     "http://localhost:8000/flows/runs?status=waiting"
   ```
   During an outage, a flow may remain waiting if the expected cross-instance event never reached the instance that owns the in-memory callback.

6. Resume waiting FlowRuns manually when you know the expected event name.
   The codebase does not expose a generic `POST /flow/{run_id}/recover` endpoint. The runtime endpoint that exists is:
   ```bash
   curl -X POST -H "Authorization: Bearer <token>" \
     http://localhost:8000/flows/runs/<run_id>/resume \
     -H "Content-Type: application/json" \
     -d '{"event_type":"<expected_waiting_for_value>","payload":{}}'
   ```
   The endpoint only succeeds when:
   - the run exists
   - the run is still in `status="waiting"`
   - `event_type` exactly matches `run.waiting_for`

7. Recover stuck AgentRuns separately if needed.
   If a Redis outage left an agent execution stuck in `executing`, use:
   ```bash
   curl -X POST -H "Authorization: Bearer <token>" \
     "http://localhost:8000/apps/agent/runs/<run_id>/recover?force=true"
   ```
   This marks the AgentRun failed so operators can replay or inspect it later.

### 3.4 Redis outage incident summary template

- Outage start time:
- Redis restored time:
- Instances restarted:
- Waiting FlowRuns resumed:
- AgentRuns manually recovered:
- Runs still unrecovered, with reason:

---

## 4. Reference

### 4.1 Useful endpoints

| Endpoint | Method | Auth required | What it shows |
|---|---|---|---|
| `/ready` | `GET` | No | Readiness gate: `startup_complete`, required dependency checks, runtime contract failures |
| `/health` | `GET` | No | Liveness and `degraded_domains` |
| `/health/deep` | `GET` | No | Deep checks for database, Redis, Mongo, scheduler, flow registry, worker, nodus, AI providers |
| `/observability/scheduler/status` | `GET` | Yes | `scheduler_running`, `is_leader`, and current lease record |
| `/flows/runs` | `GET` | Yes | Authenticated FlowRun listing with optional `status` filter |
| `/flows/runs/{run_id}/resume` | `POST` | Yes | Resume a waiting FlowRun when you know the required event name |
| `/apps/agent/runs/{run_id}/recover` | `POST` | Yes | Mark a stuck AgentRun failed for operator recovery |

Notes:
- This workspace does not define a `/client/error` route.
- This workspace does not define a generic `POST /flow/{run_id}/recover` route.

### 4.2 Key configuration variables

| Variable | Source | What it controls | Default |
|---|---|---|---|
| `STUCK_RUN_THRESHOLD_MINUTES` | `AINDY/config.py` | Periodic FlowRun stuck-run recovery threshold | `15` |
| `WORKER_VISIBILITY_TIMEOUT_SECS` | `AINDY/worker/worker_loop.py` | How long a dequeued job can stay in flight before stale-job requeue treats it as abandoned | `300` |
| `EXECUTION_MODE` | `AINDY/config.py` | `thread` vs `distributed` execution path | `thread` |
| `AINDY_REQUIRE_REDIS` | `AINDY/config.py` | Forces Redis-required deployment behavior | `False` |
| `AINDY_ENFORCE_SCHEMA` | `AINDY/main.py` environment read | Enables Alembic head enforcement at startup | `true` |
| `AINDY_ENABLE_BACKGROUND_TASKS` | `AINDY/platform_layer/deployment_contract.py` environment read | Enables background hooks and scheduler leadership participation | `true` |
| `FLOW_WAIT_TIMEOUT_MINUTES` | `AINDY/config.py` | Default wait deadline for FlowRuns unless a flow overrides it | `30` |
| `AINDY_REDIS_URL` | `AINDY/kernel/event_bus.py` | Event-bus Redis endpoint | `redis://localhost:6379/0` |

Additional note:
- Manual AgentRun recovery uses `AINDY_STUCK_RUN_THRESHOLD_MINUTES` in `AINDY/agents/stuck_run_service.py`, with a separate default of `10`.

### 4.3 Related documents

- `docs/deployment/DEPLOYMENT_MODEL.md` — deployment shapes and topology
- `docs/deployment/RUNNING_IN_PRODUCTION.md` — environment variable reference
- `docs/deployment/MIGRATION_POLICY.md` — schema migration discipline
- `docs/platform/engineering/RUNBOOK_SECRET_ROTATION.md` — secret key rotation companion runbook if present in your checkout
- `docs/architecture/MULTI_INSTANCE_RESUME.md` — cross-instance resume internals
- `docs/runtime/RUNTIME_BEHAVIOR.md` — runtime behavior and invariants
