---
title: "Model Ownership Policy"
last_verified: "2026-04-26"
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
MemoryTrace, AgentRun, NodusTraceEvent, PlatformAPIKey.

Examples of domain models (must live in apps/X/models.py):
LearningRecord, WatcherSignal, AutonomyDecision.

## Adding a new model

If your model is domain-specific, add it to apps/your_app/models.py and
register it in your app's bootstrap.py via register_models().

If you believe a model is truly platform-owned, add it to
AINDY/db/models/ and get a second review confirming it meets all three
criteria above.
