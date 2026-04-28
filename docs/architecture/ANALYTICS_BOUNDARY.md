---
title: "Analytics Boundary"
last_verified: "2026-04-27"
api_version: "1.0"
status: current
owner: "platform-team"
---

# Analytics Boundary

## `AINDY/analytics/` — Platform observability

Contains: no live Python source modules at the moment. The directory had only
stale `__pycache__` artifacts and no importers.

Rule: Code here must have no dependency on any domain concept. No user scores,
no KPI logic, no masterplan logic, no task-derived business metrics. It may
only contain domain-agnostic execution metrics, request counts, latency
tracking, infrastructure health, or similar platform observability concerns.
It must not import from `apps/`.

## `apps/analytics/` — Domain analytics

Contains: user KPI snapshots, Infinity scoring, per-user calculations,
score history, adaptive KPI weighting, policy adaptation, ARM-linked scoring,
task/masterplan/social-derived analytics, analytics routes, analytics syscalls,
and analytics public contracts consumed by other apps.

Rule: All user-facing analytics logic belongs here. New analytics features go
in `apps/analytics/services/`.
