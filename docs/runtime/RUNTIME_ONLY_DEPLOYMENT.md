---
title: Runtime-Only Deployment
last_verified: "2026-05-08"
api_version: "1.0"
status: current
owner: "platform-team"
---
# Runtime-Only Deployment

This is the authoritative contract for running AINDY without loading any
`apps/*` plugins.

Use this mode only through the explicit boot profile:

- `AINDY_BOOT_PROFILE=platform-only`

The runtime-only contract is intentionally narrower than the default monolith
profile. It is supported, but it is not the same thing as `default-apps`.

## Supported Boot Behavior

- The selected boot profile is `platform-only`.
- `aindy_plugins.json` resolves that profile to an empty plugin list.
- Startup remains strict for explicitly requested non-empty profiles.
- No `apps/*` bootstrap module is loaded in runtime-only mode.

## Mounted Route Surface

Runtime-only mode still mounts runtime-owned HTTP surfaces:

- `GET /health`
- `GET /ready`
- `GET /platform/*`
- `POST /apps/agent/run`
- `GET /apps/agent/tools`
- `GET /apps/agent/trust`
- `GET /apps/agent/suggestions`
- `POST /apps/memory/recall`
- `GET /apps/memory/nodes`
- other runtime-owned `/apps/memory/*` and `/apps/coordination/*` routes

What does not mount:

- app routers contributed by `apps/*` bootstrap registration such as
  `/apps/tasks/*` or `/apps/social/*`

## Baseline Agent Capability

The runtime agent layer stays available in platform-only mode with the generic
baseline only:

- generic planner prompt
- runtime-owned `memory.recall`
- runtime-owned `memory.write`
- default trigger evaluator
- runtime capability definitions: `execute_flow`, `read_memory`, `write_memory`
- no-op completion hook
- empty tool suggestions unless a plugin registers a suggestion provider

This baseline is domain-agnostic by design. KPI enrichment, Infinity behavior,
and app-owned tools are not part of the runtime-only contract.

## Memory And Tool Availability

Supported tool catalog:

- `memory.recall`
- `memory.write`

These tools dispatch directly to runtime/kernel-owned memory syscalls with
explicit capabilities:

- `sys.v1.memory.read`
- `sys.v1.memory.write`

Unsupported app-owned tools fail predictably because they are not registered.
For example, `task.create` returns a normal tool-registry error instead of
silently proxying into an app layer.

## Health And Readiness

- `/health` is present in runtime-only mode.
- `/ready` is present in runtime-only mode.
- runtime state reports `boot_profile=platform-only`
- runtime state reports `app_plugins_loaded=false`
- runtime state reports `app_plugin_count=0`

Health and readiness still honor the broader deployment contract for required
infrastructure such as PostgreSQL, Redis, worker mode, schema enforcement, and
event-bus requirements. Runtime-only means “no app plugins loaded”, not “skip
platform safety checks”.

## Intentionally Unavailable Without Apps

These are outside the supported runtime-only contract:

- app-domain routers from `apps/*`
- app-owned agent tools beyond the runtime memory baseline
- app-owned planner enrichment and suggestion providers
- app-owned completion hooks and Infinity orchestration
- app-owned syscalls and startup hooks
- app-owned cross-domain flows registered only through app bootstrap

## Profile Boundary

`platform-only` and `default-apps` are distinct supported modes:

- `platform-only` is the clean runtime baseline with no app plugins.
- `default-apps` is the modular-monolith profile that loads `apps.bootstrap`.

Do not infer app behavior from runtime-only success, and do not describe
runtime-only support as if it included the app profile.
