---
title: "Runbook: WAIT Flow Dead-Letter"
last_verified: "2026-04-26"
api_version: "1.0"
status: current
owner: "platform-team"
severity: P3
---

# Runbook: WAIT Flow Dead-Letter

## Severity
**P3** — background flow execution is impaired because one or more flows are waiting indefinitely for events that never arrived.

## Symptoms
- `flow_runs.status = 'waiting'` for an unexpectedly long time
- `waiting_flow_runs` rows accumulate without clearing
- Log line from the watchdog: `[resume_watchdog] Flow %s has been waiting for %r since %s but event was emitted at %s - attempting resume.`
- Log line from the wait recovery poll: `[WaitRecovery] unresolved waiting row run=%s event=%s age_minutes=%d instance=%s`
- User-visible impact: automation or workflow completion never resumes after a WAIT node.

## Immediate Triage
First 5 minutes: confirm this is an unresolved WAIT, not a Redis outage or generic stuck `running` run.

There is no dedicated wait-flows observability endpoint in this codebase. Use the DB tables directly.

```bash
psql "$DATABASE_URL" -c "SELECT id, flow_name, status, waiting_for, wait_deadline, trace_id, updated_at FROM flow_runs WHERE status = 'waiting' ORDER BY updated_at ASC;"
```

Expected output if this is the problem:
- One or more `flow_runs.status = 'waiting'`

```bash
psql "$DATABASE_URL" -c "SELECT run_id, event_type, correlation_id, waited_since, max_wait_seconds, timeout_at, instance_id FROM waiting_flow_runs ORDER BY waited_since ASC;"
```

Expected output if this is the problem:
- Rows identify the exact event name and age of the wait

Expected output if this is not the problem:
- No waiting rows; use [Runbook: Stuck Runs](RUNBOOK_STUCK_RUNS.md) or [Runbook: Redis Failure](RUNBOOK_REDIS_FAILURE.md).

### This runbook is NOT for
- `flow_runs.status = 'running'` with stale `updated_at`; use [Runbook: Stuck Runs](RUNBOOK_STUCK_RUNS.md).
- Cross-instance resume failures caused by Redis outage; use [Runbook: Redis Failure](RUNBOOK_REDIS_FAILURE.md).

## Root Cause
WAIT state is persisted in two places:
- `flow_runs.waiting_for` and `flow_runs.wait_deadline`
- `waiting_flow_runs` rows with `event_type`, `correlation_id`, `waited_since`, `max_wait_seconds`, and `timeout_at`

The scheduler rehydrates these waits on startup using:
- `rehydrate_waiting_eus()` in [AINDY/core/wait_rehydration.py](/abs/path/C:/dev/masterplan-infiniteweave-monday-node-2025-0411/AINDY/core/wait_rehydration.py)
- `rehydrate_waiting_flow_runs()` in [AINDY/core/flow_run_rehydration.py](/abs/path/C:/dev/masterplan-infiniteweave-monday-node-2025-0411/AINDY/core/flow_run_rehydration.py)

Time-based expiry is enforced by scheduled jobs in [AINDY/platform_layer/recovery_jobs.py](/abs/path/C:/dev/masterplan-infiniteweave-monday-node-2025-0411/AINDY/platform_layer/recovery_jobs.py):
- `expire_timed_out_waits()` for `flow_runs.wait_deadline`
- `expire_timed_out_wait_flows()` for `waiting_flow_runs.max_wait_seconds`

If no event is ever emitted, the wait can persist until deadline expiry or manual intervention.

## Implementation Status

Implemented (see `AINDY/agents/dead_letter_service.py`).
Timed-out flows are moved to `status="dead_letter"` by the stuck-run scanner
when `flow_runs.updated_at < NOW() - FLOW_WAIT_TIMEOUT_MINUTES`.

## Recovery Procedure

### Detection

1. List all waiting FlowRuns.

```bash
psql "$DATABASE_URL" -c "SELECT id, flow_name, waiting_for, wait_deadline, trace_id, created_at, updated_at FROM flow_runs WHERE status = 'waiting' ORDER BY updated_at ASC;"
```

2. List all persisted wait registrations.

```bash
psql "$DATABASE_URL" -c "SELECT run_id, event_type, correlation_id, waited_since, max_wait_seconds, timeout_at, eu_id, instance_id FROM waiting_flow_runs ORDER BY waited_since ASC;"
```

3. Check whether the expected event was already persisted.

```bash
psql "$DATABASE_URL" -c "SELECT type, trace_id, source, timestamp FROM system_events WHERE timestamp >= NOW() - INTERVAL '2 hours' ORDER BY timestamp DESC LIMIT 100;"
```

Success looks like:
- If a matching `system_events.type` and `trace_id` exists, the resume watchdog should recover it.
- If no matching event exists, this is a true dead-letter wait.

Additional dead-letter checks:

```bash
# Count dead-lettered flows
psql "$DATABASE_URL" -c "SELECT count(*) FROM flow_runs WHERE status = 'dead_letter';"

# List recent dead-lettered flows via API
curl -s -H "Authorization: Bearer $JWT" http://localhost:8000/observability/dead-letter | jq '.flows[] | {id, flow_name, dead_letter_reason, dead_lettered_at}'

# Inspect a specific dead-lettered flow
curl -s -H "Authorization: Bearer $JWT" http://localhost:8000/observability/dead-letter/<flow_run_id> | jq

# Prometheus metric (if OTEL/metrics configured)
curl -s http://localhost:8000/metrics | grep aindy_flow_runs_dead_lettered_total
```

### Automated Expiry

This tree includes automated expiry jobs:
- `expire_timed_out_waits()` runs every 5 minutes and fails waiting FlowRuns whose `wait_deadline` is in the past.
- `expire_timed_out_wait_flows()` runs every 60 seconds and fails `waiting_flow_runs` rows whose `max_wait_seconds` has elapsed.
- `scan_and_recover_stuck_runs()` moves stale waiting flows to `status='dead_letter'` with `dead_letter_reason` and `dead_lettered_at`.

Relevant logs:
- `Expired %d timed-out waiting FlowRun(s)`
- `Expired %d timed-out WaitingFlowRun(s)`
- `WAIT flow timeout recovery job failed (non-fatal): %s`
- `Timed-out WaitingFlowRun recovery dispatch failed: %s`

There is also a leader-only APScheduler watchdog in [AINDY/agents/stuck_run_watchdog.py](/abs/path/C:/dev/masterplan-infiniteweave-monday-node-2025-0411/AINDY/agents/stuck_run_watchdog.py):
- `watchdog_scan()` logs recovered stuck runs and dead-lettered wait flows on the configured interval

### Manual Resolution

1. If the matching event should have existed already, restart the API once to force WAIT rehydration.

```bash
docker compose restart api
```

Success looks like:
- Logs include `[startup] WAIT rehydration registered %d EU(s)` and `[startup] FlowRun rehydration registered %d run(s)`

2. If this is an agent-owned stalled execution, check whether the underlying agent run can be recovered through:

```bash
curl -s -X POST -H "Authorization: Bearer $ADMIN_TOKEN" "$API_BASE_URL/apps/agent/runs/{run_id}/recover?force=true"
```

Use this only when the waiting flow belongs to an agent execution and the caller is the run owner. The route cannot recover arbitrary waits generically.

## Impact Assessment

Dead-lettered flows are terminal - they will not resume automatically.
The flow's intended outcome did not complete.

| Scenario | User Impact |
|---|---|
| Task-completion flow dead-lettered | Task remains in its pre-completion state |
| Agent run flow dead-lettered | Agent run is stranded; use `/agent/runs/{id}/recover` |
| Memory write flow dead-lettered | Memory node may not have been persisted |

## Recovery Options

### Option 1: Replay via the existing replay endpoint

```bash
# If the flow supports replay (has a replayed_from_run_id path):
curl -s -X POST "http://localhost:8000/agent/runs/<agent_run_id>/replay" \
  -H "Authorization: Bearer $JWT" | jq
```

### Option 2: Manual state correction

For flows where the application state is recoverable:

```bash
# Re-trigger the original action that started the flow.
# Dead-lettered flows do not auto-replay - the action must be re-initiated.
echo "Re-initiate the original triggering action"
```

### Option 3: Administrative cleanup

```bash
# Mark a dead-lettered flow as acknowledged (no replay):
# There is no built-in "acknowledge" endpoint yet.
# Direct DB update (admin only):
psql "$DATABASE_URL" -c "
  UPDATE flow_runs
  SET status = 'failed',
      dead_letter_reason = dead_letter_reason || ' | acknowledged'
  WHERE id = '<flow_run_id>'
    AND status = 'dead_letter';
"
```

3. Last-resort direct DB failure of a WAIT run.

Warning: confirm no active process is still working the row before writing.

Read-only confirmation:

```bash
psql "$DATABASE_URL" -c "SELECT id, status, waiting_for, wait_deadline, updated_at FROM flow_runs WHERE id = '[run_id]';"
```

Last-resort write:

```bash
psql "$DATABASE_URL" -c "UPDATE flow_runs SET status = 'failed', waiting_for = NULL, wait_deadline = NULL, error_message = 'Manually failed by operator — wait event never received', completed_at = NOW() WHERE id = '[run_id]' AND status = 'waiting';"
```

Clean up the persisted wait row if it still exists:

```bash
psql "$DATABASE_URL" -c "DELETE FROM waiting_flow_runs WHERE run_id = '[run_id]';"
```

Success looks like:
- `UPDATE 1`
- `DELETE 1` or `DELETE 0` if the row was already cleaned up

If this fails:
- `UPDATE 0` means the row is no longer in `waiting`; re-query before doing anything else.

## Investigation

1. Identify what the flow was waiting for.

```bash
psql "$DATABASE_URL" -c "SELECT id, waiting_for, wait_deadline, trace_id, error_message FROM flow_runs WHERE id = '[run_id]';"
psql "$DATABASE_URL" -c "SELECT run_id, event_type, correlation_id, waited_since, max_wait_seconds, timeout_at FROM waiting_flow_runs WHERE run_id = '[run_id]';"
```

2. Inspect related system events.

```bash
psql "$DATABASE_URL" -c "SELECT type, source, trace_id, timestamp, payload FROM system_events WHERE trace_id = '[trace_id]' ORDER BY timestamp ASC;"
```

3. If automated expiry should have fired, look for:
- `WAIT_TIMEOUT` events emitted by `_emit_wait_timeout_system_event()`
- error events with `source='startup_recovery'` or payload `recovery_type`

## Verification

```bash
psql "$DATABASE_URL" -c "SELECT id, status, error_message, completed_at FROM flow_runs WHERE id = '[run_id]';"
psql "$DATABASE_URL" -c "SELECT run_id, event_type FROM waiting_flow_runs WHERE run_id = '[run_id]';"
```

Expected output:
- `flow_runs.status` is terminal, typically `dead_letter` or `failed`
- the `waiting_flow_runs` row is gone
- if automated timeout handled it, `error_message` is `WAIT_TIMEOUT`, `Flow wait deadline expired`, or a `wait_timeout:<N>m` dead-letter reason

## Prevention
- Set sane per-flow deadlines so `wait_deadline` is populated.
- Monitor `waiting_flow_runs` age and volume.
- Design wake events to be idempotent and observable through `system_events`.
- Keep `FLOW_WAIT_TIMEOUT_MINUTES` appropriate for real workloads.
- Increase `FLOW_WAIT_TIMEOUT_MINUTES` if legitimate flows need more time.
- Ensure the event source that should fire the resume event is healthy.
- Monitor `aindy_flow_runs_dead_lettered_total` for unexpected spikes.

## Escalation
Escalate to `platform-team` if:
- the same wait pattern repeats for the same flow after manual cleanup
- the timeout jobs are not firing even though scheduler leadership is healthy
- you cannot determine the expected wake event from `waiting_flow_runs` and `system_events`
