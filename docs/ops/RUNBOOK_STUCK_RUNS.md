---
title: "Runbook: Stuck Runs"
last_verified: "2026-04-25"
api_version: "1.0"
status: current
owner: "platform-team"
severity: P2
---

# Runbook: Stuck Runs

## Severity
**P2** — execution is degraded because FlowRuns or AgentRuns are stranded in non-terminal state after a crash or bug.

## Symptoms
- Startup log: `[StuckRunService] Startup scan: found %d stuck run(s) (threshold=%dm)`
- Startup log: `[startup] Stuck-run scan recovered %d run(s)`
- Recovery failure log: `[startup] Recovery scan FAILED [%s]: %s - stuck runs may exist. Check the SystemEvent table for recovery_type='%s'.`
- Manual recovery log: `[StuckRunService] Manual recovery: AgentRun %s marked failed (%d steps)`
- User-visible impact: a run stays `running` or `executing` but no new work occurs and no terminal state is reached.

## Immediate Triage
First 5 minutes: confirm whether this is a generic FlowRun problem or a user-owned AgentRun that can be recovered via API.

```bash
psql "$DATABASE_URL" -c "SELECT id, flow_name, workflow_type, status, updated_at, trace_id FROM flow_runs WHERE status = 'running' ORDER BY updated_at ASC LIMIT 20;"
```

Expected output if this is the problem:
- One or more `flow_runs.status = 'running'` rows with old `updated_at` values

```bash
psql "$DATABASE_URL" -c "SELECT id, status, started_at, completed_at, flow_run_id FROM agent_runs WHERE status = 'executing' ORDER BY started_at ASC LIMIT 20;"
```

Expected output if this is the problem:
- One or more `agent_runs.status = 'executing'` rows with no `completed_at`

Expected output if this is not the problem:
- No stale non-terminal rows; check [Runbook: Redis Failure](RUNBOOK_REDIS_FAILURE.md) or [Runbook: WAIT Flow Dead-Letter](RUNBOOK_WAIT_FLOW_DEADLETTER.md).

### This runbook is NOT for
- Flows stuck in `waiting` because the wake event never arrived; use [Runbook: WAIT Flow Dead-Letter](RUNBOOK_WAIT_FLOW_DEADLETTER.md).
- Scheduler leadership loss with no new background jobs running; use [Runbook: Leader Failover](RUNBOOK_LEADER_FAILOVER.md).

## Root Cause
The startup recovery path in [AINDY/startup.py](/abs/path/C:/dev/masterplan-infiniteweave-monday-node-2025-0411/AINDY/startup.py) calls `scan_and_recover_stuck_runs()` from [AINDY/agents/stuck_run_service.py](/abs/path/C:/dev/masterplan-infiniteweave-monday-node-2025-0411/AINDY/agents/stuck_run_service.py). A FlowRun is considered stuck when `flow_runs.status == 'running'` and `flow_runs.updated_at` is older than `STUCK_RUN_THRESHOLD_MINUTES`. Agent recovery is special-cased for `workflow_type == 'agent_execution'`; generic FlowRuns are marked failed only. A separate periodic scheduler job in [AINDY/platform_layer/recovery_jobs.py](/abs/path/C:/dev/masterplan-infiniteweave-monday-node-2025-0411/AINDY/platform_layer/recovery_jobs.py) only recovers stale `flow_runs.status == 'running'`; it does not handle `agent_runs` directly.

## Recovery Procedure

### Detection

1. Check the configured threshold.

```bash
python - <<'PY'
from AINDY.config import settings
print("STUCK_RUN_THRESHOLD_MINUTES =", settings.STUCK_RUN_THRESHOLD_MINUTES)
print("FLOW_WAIT_TIMEOUT_MINUTES =", settings.FLOW_WAIT_TIMEOUT_MINUTES)
PY
```

Success looks like:
- A threshold larger than `FLOW_WAIT_TIMEOUT_MINUTES`

2. Query stale FlowRuns directly.

```bash
psql "$DATABASE_URL" -c "SELECT id, flow_name, workflow_type, status, created_at, updated_at, wait_deadline, waiting_for FROM flow_runs WHERE status = 'running' AND updated_at < NOW() - INTERVAL '45 minutes' ORDER BY updated_at ASC;"
```

3. Query stale AgentRuns directly.

```bash
psql "$DATABASE_URL" -c "SELECT id, user_id, status, flow_run_id, started_at, completed_at FROM agent_runs WHERE status = 'executing' AND started_at < NOW() - INTERVAL '45 minutes' ORDER BY started_at ASC;"
```

### Automatic Recovery

The startup scan does this automatically:
- For generic FlowRuns: `_recover_generic_run()` sets `status='failed'`, clears `waiting_for` and `wait_deadline`, sets `error_message='Stuck run recovery: process terminated before completion'`, and sets `error_detail.reason='stuck_run_recovered'`.
- For agent FlowRuns: `_recover_agent_run()` also marks the linked AgentRun `failed` and reconstructs `result.steps` from `agent_steps`.

Relevant logs:
- `[StuckRunService] Startup scan: no stuck runs (threshold=%dm)`
- `[StuckRunService] Startup scan: found %d stuck run(s) (threshold=%dm)`
- `[StuckRunService] Recovered AgentRun %s (flow_run=%s, %d steps committed)`
- `[StuckRunService] Recovered generic FlowRun %s (type=%s)`
- `[startup] Stuck-run scan recovered %d run(s)`

If a restart is safe, trigger the startup scan again:

```bash
docker compose restart api
```

### Manual Recovery for AgentRuns

There is one operator-triggered recovery endpoint for agent runs:
- `POST /apps/agent/runs/{run_id}/recover`

Important behavior from `recover_stuck_agent_run()`:
- only the run owner can recover it
- returns logical errors `not_found`, `forbidden`, `wrong_status`, `too_recent`, or `internal_error`
- route maps `wrong_status` and `too_recent` to HTTP `409`
- `?force=true` overrides the age gate

Run it as the owning user:

```bash
curl -s -X POST -H "Authorization: Bearer $ADMIN_TOKEN" "$API_BASE_URL/apps/agent/runs/{run_id}/recover?force=true"
```

Success looks like:
- HTTP `200` with a recovered run payload

If this fails:
- HTTP `403` means the token does not belong to the run owner.
- HTTP `409` with `Run is not in executing state` means it is already terminal or not eligible.
- HTTP `409` with `Run started less than ... minutes ago` means use `force=true` or wait until the threshold passes.

### Last-Resort DB Recovery

Use this only if:
- the startup scan did not recover the run
- the agent recovery endpoint cannot be used
- you have confirmed the run is not actively executing anywhere

Read-only confirmation first:

```bash
psql "$DATABASE_URL" -c "SELECT id, status, updated_at, trace_id FROM flow_runs WHERE id = '[flow_run_id]';"
psql "$DATABASE_URL" -c "SELECT id, status, started_at, completed_at FROM agent_runs WHERE id = '[agent_run_id]';"
```

Last-resort write:

```bash
psql "$DATABASE_URL" -c "UPDATE flow_runs SET status = 'failed', waiting_for = NULL, wait_deadline = NULL, error_message = 'Stuck run recovery: process terminated before completion', completed_at = NOW() WHERE id = '[flow_run_id]' AND status = 'running';"
```

If the linked AgentRun also needs manual terminalization:

```bash
psql "$DATABASE_URL" -c "UPDATE agent_runs SET status = 'failed', error_message = 'Stuck run recovery: process terminated before completion', completed_at = NOW() WHERE id = '[agent_run_id]' AND status = 'executing';"
```

Success looks like:
- `UPDATE 1`

If this fails:
- `UPDATE 0` means the row no longer matches the expected state. Re-query before trying again.

## Verification

```bash
psql "$DATABASE_URL" -c "SELECT id, status, error_message, completed_at FROM flow_runs WHERE id = '[flow_run_id]';"
psql "$DATABASE_URL" -c "SELECT id, status, error_message, completed_at FROM agent_runs WHERE id = '[agent_run_id]';"
```

Expected output:
- `flow_runs.status` is `failed` or another terminal state
- `agent_runs.status` is `failed`, `completed`, or `rejected`
- `error_message` matches `Stuck run recovery: process terminated before completion` for recovered runs

## Prevention
- Alert on startup log lines containing `Startup scan: found` and `Recovery scan FAILED`.
- Alert on long-lived `flow_runs.status='running'` and `agent_runs.status='executing'`.
- Keep `STUCK_RUN_THRESHOLD_MINUTES` above `FLOW_WAIT_TIMEOUT_MINUTES`; the config validator already enforces this.

## Escalation
Escalate to `platform-team` if:
- the same run becomes stuck again after recovery
- DB writes are required for multiple runs in one incident
- startup recovery emits `Recovery scan FAILED`
