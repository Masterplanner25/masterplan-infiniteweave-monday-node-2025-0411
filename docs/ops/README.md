---
title: "Operations Runbooks"
last_verified: "2026-04-25"
api_version: "1.0"
status: current
owner: "platform-team"
---

# Operations Runbooks

This directory contains incident response procedures for the A.I.N.D.Y. platform. Each runbook describes symptoms, root cause, recovery steps, and verification for a specific class of production incident.

## Available Runbooks

| Runbook | Severity | Scenario |
|---------|----------|---------|
| [Redis Failure](RUNBOOK_REDIS_FAILURE.md) | P1 | Redis unreachable at startup or runtime |
| [Async Job Queue Failure](RUNBOOK_QUEUE_FAILURE.md) | P2 | Distributed queue fallback, stranded in-flight jobs, or DLQ replay |
| [Stuck Runs](RUNBOOK_STUCK_RUNS.md) | P2 | Flow or agent runs stranded in non-terminal state |
| [Leader Failover](RUNBOOK_LEADER_FAILOVER.md) | P2 | APScheduler leader lost, background jobs paused |
| [WAIT Flow Dead-Letter](RUNBOOK_WAIT_FLOW_DEADLETTER.md) | P3 | Flows waiting indefinitely for events |

## Severity Definitions

| Level | Definition | Response Time |
|-------|------------|---------------|
| P1 | System unavailable or data at risk | Immediate |
| P2 | Degraded functionality, some users affected | Within 1 hour |
| P3 | Background functionality impaired, no user-facing impact | Within 1 business day |

## Environment Variables Referenced

All runbooks use these environment variable placeholders:
- `$API_BASE_URL` — base URL of the AINDY API
- `$REDIS_URL` — Redis connection URL from `REDIS_URL`
- `$DATABASE_URL` — PostgreSQL connection URL from `DATABASE_URL`
- `$ADMIN_TOKEN` — bearer token for an authenticated operator

Additional code-level environment variables may also appear when the implementation uses a separate name, such as `$AINDY_REDIS_URL`.

## Keeping Runbooks Current

When you update code that changes recovery procedures, update the corresponding runbook in the same PR. Update the `last_verified` date in the frontmatter.
