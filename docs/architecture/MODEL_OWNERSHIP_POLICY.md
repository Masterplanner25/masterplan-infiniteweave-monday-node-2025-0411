---
title: "Model Ownership Policy"
last_verified: "2026-04-29"
api_version: "1.0"
status: current
owner: "platform-team"
---

# Model Ownership Policy

## Rule

A SQLAlchemy model belongs in AINDY/db/models/ if and only if it meets
ALL of the following criteria:

1. It represents a concept that is platform-wide, not domain-specific.
2. It is imported or referenced by more than one domain app, OR it is
   referenced directly by AINDY/ platform code (pipeline, startup,
   scheduler, auth).
3. It does not encode business logic belonging to a single domain.

Examples of platform models: User, FlowRun, ExecutionUnit, SystemEvent,
MemoryTrace, NodusTraceEvent, PlatformAPIKey, AgentRun, AgentStep,
AgentEvent, AgentTrustSettings.

Examples of domain models (must live in apps/X/models.py):
LearningRecord, WatcherSignal, AutonomyDecision.

Agent route handlers, flows, syscalls, and tool registration remain
domain behavior under `apps/agent/`, but the persistence types
`AgentRun`, `AgentStep`, `AgentEvent`, and `AgentTrustSettings` are
runtime-owned because they are referenced directly by runtime execution,
recovery, observability, and capability enforcement code in `AINDY/`.

## Adding a new model

If your model is domain-specific, add it to apps/your_app/models.py and
register it in your app's bootstrap.py via register_models().

If you believe a model is truly platform-owned, add it to
AINDY/db/models/ and get a second review confirming it meets all three
criteria above.

## Migrating a model between ownership layers

If a model in `AINDY/db/models/` is later determined to be domain-specific,
or a model in `apps/X/models/` is later determined to be runtime-owned,
migrate ownership deliberately using the following process:

1. Move the full class definition to the new owner package.
   Preserve `__tablename__` exactly unless a schema migration is intentional.
2. Update model registration so Alembic and startup load the canonical owner.
3. Update all `AINDY/`, app, and test imports to depend on the new owner.
4. If compatibility is needed during the transition, leave a narrow shim in
   the old location that re-exports the canonical class.
5. Add or update CI enforcement so the old forbidden import direction fails.
6. If table shape is unchanged, record the ownership transfer without a schema
   migration. Only add Alembic changes when the database schema actually changes.

The agent persistence move back into `AINDY/db/models/` is the canonical
runtime-ownership reference.
