---
title: "Runbook: Leader Failover"
last_verified: "2026-04-25"
api_version: "1.0"
status: current
owner: "platform-team"
severity: P2
---

# Runbook: Leader Failover

## Severity
**P2** — background jobs are paused because no process currently holds the background task lease.

## Symptoms
- Log line on a non-leader instance: `Background task runner not started (lease unavailable — another instance holds it).`
- Log line on the leader at startup: `Background task lease acquired by %s.`
- Heartbeat failure log: `[BackgroundTaskLease] Heartbeat: lease refresh failed — lease may have been lost.`
- Scheduler status endpoint shows `"scheduler_running": false` or `"is_leader": false` with an expired lease
- User-visible impact: scheduled background jobs, WAIT timeout enforcement, and periodic stuck-run recovery stop advancing.

## Immediate Triage
First 5 minutes: determine whether a leader exists and whether the DB lease is expired.

```bash
curl -s -H "Authorization: Bearer $ADMIN_TOKEN" "$API_BASE_URL/platform/observability/scheduler/status"
```

Expected output if this is the problem:
- A payload shaped like `{"scheduler_running":false,"is_leader":false,"lease":{...}}`
- Or `lease.expires_at` is in the past and no instance reports `is_leader=true`

Expected output if this is not the problem:
- `{"scheduler_running":true,"is_leader":true,"lease":{...}}`

### This runbook is NOT for
- Redis/event-bus degradation affecting WAIT/RESUME propagation; use [Runbook: Redis Failure](RUNBOOK_REDIS_FAILURE.md).
- A single stuck FlowRun or AgentRun with healthy scheduler leadership; use [Runbook: Stuck Runs](RUNBOOK_STUCK_RUNS.md).

## Root Cause
Leadership is implemented in [apps/tasks/services/task_service.py](/abs/path/C:/dev/masterplan-infiniteweave-monday-node-2025-0411/apps/tasks/services/task_service.py) using the `background_task_leases` table. `start_background_tasks()` acquires the lease once at startup via `_acquire_background_lease()`. The leader heartbeats the lease every 60 seconds through the scheduled job `_heartbeat_lease_job()`. The lease TTL is fixed at 120 seconds in `_BACKGROUND_LEASE_TTL_SECONDS`. There is no steady-state follower promotion loop in this codebase: a follower that lost startup election does not retry acquisition until the process is restarted and `system.startup` runs again.

## Recovery Procedure

1. Check current leader status through the API.

```bash
curl -s -H "Authorization: Bearer $ADMIN_TOKEN" "$API_BASE_URL/platform/observability/scheduler/status"
```

2. Inspect the lease row directly.

```bash
psql "$DATABASE_URL" -c "SELECT name, owner_id, acquired_at, heartbeat_at, expires_at FROM background_task_leases WHERE name = 'task_background_runner';"
```

Interpretation:
- `expires_at > NOW()` and `owner_id` still points to a live instance: leadership exists
- `expires_at < NOW()` means the old leader is dead or failed to heartbeat

3. Confirm whether any process is still heartbeating.

Look for these exact log lines on the candidate leader:
- `Background task lease acquired by %s.`
- `Background tasks initialized via APScheduler (daemon threads eliminated).`
- `APScheduler started — daemon threads replaced`
- `[BackgroundTaskLease] Heartbeat: lease refresh failed — lease may have been lost.`

4. If the lease is expired, restart one candidate process to force a fresh startup election.

```bash
docker compose restart api
```

If you run dedicated worker leadership instead:

```bash
docker compose --profile full restart worker
```

Success looks like:
- The restarted process logs:
  - `Background task lease acquired by %s.`
  - `Background tasks initialized via APScheduler (daemon threads eliminated).`
  - `APScheduler started — daemon threads replaced`

5. If a dead leader’s lease is not expiring as expected, force expiry as a last resort.

Warning: do this only after confirming the old leader process is no longer serving scheduler work.

```bash
psql "$DATABASE_URL" -c "UPDATE background_task_leases SET expires_at = NOW(), heartbeat_at = NOW() WHERE name = 'task_background_runner';"
```

Then restart one candidate process again:

```bash
docker compose restart api
```

6. Validate that scheduler jobs were re-registered.

The leader’s scheduler registers platform jobs in [AINDY/platform_layer/scheduler_service.py](/abs/path/C:/dev/masterplan-infiniteweave-monday-node-2025-0411/AINDY/platform_layer/scheduler_service.py), including `expire_timed_out_waits`, `expire_timed_out_wait_flows`, `recover_stuck_flow_runs`, and app-registered jobs such as `background_lease_heartbeat`, `wait_recovery_poll`, and `resume_watchdog`.

## Verification

```bash
curl -s -H "Authorization: Bearer $ADMIN_TOKEN" "$API_BASE_URL/platform/observability/scheduler/status"
psql "$DATABASE_URL" -c "SELECT name, owner_id, heartbeat_at, expires_at FROM background_task_leases WHERE name = 'task_background_runner';"
```

Expected output:
- Endpoint shows `"scheduler_running":true`
- Endpoint shows `"is_leader":true`
- Lease `expires_at` is in the future

Healthy job activity is also indicated by logs such as:
- `Distributed queue backend recovered to Redis`
- `Deferred async jobs resumed: %d`
- `Recovered %d stuck FlowRun(s)`
- `Expired %d timed-out WaitingFlowRun(s)`

## Prevention
- Alert when `GET /platform/observability/scheduler/status` reports no leader or `scheduler_running=false`.
- Alert when `background_task_leases.expires_at < NOW()` for `task_background_runner`.
- Alert on heartbeat failure log `[BackgroundTaskLease] Heartbeat: lease refresh failed — lease may have been lost.`

## Known Limitation
> ⚠️ In-progress Nodus scheduled jobs that were executing on the crashed leader are NOT recovered. These jobs must be re-triggered manually or will execute on their next scheduled interval. See: [Nodus](../nodus/index.md).

## Escalation
Escalate to `platform-team` if:
- no instance becomes leader after one forced lease expiry and one restart
- the lease row keeps moving but `scheduler_running` remains false
- scheduled jobs still do not execute after leadership is restored
