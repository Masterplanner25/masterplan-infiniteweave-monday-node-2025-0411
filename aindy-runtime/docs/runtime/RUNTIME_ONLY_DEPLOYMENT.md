---
title: Runtime-Only Deployment
last_verified: "2026-05-10"
api_version: "1.0"
status: current
owner: "platform-team"
---
# Runtime-Only Deployment

This is the authoritative contract for running AINDY without loading any
`apps/*` plugins.

Repository ownership:

- this document belongs to the future `aindy-runtime` repo
- the broader documentation split map lives in
  [Runtime Docset Boundary](./RUNTIME_DOCSET_BOUNDARY.md)

Use this mode through one of the supported first-class activation paths:

- `aindy-runtime`
- `python -m AINDY.runtime_only`
- `uvicorn AINDY.runtime_only:app`
- `AINDY_BOOT_MODE=runtime-only`

The runtime-only contract is intentionally narrower than the default monolith
profile. It is supported, but it is not the same thing as `default-apps`.

Configuration precedence is:

1. explicit profile argument passed to registry/bootstrap helpers
2. `AINDY_BOOT_PROFILE`
3. `AINDY_PLUGIN_PROFILE`
4. `AINDY_BOOT_MODE=runtime-only` -> resolves to `platform-only`
5. the selected manifest's `default_profile`

Manifest ownership and selection are separate from profile selection:

- `AINDY/runtime_plugins.json` is the runtime-owned manifest and is the source
  of truth for runtime-only boot.
- repo-root `aindy_plugins.json` is the app-owned manifest in the monolith and
  is the source of truth for app-profile boot.
- `AINDY_PLUGIN_MANIFEST` overrides manifest selection entirely.
- `AINDY_RUNTIME_PLUGIN_MANIFEST` overrides only the runtime manifest path.
- `AINDY_APP_PLUGIN_MANIFEST` overrides only the app manifest path.
- when no explicit profile is requested, the monolith prefers the app manifest
  if present; otherwise startup falls back to the runtime manifest

## Supported Boot Behavior

- The selected boot mode is `runtime-only`.
- The selected boot profile is `platform-only`.
- Startup state reports `boot_mode=runtime-only`.
- `AINDY/runtime_plugins.json` resolves that profile to an empty plugin list.
- Startup remains strict for explicitly requested non-empty profiles.
- No `apps/*` bootstrap module is loaded in runtime-only mode.

This means the future runtime repo can boot on its own as long as it ships the
runtime manifest, even if no app manifest exists beside it.

## Packaged Runtime Use

Canonical install command during the monolith transition:

- `python -m pip install -e .`

Canonical runtime-only entrypoints after installation:

- `aindy-runtime`
- `python -m AINDY.runtime_only`
- `uvicorn AINDY.runtime_only:app`

Canonical generic API entrypoint after installation:

- `aindy-runtime-api`

When a future apps repo depends on the installed runtime, app-profile boot
should either:

- provide `aindy_plugins.json` in the working tree the process starts from, or
- set `AINDY_APP_PLUGIN_MANIFEST=/path/to/aindy_plugins.json`

Runtime-only boot does not depend on that app manifest existing.

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

## Frontend Behavior

Runtime-only mode is presented intentionally in the shipped client shell:

- the authenticated app shell redirects its default entry route to `/memory`
- app-profile navigation such as dashboard, tasks, analytics, growth, and ARM
  pages is hidden
- the remaining authenticated shell presents runtime-safe identity and memory
  surfaces
- admin users still retain the platform console entrypoints, but runtime-only
  navigation omits pages that are still backed by app-domain APIs
- the standalone `/platform` app no longer depends on `identity/boot` just to
  render its operator shell

This means runtime-only mode should appear as a deliberate platform surface,
not as a partially broken monolith UI.

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

Agent enrichment boundary in runtime-only mode:

- planner context baseline: generic runtime prompt with an empty context block
- planner context enrichment: plugin-owned KPI or domain-memory guidance
- suggestions baseline: empty list
- suggestions enrichment: plugin-owned KPI-driven or persisted-loop suggestions
- completion baseline: no-op completion hook
- completion enrichment: plugin-owned post-run orchestration such as Infinity

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
- runtime state reports `boot_mode=runtime-only`
- runtime state reports `boot_profile=platform-only`
- runtime state reports `boot_profile_source=AINDY_BOOT_MODE` when booted through the first-class mode selector
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

- `runtime-only` is the supported operator-facing mode and resolves to the `platform-only` profile.
- `default-apps` is the modular-monolith profile that loads `apps.bootstrap`.
- in the future split, `platform-only` belongs to the runtime repo manifest and
  `default-apps` belongs to the apps repo manifest

Do not infer app behavior from runtime-only success, and do not describe
runtime-only support as if it included the app profile.
