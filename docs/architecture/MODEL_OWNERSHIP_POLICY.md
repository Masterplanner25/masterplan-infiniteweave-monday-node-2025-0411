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
MemoryTrace, NodusTraceEvent, PlatformAPIKey.

Examples of domain models (must live in apps/X/models.py):
LearningRecord, WatcherSignal, AutonomyDecision.

AgentRun, AgentStep, AgentEvent, AgentTrustSettings — domain models
that were initially placed in AINDY/db/models/ but were migrated to
apps/agent/models/ because they encode agent-domain business logic
(approval gates, trust policy, event timeline) rather than
platform-generic execution concepts.

## Adding a new model

If your model is domain-specific, add it to apps/your_app/models.py and
register it in your app's bootstrap.py via register_models().

If you believe a model is truly platform-owned, add it to
AINDY/db/models/ and get a second review confirming it meets all three
criteria above.

## Migrating a model from AINDY/db/models/ to apps/X/models/

If a model in AINDY/db/models/ is later determined to be domain-specific
(fails criterion 1 or 3 above), migrate it to apps/X/models/ using the
following process:

1. Create apps/X/models/<name>.py with the full class definition.
   Preserve __tablename__ exactly — do not change the database table name.
2. Update apps/X/bootstrap.py to call register_models() for the new module.
3. Remove the model from AINDY/db/model_registry.py direct imports.
4. Replace AINDY/db/models/<name>.py with a __getattr__ lazy shim that
   redirects to the new location for backward compatibility:
       def __getattr__(name: str):
           from apps.X.models import <name_module> as _m
           return getattr(_m, name)
5. Identify all platform-layer files (AINDY/**) that import the model at
   module level. Convert each to a deferred import inside the function body.
6. Once all platform-layer module-level callers are converted, delete the
   shim file.
7. Create a no-op Alembic migration recording the ownership transfer. The
   __tablename__ does not change, so no schema migration is required.

The AgentRun migration (apps/agent/models/) is the canonical reference.
