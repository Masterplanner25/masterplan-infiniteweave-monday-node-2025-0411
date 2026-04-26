---
title: "Runbook: Redis Failure"
last_verified: "2026-04-25"
api_version: "1.0"
status: current
owner: "platform-team"
severity: P1
---

# Runbook: Redis Failure

## Severity
**P1** — Redis failure breaks cross-instance WAIT/RESUME propagation and can block distributed execution paths.

## Symptoms
- Startup failure with `Redis is configured but not reachable at startup. Verify REDIS_URL and Redis availability before starting.`
- Startup warning with `[startup] Redis is not configured (REDIS_URL is unset). Running in single-instance mode. WAIT/RESUME events will not propagate across multiple instances.`
- Runtime warning with `[EventBus] WAIT/RESUME event %r could NOT be propagated to other instances (Redis unavailable). Flows waiting on other instances will not be resumed. correlation_id=%s error=%s`
- Runtime warning with `[EventBus] disabled after %d consecutive failures — Redis unavailable. Set AINDY_EVENT_BUS_ENABLED=false to suppress this.`
- Runtime warning with `[EventBus] subscriber lost connection (%s) — reconnecting in %.1fs`
- Runtime warning with `[startup] WAIT/RESUME is operating in LOCAL-ONLY mode. Flows that enter WAIT on one instance CANNOT be resumed by events received on a different instance.`
- User-visible impact: flows already in `waiting` on another instance stay suspended even after the matching event is emitted.

## Immediate Triage
First 5 minutes: confirm whether this is startup failure, runtime degradation, or post-outage stranded WAIT state.

```bash
redis-cli -u "${AINDY_REDIS_URL:-$REDIS_URL}" ping
```

Expected output if this is the problem:
- `NOAUTH Authentication required.` means the URL is missing credentials.
- `Could not connect to Redis` means Redis is unreachable.
- `PONG` means Redis is reachable and the incident is likely post-outage recovery, not active connectivity loss.

```bash
curl -s "$API_BASE_URL/health"
```

Expected output if this is the problem:
- A `wait_resume` payload with `"propagation_mode":"local-only"` or `"redis_connected":false`

Expected output if this is not the problem:
- `{"status":"healthy",...,"wait_resume":{"propagation_mode":"cross-instance","redis_connected":true,"subscriber_running":true}}`

### This runbook is NOT for
- `GET /ready` returning `restore_pending` or `registry_restore_incomplete`; use the platform restore/readiness recovery process instead.
- A single stranded FlowRun or AgentRun with no Redis symptoms; use [Runbook: Stuck Runs](RUNBOOK_STUCK_RUNS.md).

## Root Cause
Redis is used by the distributed event bus in [AINDY/kernel/event_bus.py](/abs/path/C:/dev/masterplan-infiniteweave-monday-node-2025-0411/AINDY/kernel/event_bus.py), by distributed queue paths, and by multi-instance WAIT/RESUME propagation. At startup, `_enforce_redis_startup_guard()` in [AINDY/startup.py](/abs/path/C:/dev/masterplan-infiniteweave-monday-node-2025-0411/AINDY/startup.py) raises `RuntimeError` when `settings.requires_redis` is true and `REDIS_URL` is missing or unreachable. During runtime, `EventBus.publish()` never raises; it logs warnings, falls back to local-only resume behavior, and disables itself after three consecutive publish failures. The subscriber loop reconnects automatically with exponential backoff from 1s up to 30s.

## Recovery Procedure

### A. Redis is unreachable at startup

1. Confirm the configured Redis URL.

```bash
python - <<'PY'
from AINDY.config import settings
print("REDIS_URL =", settings.REDIS_URL)
print("requires_redis =", settings.requires_redis)
PY
```

Success looks like:
- `REDIS_URL = redis://...`
- `requires_redis = True` for production-style deployments

If this fails:
- Fix environment configuration before restarting AINDY. The startup guard will continue to raise `RuntimeError`.

2. Check the Redis container in the standard deployment.

```bash
docker compose ps redis
docker compose logs --tail=50 redis
```

Success looks like:
- `redis` service is `running`
- Logs do not show crash loops or auth failures

If this fails:
- Start or restart Redis:

```bash
docker compose --profile full up -d redis
docker compose --profile full restart redis
```

3. Verify Redis connectivity from the operator shell.

```bash
redis-cli -u "${AINDY_REDIS_URL:-$REDIS_URL}" ping
```

Success looks like:
- `PONG`

If this fails:
- `NOAUTH Authentication required.` means the URL or password is wrong.
- `Could not connect` means Redis is still down or unreachable on the network path.

4. Restart the API after Redis is healthy.

```bash
docker compose restart api
```

Success looks like:
- API logs include `[startup] Redis connectivity verified.`

If this fails:
- Re-check `REDIS_URL`, `AINDY_REQUIRE_REDIS`, and Redis authentication.

### B. Redis becomes unavailable while the server is running

1. Confirm the event bus degraded to local-only mode.

```bash
curl -s "$API_BASE_URL/health"
```

Success looks like:
- `wait_resume.redis_connected` is `false`, or `wait_resume.propagation_mode` is `local-only`

If this fails:
- If `/health` is down entirely, treat this as a broader API outage first.

2. Confirm runtime Redis loss in logs.

Look for these exact messages:
- `[EventBus] WAIT/RESUME event %r could NOT be propagated to other instances (Redis unavailable). Flows waiting on other instances will not be resumed. correlation_id=%s error=%s`
- `[EventBus] subscriber lost connection (%s) — reconnecting in %.1fs`
- `[EventBus] disabled after %d consecutive failures — Redis unavailable. Set AINDY_EVENT_BUS_ENABLED=false to suppress this.`

3. Restore Redis.

```bash
docker compose --profile full restart redis
redis-cli -u "${AINDY_REDIS_URL:-$REDIS_URL}" ping
```

Success looks like:
- Redis answers `PONG`

If this fails:
- Do not restart AINDY first. The underlying Redis outage must be resolved before cross-instance resume can recover.

4. Wait for automatic subscriber reconnect.

The subscriber loop in `EventBus._subscriber_loop()` reconnects automatically with exponential backoff and logs:
- `[EventBus] subscribed to channel=%s instance=%s`

Verify with:

```bash
curl -s "$API_BASE_URL/health"
```

Success looks like:
- `wait_resume.propagation_mode` becomes `cross-instance`
- `wait_resume.subscriber_running` is `true`
- `wait_resume.redis_connected` is `true`

If this does not recover:
- Restart the API process:

```bash
docker compose restart api
```

### C. Redis recovers but WAIT flows were active during the outage

Redis pub/sub does not replay missed messages. Recovery depends on persisted DB state:
- `rehydrate_waiting_flow_runs()` in [AINDY/core/flow_run_rehydration.py](/abs/path/C:/dev/masterplan-infiniteweave-monday-node-2025-0411/AINDY/core/flow_run_rehydration.py)
- `scan_and_resume_stranded_flows()` in [AINDY/core/resume_watchdog.py](/abs/path/C:/dev/masterplan-infiniteweave-monday-node-2025-0411/AINDY/core/resume_watchdog.py)
- `recover_orphaned_waits()` in [AINDY/kernel/scheduler/recovery.py](/abs/path/C:/dev/masterplan-infiniteweave-monday-node-2025-0411/AINDY/kernel/scheduler/recovery.py)

1. Check for still-waiting flow rows.

```bash
psql "$DATABASE_URL" -c "SELECT run_id, event_type, correlation_id, waited_since, timeout_at, instance_id FROM waiting_flow_runs ORDER BY waited_since ASC;"
```

Success looks like:
- Rows explain which flows were in WAIT during the outage

If this fails:
- Resolve DB connectivity first. Redis recovery alone is not enough for stranded WAIT analysis.

2. Check whether the matching events were already persisted.

```bash
psql "$DATABASE_URL" -c "SELECT type, trace_id, timestamp FROM system_events WHERE timestamp >= NOW() - INTERVAL '2 hours' ORDER BY timestamp DESC LIMIT 50;"
```

Success looks like:
- Matching `type` and `trace_id` values exist for the waiting rows

If matching events exist:
- The `resume_watchdog` job should recover them. Look for:
  - `[resume_watchdog] Flow %s has been waiting for %r since %s but event was emitted at %s - attempting resume.`
  - `[resume_watchdog] notify_event resumed %d flow(s) for event %r (run_id=%s)`
  - `[resume_watchdog] Resumed %d stranded flow(s)`

3. Force a clean rehydration cycle if rows remain stranded.

```bash
docker compose restart api
```

Success looks like:
- API logs include:
  - `[startup] WAIT rehydration registered %d EU(s)`
  - `[startup] FlowRun rehydration registered %d run(s)`
  - `[EventBus] draining %d buffered pre-rehydration event(s)` when buffered events existed

If this fails:
- Escalate if rows remain in `waiting_flow_runs` and matching `system_events` exist after one restart and one watchdog interval.

## Verification

```bash
curl -s "$API_BASE_URL/health"
psql "$DATABASE_URL" -c "SELECT id, status, waiting_for, wait_deadline FROM flow_runs WHERE status = 'waiting' ORDER BY updated_at DESC LIMIT 20;"
```

Expected output:
- `/health` shows `wait_resume.propagation_mode` = `cross-instance`
- `waiting_for` rows decrease or match only intentionally active waits
- If the watchdog recovered a stranded wait, logs include `[resume_watchdog] notify_event resumed %d flow(s) for event %r (run_id=%s)`

## Prevention
- Alert on `/health` `wait_resume.propagation_mode != "cross-instance"` in environments where `requires_redis` is true.
- Alert on repeated `[EventBus] subscriber lost connection` and `[EventBus] disabled after` warnings.
- Monitor `waiting_flow_runs` growth and `resume_watchdog` recovery logs.

## Escalation
Escalate to `platform-team` after one Redis restart and one API restart if:
- `/health` still reports `local-only` mode
- `waiting_flow_runs` rows remain stranded with matching `system_events`
- the API still fails startup with the Redis guard `RuntimeError`
