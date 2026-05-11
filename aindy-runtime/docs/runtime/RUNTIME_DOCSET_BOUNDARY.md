---
title: "Runtime Docset Boundary"
last_verified: "2026-05-10"
api_version: "1.0"
status: current
owner: "platform-team"
---
# Runtime Docset Boundary

This document defines the documentation boundary for the future
`aindy-runtime` and `aindy-apps-monolith` repo split.

Use it as the ownership map for the current combined repo:

- docs listed under **Move To `aindy-runtime`** should travel with the runtime
  repo and avoid app-monolith assumptions
- docs listed under **Move To `aindy-apps-monolith`** are app-owned and should
  not be treated as runtime contracts
- docs listed under **Shared Or Split Later** are still useful in the monolith
  but either span both repos or need a later editorial split

The runtime-only operating contract remains
[Runtime-Only Deployment](./RUNTIME_ONLY_DEPLOYMENT.md).

## Move To `aindy-runtime`

These docs describe runtime-owned behavior, public contracts, or deployment
surfaces that must stand on their own with no `apps/` tree present.

- [RUNTIME_ONLY_DEPLOYMENT.md](./RUNTIME_ONLY_DEPLOYMENT.md)
- [AGENT_RUNTIME.md](./AGENT_RUNTIME.md)
- [SYSCALL_SYSTEM.md](./SYSCALL_SYSTEM.md)
- [PUBLIC_API_CONTRACT.md](./PUBLIC_API_CONTRACT.md)
- [DB_OWNERSHIP_CONTRACT.md](./DB_OWNERSHIP_CONTRACT.md)
- [REPO_COMPATIBILITY_POLICY.md](./REPO_COMPATIBILITY_POLICY.md)
- [EXECUTION_CONTRACT.md](./EXECUTION_CONTRACT.md)
- [OS_ISOLATION_LAYER.md](./OS_ISOLATION_LAYER.md)
- [MEMORY_ADDRESS_SPACE.md](./MEMORY_ADDRESS_SPACE.md)
- [RUNTIME_BEHAVIOR.md](./RUNTIME_BEHAVIOR.md)

Runtime-repo rule:
- these docs may describe optional plugin enrichment, but their normative
  contracts must remain valid when no app plugin is installed

## Move To `aindy-apps-monolith`

These docs describe app-domain features, enrichment behavior, or monolith-only
user-facing capabilities.

- [../apps/APPS_MONOLITH_REPO_SHAPE.md](../apps/APPS_MONOLITH_REPO_SHAPE.md)
- [../apps/CLIENT_OWNERSHIP.md](../apps/CLIENT_OWNERSHIP.md)
- [../apps/AGENTICS.md](../apps/AGENTICS.md)
- `docs/apps/*` domain guides such as analytics, freelancing, rippletrace, and
  other app feature docs
- app route and app service behavior currently cataloged under monolith-facing
  API and architecture references

Apps-repo rule:
- app docs may depend on runtime contracts, but must not redefine runtime
  ownership or imply that app bootstrap is part of the runtime baseline

## Shared Or Split Later

These docs are still useful in the combined repo, but they span both runtime
and app concerns and should either remain duplicated intentionally or be split
later into runtime-owned and app-owned companions.

- [../architecture/BOOT_PROFILES.md](../architecture/BOOT_PROFILES.md)
- [../architecture/ARCHITECTURE_MAP.md](../architecture/ARCHITECTURE_MAP.md)
- [../architecture/PLUGIN_REGISTRY_PATTERN.md](../architecture/PLUGIN_REGISTRY_PATTERN.md)
- [../platform/interfaces/API_CONTRACTS.md](../platform/interfaces/API_CONTRACTS.md)

Split guidance:
- `BOOT_PROFILES.md` is shared until both repos have their own startup docs;
  after the split, runtime-only boot guidance should live in the runtime repo
  and app-profile boot guidance should live in the apps repo
- `ARCHITECTURE_MAP.md` currently explains both `AINDY/` and `apps/`; it
  should later become separate runtime and apps architecture maps
- `PLUGIN_REGISTRY_PATTERN.md` describes the registration contract between the
  two repos and may remain shared conceptually, but examples should avoid
  implying one repo-root manifest
- `API_CONTRACTS.md` is currently a monolith HTTP inventory; the runtime repo
  should eventually carry only runtime-owned routes and interfaces, while the
  apps repo carries app-route inventories

## Current Boundary Notes

- Runtime-owned `/apps/*` routes are still runtime docs, not app docs. Current
  examples include the agent, memory, watcher, and coordination surfaces under
  `AINDY.routes.*`.
- App-owned `/apps/*` routes remain app docs even though they share the `/apps`
  URL prefix.
- Runtime docs may reference app-profile behavior only to explain what is
  intentionally unavailable without plugins.
- App docs should reference runtime contracts instead of copying runtime rules.
