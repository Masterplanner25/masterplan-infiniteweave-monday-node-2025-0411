---
title: "Runbook: Async Job Queue Failure"
last_verified: "2026-04-29"
api_version: "1.0"
status: current
owner: "platform-team"
severity: P2
---

# Runbook: Async Job Queue Failure

## Severity
**P2** — Queue failure degrades async job execution for distributed workloads (agent runs, automation jobs, scheduled tasks). Synchronous routes are unaffected. Upgrade to **P1** if the dead-letter queue is growing and no operator action has been taken for more than 15 minutes.

## Symptoms
What an operator sees when this incident is occurring:
- Startup fallback warning from [distributed_queue.py](/abs/path/C:/dev/masterplan-infiniteweave-monday-node-2025-0411/AINDY/core/distributed_queue.py:426):
  - `[DistributedQueue] Redis unavailable (%s) — falling back to in-memory queue. In multi-instance mode, jobs will NOT be shared across instances. Set AINDY_REQUIRE_REDIS=true to prevent degraded-mode startup.`
- Startup warning when Redis is not configured at all:
  - `[Queue] REDIS_URL not set — using in-memory queue. Multi-process distributed execution requires Redis.`
- Runtime backend failure warnings:
  - `RedisQueueBackend: operation=%s failed error=%s`
  - `RedisQueueBackend: circuit breaker OPEN for %.1fs after %d failures`
  - `RedisQueueBackend: retry attempt=%s exception=%s`
- Recovery log lines after Redis returns:
  - `RedisQueueBackend: circuit breaker CLOSED (connection restored)`
  - `[DistributedQueue] Redis connection restored - queue backend switched to Redis.`
  - `Distributed queue backend recovered to Redis`
- Worker-side symptoms when dequeue/queue operations fail:
  - `[Worker] loop error: %s`
  - `[Worker] stale recovery error: %s`
- Worker advisory at API startup when distributed mode is enabled but no worker heartbeat exists:
  - `[startup] EXECUTION_MODE=distributed: no worker heartbeat found in Redis (key=%s). If no worker process is running, enqueued jobs will not be processed. Start a worker with: WORKER_CONCURRENCY=1 python -m AINDY.worker.worker_loop`
- Health endpoint signals:
  - `GET /health` → `.dependencies.queue.status == "degraded"` indicates queue degradation.
  - `GET /health` → `.dependencies.queue.backend == "memory"` indicates fallback to the in-memory backend.
  - `GET /health` → `.dependencies.queue.degraded == true` and `.dependencies.queue.redis_available == false` confirm Redis-backed queue loss.
  - `GET /health` → `.platform.execution_engine == "degraded"` means the queue is impacting the execution path.

## Immediate Triage
First 5 minutes: confirm whether the queue is on Redis or in-memory, whether the worker is still consuming, and whether dead-letter backlog exists.

1. Is the queue backend currently Redis or memory?

```bash
curl -s "$API_BASE_URL/health" | jq '.dependencies.queue'
```

Expected output if this is the problem:
- `"status": "degraded"`
- `"backend": "memory"`
- `"degraded": true`

Expected output if this is not the problem:
- `"status": "ok"`
- `"backend": "redis"`
- `"degraded": false`

2. Are new jobs being accepted, and what is current queue depth?

The generic `/health` payload does not expose queue depth. Use the queue health endpoint instead:

```bash
curl -s -H "Authorization: Bearer $ADMIN_TOKEN" \
  "$API_BASE_URL/platform/queue/health" | jq '.data | {backend, degraded, queue_depth, in_flight_count, dlq_depth, delayed_jobs, reason}'
```

Expected output if this is the problem:
- `backend` is `memory`, or
- `degraded` is `true`, or
- `queue_depth` rises while `in_flight_count` stays flat

Expected output if this is not the problem:
- `backend` is `redis`
- `degraded` is `false`
- `queue_depth` stays low or drains

3. How many jobs are in the DLQ?

Current implementation requires authenticated access. Examples below use a JWT bearer token.

```bash
curl -s -H "Authorization: Bearer $ADMIN_TOKEN" \
  "$API_BASE_URL/platform/queue/dead-letters?limit=20" | jq '.data | {backend, count, items}'
```

Expected output if this is the problem:
- `count > 0`, with entries containing `job_id`, `payload`, `payload_raw`, `error`, and `failed_at`

Expected output if this is not the problem:
- `count == 0`

### This runbook is NOT for
- Redis event bus failures (WAIT/RESUME propagation); use [Runbook: Redis Failure](RUNBOOK_REDIS_FAILURE.md).
- Stuck flow runs or agent runs with no queue/backend degradation; use [Runbook: Stuck Runs](RUNBOOK_STUCK_RUNS.md).
- A single job that failed and moved to the DLQ under otherwise normal queue health. That is expected retry exhaustion behavior, not a queue-backend incident.

## Root Cause Classification
Why this happens. What code path leads to this state.

### A. Redis unreachable at startup
`get_queue()` in [distributed_queue.py](/abs/path/C:/dev/masterplan-infiniteweave-monday-node-2025-0411/AINDY/core/distributed_queue.py:1082) tries to construct `RedisQueueBackend`, calls `assert_ready()`, and falls back through `_fallback_to_memory_backend()` when Redis is unreachable and `AINDY_REQUIRE_REDIS=false`. The API process then holds an `InMemoryQueueBackend`.

### B. Redis dies after startup
`RedisQueueBackend._run_redis_operation()` records runtime Redis failures, opens a circuit breaker after 5 failures for 30 seconds, and raises. The reconnect path is not embedded in the backend itself. APScheduler runs `_check_queue_backend_health()` every 60 seconds and calls `attempt_queue_backend_reconnect()` to swap the singleton back to Redis when possible.

### C. Worker crashed between dequeue and ack
The worker dequeues with `BRPOP`, the queue records the job in `aindy:jobs:inflight`, and `worker_loop.process_one_job()` later calls `ack()` or `fail()`. If the worker dies between dequeue and ack/fail, the job is absent from `aindy:jobs` but still present in `aindy:jobs:inflight`. Recovery is via `requeue_stale_jobs(timeout_seconds)`.

### D. Worker never started or stopped while jobs were queued
Jobs accumulate in Redis (`aindy:jobs` and `aindy:jobs:delayed`) or, after terminal failure, in `aindy:jobs:dead`. In distributed mode, API-side in-memory fallback is especially dangerous because jobs accepted by the API are then stranded in that process heap and are invisible to the separate worker process.

## Recovery Procedure

### A. In-memory queue at startup (non-durable mode)

1. Verify Redis is reachable.

```bash
docker compose ps redis
docker compose logs --tail=50 redis
redis-cli -u "${AINDY_REDIS_URL:-$REDIS_URL}" ping
```

Success looks like:
- Redis is running
- `redis-cli` returns `PONG`

If this fails:
- Restore Redis before touching the API or worker

2. Restart the API and worker so both processes rebuild their queue singleton against Redis.

```bash
docker compose restart api worker
```

Success looks like:
- API logs include `[Queue] Redis backend - url=%s queue=%s`
- `/health` shows `.dependencies.queue.backend == "redis"`

If this fails:
- If the API still logs the fallback warning, Redis is still unavailable or credentials are wrong.

3. Identify jobs created during the degraded window.

Jobs submitted to `InMemoryQueueBackend` during the degraded window are not durable and, in distributed mode, are not shared to the separate worker process. If the API process was restarted after fallback, those specific jobs are gone and must be re-triggered from the originating UI or API call.

Use the operator-facing `automation_logs` table to identify likely lost work:

```bash
psql "$DATABASE_URL" -c "
SELECT id, source, task_name, status, trace_id, created_at
FROM automation_logs
WHERE status IN ('pending', 'running', 'retrying')
ORDER BY created_at DESC
LIMIT 100;
"
```

Success looks like:
- You can correlate stranded records to the time window when the API was on `backend=memory`

If this fails:
- Query `job_logs` as the lower-level execution record:

```bash
psql "$DATABASE_URL" -c "
SELECT id, source, job_name, status, trace_id, created_at
FROM job_logs
WHERE status IN ('pending', 'running')
ORDER BY created_at DESC
LIMIT 100;
"
```

### B. Redis died after startup (circuit breaker scenario)

1. Confirm queue degradation and current backend.

There is no dedicated public `circuit_open` field. Infer circuit-breaker state from the log lines plus queue health:

```bash
curl -s "$API_BASE_URL/health" | jq '.dependencies.queue'
curl -s -H "Authorization: Bearer $ADMIN_TOKEN" \
  "$API_BASE_URL/platform/queue/health" | jq '.data'
```

Success looks like:
- `.dependencies.queue.status == "degraded"`
- `.dependencies.queue.backend == "memory"` or `.data.degraded == true`
- recent logs include `RedisQueueBackend: circuit breaker OPEN for %.1fs after %d failures`

If this fails:
- If health remains `backend=redis`, this is not the queue fallback incident. Investigate normal job failures instead.

2. Restore Redis.

```bash
docker compose restart redis
redis-cli -u "${AINDY_REDIS_URL:-$REDIS_URL}" ping
```

Success looks like:
- `PONG`

3. Wait for reconnect automation.

The reconnect path runs from APScheduler every 60 seconds via the `queue_backend_reconnect` job in [scheduler_service.py](/abs/path/C:/dev/masterplan-infiniteweave-monday-node-2025-0411/AINDY/platform_layer/scheduler_service.py:219). The Redis backend circuit breaker itself opens for 30 seconds after 5 failures.

```bash
curl -s "$API_BASE_URL/health" | jq '.dependencies.queue'
```

Success looks like:
- `.backend == "redis"`
- `.degraded == false`
- logs include `[DistributedQueue] Redis connection restored - queue backend switched to Redis.`

If this fails:
- Restart the API if APScheduler is not running or the backend stays on memory:

```bash
docker compose restart api
```

4. Confirm the degraded window and assess data loss risk.

```bash
curl -s "$API_BASE_URL/health" | jq '.dependencies.queue'
curl -s -H "Authorization: Bearer $ADMIN_TOKEN" \
  "$API_BASE_URL/platform/queue/health" | jq '.data | {backend, degraded, reason}'
```

Interpretation:
- `reason` is the last fallback reason string from `backend.fallback_reason`
- Any job accepted while the API queue backend was memory was non-durable and not cross-process visible
- If the API restarted during that window, those jobs were lost and must be re-triggered

### C. Jobs stranded in Redis in-flight tracking

1. Inspect the Redis in-flight hash directly.

```bash
redis-cli -u "${AINDY_REDIS_URL:-$REDIS_URL}" HGETALL aindy:jobs:inflight
```

Success looks like:
- Each entry is keyed by `job_id`
- Each value is JSON with `payload` and `dequeued_at`

If this fails:
- Redis is still unavailable; resolve that first.

2. Understand the automatic recovery threshold.

`requeue_stale_jobs(timeout_seconds)` uses the worker visibility timeout, which defaults to `WORKER_VISIBILITY_TIMEOUT_SECS=300`. The worker runs stale recovery immediately on startup and then every `WORKER_STALE_CHECK_INTERVAL_SECS=60`.

There is no dedicated HTTP endpoint to trigger stale-job recovery manually. The supported operator action is to restart the worker, which forces an immediate stale scan:

```bash
docker compose restart worker
```

Success looks like:
- Worker logs show `[Worker] stale recovery: re-enqueued %d jobs` or individual Redis logs show `[Queue:redis] requeued stale job_id=%s age=%.0fs`

If this fails:
- Check for stale recovery errors in worker logs:
  - `[Worker] stale recovery error: %s`
  - `[Queue:redis] stale check failed job_id=%s: %s`

3. Confirm whether recovered jobs later failed into the DLQ.

```bash
curl -s -H "Authorization: Bearer $ADMIN_TOKEN" \
  "$API_BASE_URL/platform/queue/dead-letters?limit=20" | jq '.data'
```

Success looks like:
- `count` stays low if the requeued jobs recovered cleanly

If this fails:
- If `count` rises, move to the DLQ replay procedure after fixing the underlying job failure cause.

### D. DLQ drain and replay

The DLQ contains jobs that exhausted retries or were marked terminally failed through `backend.fail()`. In Redis this is the `aindy:jobs:dead` list.

1. Inspect the DLQ.

```bash
curl -s -H "Authorization: Bearer $ADMIN_TOKEN" \
  "$API_BASE_URL/platform/queue/dead-letters?limit=20" | jq '.data'
```

Expected response shape:
- `.data.backend` — `redis` or `memory`
- `.data.count` — number of returned entries
- `.data.items[]` — objects containing `job_id`, `payload`, `payload_raw`, `error`, `failed_at`

2. Replay one dead-lettered job after fixing the root cause.

Current implementation does not support bulk requeue through `POST /platform/queue/dead-letters/drain`. Replay is per job:

```bash
JOB_ID="<dead_letter_job_id>"
curl -s -X POST -H "Authorization: Bearer $ADMIN_TOKEN" \
  "$API_BASE_URL/platform/queue/dead-letters/$JOB_ID/replay" | jq '.data'
```

Expected response shape:
- `.data.replayed == true`
- `.data.job_id == $JOB_ID`

3. Drain the DLQ only when you intend to delete all current dead letters.

Current implementation drains the full DLQ and does not accept `max_items` or `requeue` in the request body.

```bash
curl -s -X POST -H "Authorization: Bearer $ADMIN_TOKEN" \
  "$API_BASE_URL/platform/queue/dead-letters/drain" | jq '.data'
```

Expected response shape:
- `.data.drained` — number of dead-lettered jobs removed

Warning:
- `POST /platform/queue/dead-letters/drain` is destructive. It removes all current dead letters.
- There is no bulk `requeue=true` mode in the current platform API.
- If the root cause is still present, replaying jobs one-by-one will just fail them again.

## Verification
How to confirm the system is healthy after recovery.

1. Queue backend is Redis again.

```bash
curl -s "$API_BASE_URL/health" | jq '.dependencies.queue'
```

Expected output:
- `"status": "ok"`
- `"backend": "redis"`
- `"degraded": false`

2. DLQ depth is stable or decreasing.

```bash
curl -s -H "Authorization: Bearer $ADMIN_TOKEN" \
  "$API_BASE_URL/platform/queue/health" | jq '.data | {dlq_depth, queue_depth, in_flight_count}'
```

Expected output:
- `dlq_depth` is `0` or decreasing after replay/remediation

3. Worker is processing jobs.

```bash
redis-cli -u "${AINDY_REDIS_URL:-$REDIS_URL}" GET aindy:worker:heartbeat
redis-cli -u "${AINDY_REDIS_URL:-$REDIS_URL}" HLEN aindy:jobs:inflight
```

Expected output:
- `aindy:worker:heartbeat` returns a recent timestamp
- `HLEN aindy:jobs:inflight` changes over time while backlog drains

4. Old pending/running automation logs have cleared.

```bash
psql "$DATABASE_URL" -c "
SELECT id, source, task_name, status, created_at, started_at, completed_at
FROM automation_logs
WHERE status IN ('pending', 'running')
  AND created_at < NOW() - INTERVAL '10 minutes'
ORDER BY created_at ASC;
"
```

Expected output:
- Zero rows, or only rows that are actively being investigated as application-level failures

## Prevention
- Set `AINDY_REQUIRE_REDIS=true` in any production deployment that runs `EXECUTION_MODE=distributed`. This turns queue-backend loss into a startup error instead of a silent fallback to non-durable mode.
- Alert on `/health` when `.dependencies.queue.degraded == true` or `.dependencies.queue.backend != "redis"` while `EXECUTION_MODE=distributed`.
- Monitor `automation_logs` rows with `status='running'` older than 5 minutes. These usually mean the worker is stalled, the queue is degraded, or a job is stuck.

## Escalation
If recovery fails after the documented attempts, contact `platform-team`.

Escalate immediately if:
- DLQ depth is growing faster than replay/remediation can drain it
- Redis is healthy but `/health` still shows `.dependencies.queue.backend == "memory"` after one API restart
- `automation_logs` rows remain in `status='running'` for more than 15 minutes after worker restart
