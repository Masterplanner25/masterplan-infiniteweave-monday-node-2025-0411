---
title: "Stuck-Run Recovery SLA"
last_verified: "2026-04-28"
api_version: "1.0"
status: current
owner: "platform-team"
---
# Stuck-Run Recovery SLA

## Recovery window

A stuck run will be recovered within:

  AINDY_WATCHDOG_INTERVAL_MINUTES (default: 2 minutes)

after the watchdog next executes, provided the run has been stuck for
longer than:

  STUCK_RUN_THRESHOLD_MINUTES (default: 45 minutes)

## What "stuck" means

A FlowRun or AgentRun is considered stuck when:
- Its status is not terminal (not completed, failed, or dead-lettered)
- Its last activity timestamp is older than STUCK_RUN_THRESHOLD_MINUTES

## Leader failure scenario

If the APScheduler leader instance fails:
1. The next leader starts its watchdog at the next scheduled interval
   (AINDY_WATCHDOG_INTERVAL_MINUTES after its own startup scan).
2. Startup also calls `scan_and_recover_stuck_runs()` immediately on boot,
   so any run that was stuck before the leader failed is recovered within
   seconds of the new leader starting.
3. The maximum gap between leader failure and recovery is therefore:
     time_until_new_leader_starts + AINDY_WATCHDOG_INTERVAL_MINUTES
   In a healthy deployment, new leaders start within 30 seconds.

## Observability

Every watchdog scan emits a SystemEvent of type `"watchdog.scan.completed"`
with the count of recovered and dead-lettered runs.

The current watchdog state is available at:
  `GET /platform/observability/scheduler/status`
  → `result["stuck_run_watchdog"]["last_run_at"]`
  → `result["stuck_run_watchdog"]["last_recovered"]`

A Prometheus counter tracks cumulative recoveries:
  `startup_recovery_runs_recovered_total{recovery_type="watchdog_periodic"}`

## Tuning

| Setting | Default | Effect |
|---|---|---|
| AINDY_WATCHDOG_INTERVAL_MINUTES | 2 | How often the watchdog scans |
| STUCK_RUN_THRESHOLD_MINUTES | 45 | Minimum age before a run is recovered |
| FLOW_WAIT_TIMEOUT_MINUTES | (see config) | When a waiting flow becomes stuck |

STUCK_RUN_THRESHOLD_MINUTES must always be greater than
FLOW_WAIT_TIMEOUT_MINUTES. Startup validates this.

Reducing AINDY_WATCHDOG_INTERVAL_MINUTES below 1 minute is not
recommended — it increases DB load with minimal recovery benefit.
