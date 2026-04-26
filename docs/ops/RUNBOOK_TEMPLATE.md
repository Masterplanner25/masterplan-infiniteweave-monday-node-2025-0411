---
title: "Runbook: [Incident Name]"
last_verified: "2026-04-25"
api_version: "1.0"
status: current
owner: "platform-team"
severity: P1
---

# Runbook: [Incident Name]

## Severity
**[P1/P2/P3]** — [one sentence on impact]

## Symptoms
What an operator sees when this incident is occurring:
- [Specific error message or log line]
- [Specific metric or health check behavior]
- [User-visible impact]

## Immediate Triage
First 5 minutes: confirm this is the right runbook.

[Specific command to run to confirm]

Expected output if this is the problem:
- [What success looks like]

Expected output if this is not the problem:
- [What points to a different incident]

### This runbook is NOT for
- [Similar-looking failure mode that belongs to another runbook]
- [Second similar-looking failure mode]

## Root Cause
Why this happens. What code path leads to this state.

## Recovery Procedure
Step-by-step. Each step has:
- The exact command to run
- What success looks like
- What to do if the step fails

## Verification
How to confirm the system is healthy after recovery.

[Specific command]

Expected output:
- [What healthy looks like]

## Prevention
What monitoring or alerting should catch this before it becomes an incident.

## Escalation
If recovery fails after the documented attempts, contact `platform-team`.
