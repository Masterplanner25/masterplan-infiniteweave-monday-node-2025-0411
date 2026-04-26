---
title: "A.I.N.D.Y. Failure Mode Runbooks"
last_verified: "2026-04-25"
api_version: "1.0"
status: current
owner: "platform-team"
---

# A.I.N.D.Y. Failure Mode Runbooks

Commands below assume you are in the repository root and the API writes logs to:

```bash
export LOG_FILE="logs/aindy_${ENV:-production}.log"
```

If your deployment wraps the API in a service manager or container platform, run the equivalent service restart command after editing `AINDY/.env`.

---

## OpenAI Degradation

### What This Is
OpenAI degradation affects two very different paths in this codebase. Memory writes no longer block on embeddings: `MemoryNodeDAO.save()` persists the row with `embedding_pending=True` and `embedding_status="pending"`, then `memory/embedding_jobs.py` retries embeddings asynchronously through the scheduler. Agent planning and other chat-completion features still call OpenAI synchronously through `AINDY/platform_layer/openai_client.py`, which applies a 3-attempt retry with exponential backoff, a 60-second circuit breaker after 3 terminal failures, and per-call timeouts from `OPENAI_CHAT_TIMEOUT_SECONDS` and `OPENAI_EMBEDDING_TIMEOUT_SECONDS`. When OpenAI is slow or down, memory writes continue, semantic recall degrades to empty/low-signal results, and chat-backed features such as agent planning, Genesis, LeadGen, Research, and ARM can return errors or retryable 503s.

### Detection
- Primary signal: `/health` shows `dependencies.ai_providers.status = "degraded"` and `dependencies.ai_providers.openai.circuit = "open"`.
- Secondary signals: rising `memory_ingest_queue.depth`, growing `memory_nodes.embedding_pending`, and retry/error logs from `openai_client.py`, `embedding_service.py`, `embedding_jobs.py`, `agent_runtime`, or Genesis.
- Log search commands:
```bash
grep -E "\[OpenAI\] chat retry attempt|\[OpenAI\] embedding retry attempt|\[EmbeddingService\]|\[EmbeddingJobs\] embedding deferred|\[AgentRuntime\] Plan generation failed|\[Genesis\] OpenAI circuit open" "$LOG_FILE" | tail -50
grep -E "429|RateLimitError|APITimeoutError|APIConnectionError|circuit open|rejecting call" "$LOG_FILE" | tail -50
```
- Health endpoint check:
```bash
curl -s http://localhost:8000/health | jq '.dependencies.ai_providers, .memory_ingest_queue'
curl -s http://localhost:8000/health/deep | jq '.checks.redis, .checks.worker, .checks.scheduler'
```
- Config timeout check:
```bash
grep -E "OPENAI_CHAT_TIMEOUT_SECONDS|OPENAI_EMBEDDING_TIMEOUT_SECONDS|OPENAI_MAX_RETRIES|OPENAI_RETRY_BACKOFF_BASE_SECONDS" AINDY/.env
```

### Impact

| Component | Status | User Impact |
|-----------|--------|-------------|
| Memory writes (`POST /memory/nodes`, internal memory capture) | DEGRADED | Writes still succeed; rows remain `embedding_pending=True` until OpenAI recovers |
| Embedding worker | DEGRADED | Scheduler keeps retrying pending embeddings every minute; backlog grows |
| Semantic recall / similarity search | DEGRADED | Query embedding falls back to zero-vector behavior; semantic results may be empty |
| Agent planning (`POST /agent/run`) | DOWN | Plan generation can fail and return a 500 from the agent flow |
| Genesis / LeadGen / Research / ARM chat-backed endpoints | DEGRADED or DOWN | Many routes return retryable 503s or route-specific failures while the circuit is open |
| Platform core health | UNAFFECTED | `/health` stays HTTP 200 unless another critical dependency fails |

### Immediate Containment
1. Confirm the OpenAI circuit is actually open:
```bash
curl -s http://localhost:8000/health | jq '.dependencies.ai_providers'
```
Expected degraded output:
```json
{"status":"degraded","openai":{"circuit":"open","failure_count":3}}
```
2. Confirm this is not only an embedding backlog:
```bash
grep -E "\[AgentRuntime\] Plan generation failed|\[Genesis\] OpenAI circuit open|\[OpenAI\] chat retry attempt" "$LOG_FILE" | tail -20
```
3. Check whether the system is safely degrading on the memory side:
```bash
curl -s http://localhost:8000/health | jq '.memory_ingest_queue'
psql "$DATABASE_URL" -c "SELECT count(*) AS pending_embeddings FROM memory_nodes WHERE embedding_pending = true;"
```
4. Stop initiating bulk or manual AI-heavy work until recovery is verified. There is no runtime feature flag in this codebase to hot-disable agent planning or embeddings independently; the only safe containment is traffic reduction while the circuit breaker is open.
5. Do not restart the API repeatedly during an upstream outage. The circuit breaker already reduces load after 3 failures and a restart only closes it and replays pressure immediately.

### Root Cause Verification
Use these checks to distinguish upstream OpenAI degradation from a local application bug:

```bash
curl -s http://localhost:8000/health | jq '.dependencies.ai_providers'
grep -E "\[OpenAI\]|\[EmbeddingService\]|\[AgentRuntime\] Plan generation failed" "$LOG_FILE" | tail -30
```

OpenAI degradation is the likely root cause when:
- the circuit is `open` or retry attempts are repeating
- both embedding and chat-completion paths show failures
- Redis, PostgreSQL, and scheduler checks remain healthy in `/health` or `/health/deep`

Distinguish it from a scheduler-only problem with:

```bash
curl -s http://localhost:8000/health/deep | jq '.checks.scheduler'
psql "$DATABASE_URL" -c "SELECT count(*) AS pending_embeddings FROM memory_nodes WHERE embedding_pending = true;"
```

If embeddings are piling up but there are no OpenAI retry/circuit logs and scheduler is not running, the problem is scheduler failure, not OpenAI.

### Recovery Steps
1. Confirm the upstream issue on the provider side.
```bash
curl -s http://localhost:8000/health | jq '.dependencies.ai_providers'
```
Expected healthy output before proceeding:
```json
{"status":"ok","openai":{"circuit":"closed","failure_count":0}}
```
2. Verify the application is no longer logging OpenAI retries.
```bash
grep -E "\[OpenAI\] chat retry attempt|\[OpenAI\] embedding retry attempt|\[Genesis\] OpenAI circuit open" "$LOG_FILE" | tail -20
```
Expected result: no new lines appearing after recovery.
3. Let the scheduled embedding sweep drain the backlog. It runs every minute as APScheduler job `process_pending_memory_embeddings`.
```bash
watch -n 30 'psql "$DATABASE_URL" -c "SELECT count(*) AS pending_embeddings FROM memory_nodes WHERE embedding_pending = true;"'
```
Expected result: `pending_embeddings` decreases over time.
4. If `pending_embeddings` is not decreasing, verify the scheduler is running before doing anything else.
```bash
curl -s http://localhost:8000/health/deep | jq '.checks.scheduler'
grep -E "process_pending_memory_embeddings|embedding deferred|Recovered|scheduler" "$LOG_FILE" | tail -50
```
Expected result: scheduler status is `ok`.
5. Re-test one chat-completion route after the circuit closes.
```bash
JWT=$(curl -s -X POST http://localhost:8000/auth/login -H "Content-Type: application/json" -d '{"email":"admin@example.com","password":"change-this"}' | jq -r '.access_token')
curl -s -X POST http://localhost:8000/agent/run \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{"goal":"Summarize one safe next step for today."}' | jq
```
Expected result: a normal agent-run payload or a 202 defer response, not `HTTP 500` and not `{"error":"ai_provider_unavailable"}`.

### Post-Recovery Verification
Run all three checks:

```bash
curl -s http://localhost:8000/health | jq '.dependencies.ai_providers, .memory_ingest_queue'
psql "$DATABASE_URL" -c "SELECT count(*) AS pending_embeddings FROM memory_nodes WHERE embedding_pending = true;"
curl -s http://localhost:8000/health/deep | jq '.checks.scheduler'
```

Healthy recovery means:
- `ai_providers.status` is `ok`
- `openai.circuit` is `closed`
- `pending_embeddings` returns to normal backlog for your environment
- `memory_ingest_queue.depth` is low and `worker_running` is `true`
- scheduler is `ok`

### Prevention (Long-term)
- Prompt 2 moved embedding generation off the write path and is the main reason memory writes survive OpenAI outages.
- Prompt 6 added bounded memory-ingest backpressure so OpenAI outages do not create unbounded ingest growth.
- Add an operator-facing kill switch for chat-heavy routes if this becomes a frequent incident.
- Add per-route synthetic checks for `POST /agent/run` and a minimal Genesis message path so OpenAI degradation is detected before users report it.

---

## Redis Loss

### What This Is
Redis is used by several different runtime features, and the impact depends on how the deployment is configured. The event bus uses Redis pub/sub for cross-instance WAIT/RESUME propagation and degrades to local-only behavior when Redis is unavailable. `RedisWaitRegistry` stores cross-instance resume specs and returns `False`/`None` instead of raising when Redis is unreachable. The cache layer has explicit startup-time behavior: in production, `AINDY_CACHE_BACKEND=redis` with missing or failed Redis initialization degrades to a disabled `NoOpCacheBackend`, not an unsafe in-memory cache. Distributed async job execution and worker heartbeats also depend on Redis. There is no general runtime-wide “Redis hot fallback” for every feature after startup; some features degrade, some stop working cross-instance, and some are only protected during initialization.

### Detection
- Primary signal: `/health` shows `dependencies.redis.status = "unavailable"` or `dependencies.queue.status = "degraded"`, and `/health.wait_resume.propagation_mode` changes away from `cross-instance`.
- Secondary signals: `RedisWaitRegistry.* failed`, event-bus propagation warnings, distributed queue backend warnings, and missing worker heartbeat.
- Log search commands:
```bash
grep -E "RedisWaitRegistry|\\[EventBus\\]|\\[health\\] Redis ping failed|\\[DistributedQueue\\] Redis unavailable|worker heartbeat" "$LOG_FILE" | tail -80
grep -E "ConnectionError|TimeoutError|ECONNREFUSED|NOAUTH|socket_timeout" "$LOG_FILE" | tail -80
```
- Health endpoint check:
```bash
curl -s http://localhost:8000/health | jq '.dependencies.redis, .dependencies.queue, .wait_resume, .cache'
curl -s http://localhost:8000/ready | jq
```
- Direct Redis checks:
```bash
redis-cli -u "$REDIS_URL" ping
redis-cli -u "$REDIS_URL" info server
redis-cli -u "$REDIS_URL" info clients
redis-cli -u "$REDIS_URL" info memory
```

### Impact

| Component | Status | User Impact |
|-----------|--------|-------------|
| Cache with `AINDY_CACHE_BACKEND=redis` at startup | DEGRADED | In production, cache disables to `NoOpCacheBackend`; requests still work but cache misses hit the database |
| Cache with live Redis loss after startup | DEGRADED | `/health` reports Redis unavailable; actual cache behavior depends on the already-initialized backend and can become error-prone or ineffective |
| Event bus | DEGRADED | WAIT/RESUME propagation becomes local-only; cross-instance resume notifications do not travel |
| `RedisWaitRegistry` | DEGRADED | Cross-instance resume spec registration/lookup fails quietly; same-instance waits can still work |
| `waiting_flow_runs` table + `resume_watchdog` | STILL WORKING | Stranded waits can be recovered later from SQL + `SystemEvent`, but not immediately |
| Distributed queue / worker heartbeat | DEGRADED or DOWN | Worker health and job sharing can fail; `/health.dependencies.queue` shows degraded/unavailable |
| Single-instance thread mode | MOSTLY UNAFFECTED | The platform can keep serving if Redis is not contractually required |

### Immediate Containment
1. Confirm Redis loss from inside the platform and directly against Redis:
```bash
curl -s http://localhost:8000/health | jq '.dependencies.redis, .dependencies.queue, .wait_resume'
redis-cli -u "$REDIS_URL" ping
```
Expected failed direct check:
```text
Could not connect to Redis ...
```
2. Determine whether this deployment treats Redis as mandatory:
```bash
grep -E "AINDY_REQUIRE_REDIS|AINDY_CACHE_BACKEND|EXECUTION_MODE|REDIS_URL" AINDY/.env
```
3. Freeze deploys and restarts until you know which mode you are in. Same-process waiting callbacks are held in memory; unnecessary restarts remove the only local wait state you still have during an outage.
4. If `/health.wait_resume.propagation_mode` is `local-only`, assume cross-instance WAIT/RESUME is broken until Redis is healthy again.
5. If `/health.dependencies.queue.status` is degraded or unavailable, stop manually replaying or bulk-enqueueing async jobs until Redis recovers.

### Root Cause Verification
Use the platform and direct Redis CLI together so you can distinguish “Redis is down” from “the app cannot authenticate to Redis” or “only the event bus is misconfigured”.

```bash
curl -s http://localhost:8000/health | jq '.dependencies.redis, .wait_resume'
redis-cli -u "$REDIS_URL" ping
grep -E "RedisWaitRegistry|\\[EventBus\\]|\\[DistributedQueue\\]" "$LOG_FILE" | tail -50
```

Interpretation:
- `redis-cli ... ping` fails and `/health.dependencies.redis.status` is `unavailable`: real Redis outage or network/auth failure.
- `redis-cli ... ping` succeeds but `/health.wait_resume.propagation_mode` is not `cross-instance`: event-bus subscriber problem, not a Redis outage.
- `redis-cli ... ping` succeeds but `/health.dependencies.queue.status` is degraded: distributed queue backend issue, not basic Redis reachability.

### Recovery Steps
1. Verify Redis is actually back before touching the API.
```bash
redis-cli -u "$REDIS_URL" ping
```
Expected output:
```text
PONG
```
2. Verify the platform sees Redis again.
```bash
curl -s http://localhost:8000/health | jq '.dependencies.redis, .dependencies.queue, .wait_resume'
```
Expected healthy values:
- `dependencies.redis.status = "ok"`
- `wait_resume.propagation_mode = "cross-instance"`
3. Check for waiting flows that may have been stranded during the outage.
```bash
psql "$DATABASE_URL" -c "SELECT run_id, event_type, waited_since, timeout_at, correlation_id FROM waiting_flow_runs ORDER BY waited_since ASC LIMIT 20;"
psql "$DATABASE_URL" -c "SELECT id, flow_name, status, waiting_for, updated_at FROM flow_runs WHERE status = 'waiting' ORDER BY updated_at ASC LIMIT 20;"
```
4. Let the resume watchdog and rehydration paths do their work. The watchdog runs from `apps/tasks/bootstrap.py` and checks stale waiting flows every `AINDY_WATCHDOG_INTERVAL_MINUTES`.
```bash
grep -E "\\[resume_watchdog\\]|Cross-instance resume claimed run_id|WAIT/RESUME event" "$LOG_FILE" | tail -80
```
Expected healthy recovery lines include one of:
```text
[resume_watchdog] notify_event resumed ...
Cross-instance resume claimed run_id=...
```
5. If waiting flows remain stuck after Redis is healthy, restart the API once so startup rehydration re-registers waiting callbacks from `waiting_flow_runs`.
```bash
pkill -f "uvicorn AINDY.main:app"
uvicorn AINDY.main:app --host 0.0.0.0 --port 8000
```

### Post-Recovery Verification
Run these checks:

```bash
curl -s http://localhost:8000/health | jq '.dependencies.redis, .dependencies.queue, .wait_resume, .cache'
curl -s http://localhost:8000/ready | jq
psql "$DATABASE_URL" -c "SELECT count(*) AS waiting_runs FROM waiting_flow_runs;"
```

Healthy recovery means:
- Redis ping returns `PONG`
- `/ready.status` is `ready`
- `/health.dependencies.redis.status` is `ok`
- `/health.wait_resume.propagation_mode` is `cross-instance`
- `waiting_flow_runs` count is stable or dropping after queued resumes fire

### Prevention (Long-term)
- Keep `AINDY_REQUIRE_REDIS=true` in any production topology that depends on multi-instance WAIT/RESUME or distributed workers.
- Add a dedicated Redis outage synthetic check that compares `/health.wait_resume.propagation_mode` against `redis-cli ping`.
- Consider making queue and event-bus recovery more explicit after live Redis loss, not only at startup.

---

## Stuck Job Storm

### What This Is
There are two separate stuck-run recovery paths in this codebase. `AINDY/agents/stuck_run_service.py` runs a startup scan that marks stale `flow_runs.status='running'` rows as failed. Separately, APScheduler runs `AINDY/platform_layer/recovery_jobs.py::run_recover_stuck_runs_job()` every 5 minutes and marks every stale `running` FlowRun as failed in one batch. There is no per-scan limit on how many runs are recovered. `STUCK_RUN_THRESHOLD_MINUTES` defaults to 45 and guards classification, but `AINDY_WATCHDOG_INTERVAL_MINUTES` does not control stuck-run scan cadence; it controls the Redis resume watchdog cadence. A storm happens when many runs become stale at once and the periodic recovery job or startup recovery scan processes all of them together, causing a second wave of DB and scheduler load.

### Detection
- Primary signal: repeated stuck-run recovery logs plus a large count of stale `flow_runs` in SQL.
- Secondary signals: scheduler load, elevated DB connections, and many runs with the same stale timestamp range.
- Log search commands:
```bash
grep -E "\\[StuckRunService\\]|Recovered [0-9]+ stuck FlowRun|stuck_run_recovered|recover_stuck_flow_runs" "$LOG_FILE" | tail -100
grep -E "stuck_run_scan_rollback_failed|Stuck-run recovery job failed|Recovery scan FAILED" "$LOG_FILE" | tail -50
```
- Count current stale running flows:
```bash
psql "$DATABASE_URL" -c "
  SELECT count(*) AS stuck_count
  FROM flow_runs
  WHERE status = 'running'
    AND updated_at < NOW() - INTERVAL '45 minutes';
"
```
- Check how concentrated the storm is:
```bash
psql "$DATABASE_URL" -c "
  SELECT date_trunc('minute', updated_at) AS bucket, count(*) AS runs
  FROM flow_runs
  WHERE status = 'running'
    AND updated_at < NOW() - INTERVAL '45 minutes'
  GROUP BY 1
  ORDER BY 1 DESC
  LIMIT 10;
"
```

### Impact

| Component | Status | Notes |
|-----------|--------|-------|
| Flow engine | DEGRADED | Recovery marks many runs failed at once |
| Scheduler | STRESSED | `recover_stuck_flow_runs` runs in one batch every 5 minutes |
| Database | STRESSED | Bulk updates and recovery-related queries hit `flow_runs` together |
| New flow execution | DEGRADED | Shared DB and scheduler capacity are consumed by recovery work |
| User experience | DEGRADED | New executions are delayed, failed, or appear unstable |

### Immediate Containment
1. Confirm it is a storm, not one or two normal recoveries.
```bash
psql "$DATABASE_URL" -c "
  SELECT count(*) AS stuck_count
  FROM flow_runs
  WHERE status = 'running'
    AND updated_at < NOW() - INTERVAL '45 minutes';
"
```
Treat `stuck_count > 10` as a storm unless you have a known larger baseline.
2. Stop the periodic stuck-run recovery loop by raising the threshold well above reality.
```bash
python - <<'PY'
from pathlib import Path
env = Path('AINDY/.env')
text = env.read_text(encoding='utf-8')
if 'STUCK_RUN_THRESHOLD_MINUTES=' in text:
    import re
    text = re.sub(r'^STUCK_RUN_THRESHOLD_MINUTES=.*$', 'STUCK_RUN_THRESHOLD_MINUTES=9999', text, flags=re.MULTILINE)
else:
    text += '\nSTUCK_RUN_THRESHOLD_MINUTES=9999\n'
env.write_text(text, encoding='utf-8')
print('STUCK_RUN_THRESHOLD_MINUTES set to 9999')
PY
```
3. Restart the API so the new threshold takes effect.
```bash
pkill -f "uvicorn AINDY.main:app"
uvicorn AINDY.main:app --host 0.0.0.0 --port 8000
```
4. Verify the platform is back but not classifying new runs as stuck.
```bash
curl -s http://localhost:8000/health | jq '.stuck_run'
```
Expected output includes:
```json
{"threshold_minutes":9999}
```
5. Do not restore the normal threshold until you verify the real root cause below.

### Root Cause Verification
Check the likely causes in this order.

1. Worker process missing or unhealthy:
```bash
pgrep -af "AINDY.worker|worker_loop"
```
Expected healthy result: at least one worker process if `EXECUTION_MODE=distributed`.

2. Scheduler lease/heartbeat issue:
```bash
psql "$DATABASE_URL" -c "
  SELECT name, owner_id, heartbeat_at, expires_at
  FROM background_task_leases
  ORDER BY heartbeat_at DESC;
"
```
Expected healthy result: one current `heartbeat_at` and `expires_at > NOW()`.

3. DB connection pressure:
```bash
psql "$DATABASE_URL" -c "
  SELECT count(*) AS active_connections
  FROM pg_stat_activity
  WHERE state = 'active';
"
curl -s http://localhost:8000/health | jq '.db_pool'
```

4. OpenAI-driven upstream slowdown that made many flows stale:
```bash
curl -s http://localhost:8000/health | jq '.dependencies.ai_providers'
grep -E "\\[OpenAI\\]|\\[AgentRuntime\\] Plan generation failed|\\[EmbeddingService\\]" "$LOG_FILE" | tail -50
```

5. WAIT/RESUME coordination issue instead of general stuck-run failure:
```bash
curl -s http://localhost:8000/health | jq '.wait_resume'
psql "$DATABASE_URL" -c "SELECT count(*) AS waiting_count FROM waiting_flow_runs;"
```

### Recovery Steps
1. Fix the real root cause first. Do not lower the threshold while workers, scheduler, Redis, or DB are still unhealthy.
2. Restore the normal stuck-run threshold.
```bash
python - <<'PY'
from pathlib import Path
import re
env = Path('AINDY/.env')
text = env.read_text(encoding='utf-8')
text = re.sub(r'^STUCK_RUN_THRESHOLD_MINUTES=.*$', 'STUCK_RUN_THRESHOLD_MINUTES=45', text, flags=re.MULTILINE)
env.write_text(text, encoding='utf-8')
print('STUCK_RUN_THRESHOLD_MINUTES restored to 45')
PY
```
3. Restart the API again with the normal threshold.
```bash
pkill -f "uvicorn AINDY.main:app"
uvicorn AINDY.main:app --host 0.0.0.0 --port 8000
```
4. Watch the stale-running count decrease over successive 5-minute scheduler scans.
```bash
watch -n 30 'psql "$DATABASE_URL" -c "SELECT count(*) AS stuck_count FROM flow_runs WHERE status = '\''running'\'' AND updated_at < NOW() - INTERVAL '\''45 minutes'\'';"'
```
Expected result: `stuck_count` decreases every few minutes.
5. If individual agent runs remain stuck after the system is stable, recover one specific stale agent run.
```bash
JWT=$(curl -s -X POST http://localhost:8000/auth/login -H "Content-Type: application/json" -d '{"email":"admin@example.com","password":"change-this"}' | jq -r '.access_token')
RUN_ID=$(psql "$DATABASE_URL" -Atc "SELECT ar.id FROM agent_runs ar JOIN flow_runs fr ON fr.id = ar.flow_run_id WHERE ar.status = 'executing' AND fr.status = 'running' AND fr.updated_at < NOW() - INTERVAL '45 minutes' ORDER BY fr.updated_at ASC LIMIT 1;")
curl -s -X POST "http://localhost:8000/agent/runs/${RUN_ID}/recover?force=true" \
  -H "Authorization: Bearer $JWT" | jq
```
Expected result:
```json
{"ok":true,...}
```

### Post-Recovery Verification
Run all four checks:

```bash
psql "$DATABASE_URL" -c "
  SELECT count(*) AS stuck_count
  FROM flow_runs
  WHERE status = 'running'
    AND updated_at < NOW() - INTERVAL '45 minutes';
"
psql "$DATABASE_URL" -c "
  SELECT name, owner_id, heartbeat_at, expires_at
  FROM background_task_leases
  ORDER BY heartbeat_at DESC;
"
curl -s http://localhost:8000/health | jq '.stuck_run, .dependencies, .wait_resume'
curl -s http://localhost:8000/ready | jq
```

Recovery is complete when:
- `stuck_count` is `0`
- the scheduler lease heartbeat is current
- `/ready.status` is `ready`
- `/health.stuck_run.threshold_minutes` is back to `45`
- Redis, queue, and AI provider checks are not degraded due to the original root cause

### Prevention (Long-term)
- Prompt 1 prevents the `STUCK_RUN_THRESHOLD_MINUTES <= FLOW_WAIT_TIMEOUT_MINUTES` misconfiguration that can manufacture false stuck runs.
- Prompt 7 reduces abandoned `running` rows during shutdown by draining in-flight work.
- Add a max-batch or rate limit inside `platform_layer/recovery_jobs.py::recover_stuck_runs()`; today it processes every stale run in one scan.
- Expose a runtime operator toggle for stuck-run recovery so containment does not require editing `AINDY/.env` and restarting the API.
