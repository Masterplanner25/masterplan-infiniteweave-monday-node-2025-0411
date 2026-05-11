---
title: "Database Ownership Contract"
last_verified: "2026-05-10"
api_version: "1.0"
status: current
owner: "platform-team"
---
# Database Ownership Contract

This document defines the runtime-vs-app database ownership boundary for the
future `aindy-runtime` / `aindy-apps-monolith` split.

Ownership note:

- the runtime owns the shared SQLAlchemy infrastructure and the runtime-owned
  ORM model set under `AINDY/db/`
- apps own their domain ORM models and load them into the shared metadata
  through app bootstrap
- the current monolith still uses one Alembic tree, but ownership of revisions
  should now be treated as explicit

## Current Registration Contract

The current model-loading shape is:

1. `AINDY.db.database.Base` defines the shared metadata object.
2. Importing `AINDY.db.model_registry` loads runtime-owned ORM models into that
   metadata.
3. App bootstrap modules call `AINDY.db.model_registry.register_models(...)`
   from each owning app bootstrap file.
4. Those app model imports extend the same `Base.metadata`.

This is the contract the split must preserve:

- runtime-only boot must be able to import runtime models without `apps/`
- app-profile boot may extend the runtime metadata with app-owned tables
- the runtime must not import `apps.*` directly just to know about app models

## Runtime-Owned Models

Runtime-owned SQLAlchemy models live under `AINDY/db/models/` and should move
with `aindy-runtime`.

Model categories:

- identity and platform access:
  `user`, `user_identity`, `api_key`
- agent runtime persistence:
  `agent`, `agent_registry`, `agent_run`, `agent_event`
- execution, waits, and scheduler infrastructure:
  `execution_unit`, `flow_run`, `waiting_flow_run`,
  `background_task_lease`, `job_log`, `event_edge`,
  `nodus_scheduled_job`, `nodus_trace_event`
- memory and observability infrastructure:
  `memory_metrics`, `memory_node_history`, `memory_trace`,
  `memory_trace_node`, `request_metric`, `system_event`,
  `system_health_log`, `system_state_snapshot`
- runtime-managed dynamic platform state:
  `capability`, `dynamic_flow`, `dynamic_node`,
  `webhook_subscription`

Rules:

- new platform/runtime capabilities should add tables under `AINDY/db/models/`
- these models may be used by app code through the public runtime boundary, but
  their ownership remains runtime-side
- compatibility shims under `apps/agent/models/` do not change ownership; the
  canonical agent persistence models are runtime-owned in `AINDY/db/models/`

## App-Owned Models

App-owned SQLAlchemy models stay with `aindy-apps-monolith`. They should not be
moved into runtime just to simplify packaging.

Current app-owned categories include:

- tasks:
  task/task-adjacent planning tables under `apps/tasks/models.py`
- analytics:
  KPI scores, snapshots, calculations, canonical metrics, and learning tables
- masterplan:
  goals, master plans, genesis sessions, and goal-state tables
- automation:
  automation logs, waits, loop state, and related automation-owned tables
- arm:
  ARM analysis, config, and result tables
- search:
  leadgen, research results, and search history tables
- freelance:
  order, client, delivery, refund, and webhook-related tables
- rippletrace:
  ripple, playbook, strategy, pin, and drop tables
- authorship, autonomy, and social:
  their domain-specific tables under the owning app packages

Rules:

- app models should be defined under the owning app package
- the owning app bootstrap module is responsible for importing them
- if app code wants runtime lookup by model symbol, it must publish those
  symbols during app bootstrap

## Model Registration After The Split

The future split should preserve one shared metadata object at runtime:

- `aindy-runtime` provides `AINDY.db.database.Base`,
  `AINDY.db.model_registry`, engine/session helpers, and runtime-owned models
- `aindy-apps-monolith` installs `aindy-runtime` and imports runtime DB
  infrastructure from there
- `apps/bootstrap.py` remains the app-owned entrypoint that imports app models
  and extends `Base.metadata`

This means app registration after the split still looks conceptually like:

```python
from AINDY.db.model_registry import register_models
import apps.tasks.models as tasks_models

register_models(tasks_models.register_models)
```

The important boundary is ownership, not a separate SQLAlchemy base.

## Migration Ownership

Current monolith state:

- one Alembic environment lives under `alembic/`
- `alembic/env.py` imports runtime model registry first, then
  `apps.bootstrap.bootstrap_models()`
- the resulting `Base.metadata` contains both runtime-owned and app-owned
  tables for autogeneration and migration application

Expected split behavior without a migration-system rewrite:

- `aindy-runtime` owns runtime model definitions and the contract for their
  tables
- `aindy-apps-monolith` owns the deployment-specific Alembic tree for the
  combined application database
- runtime schema changes should be consumed by the apps repo as a dependency
  update, then represented in the apps repo's migration history
- app schema changes remain fully owned by the apps repo and land in that same
  Alembic tree

This keeps one migration authority per deployed database while avoiding a
premature multi-repo Alembic split.

## Migration Authoring Rules

Until the repos are fully split:

- continue using the existing `alembic/versions/` tree in the monolith
- when a migration changes only runtime-owned tables, document it as
  runtime-owned in the revision message or review context
- when a migration changes app-owned tables, the owning app remains
  responsible even though the file still lives in the shared Alembic tree
- mixed runtime-plus-app migrations should be treated as temporary debt and
  avoided where practical

## Test Boundary

Runtime-owned tests should be able to:

- import `AINDY.db.model_registry`
- use runtime-owned models and `Base.metadata`
- run without `apps.bootstrap`

App-profile tests should explicitly opt into:

- `apps.bootstrap.bootstrap_models()`
- app-owned tables being present in `Base.metadata`
- app-owned model symbol registration
