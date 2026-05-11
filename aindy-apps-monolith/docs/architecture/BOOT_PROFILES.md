---
title: Boot Profiles
last_verified: "2026-05-10"
api_version: "1.0"
status: current
owner: "platform-team"
---

# Boot Profiles

Ownership note:

- this document is currently shared because it explains both runtime-owned and
  app-owned boot semantics
- runtime-only operating details now live in the separate `aindy-runtime` repo
- the apps-side dependency boundary is documented in
  [Runtime Dependency](../apps/RUNTIME_DEPENDENCY.md)

Boot configuration is now split by ownership:

- `AINDY/runtime_plugins.json` is the runtime-owned manifest.
- `aindy_plugins.json` at repo root is the app-owned/monolith manifest.

Current runtime manifest shape:

```json
{
  "default_profile": "platform-only",
  "profiles": {
    "platform-only": {
      "plugins": []
    }
  }
}
```

Current app manifest shape:

```json
{
  "default_profile": "default-apps",
  "profiles": {
    "platform-only": {
      "plugins": []
    },
    "default-apps": {
      "plugins": [
        "apps.bootstrap"
      ]
    }
  }
}
```

Rules:

- The runtime manifest owns runtime-only boot and must ship with the future runtime repo.
- The app manifest owns app-profile boot and must ship with the future apps repo.
- `default-apps` preserves the existing modular-monolith startup path.
- `platform-only` is the explicit no-app boot profile.
- `AINDY_BOOT_MODE=runtime-only` is the first-class runtime-only selector and resolves to `platform-only`.
- `AINDY_BOOT_PROFILE` selects a named profile at runtime.
- `AINDY_PLUGIN_PROFILE` is accepted as a backward-compatible alias.
- `AINDY_PLUGIN_MANIFEST` overrides manifest selection entirely.
- `AINDY_RUNTIME_PLUGIN_MANIFEST` overrides only the runtime-owned manifest path.
- `AINDY_APP_PLUGIN_MANIFEST` overrides only the app-owned manifest path.
- Profile selection precedence is: explicit profile argument, `AINDY_BOOT_PROFILE`, `AINDY_PLUGIN_PROFILE`, `AINDY_BOOT_MODE`, then the selected manifest's `default_profile`.
- Manifest selection precedence is:
  1. explicit manifest path argument
  2. `AINDY_PLUGIN_MANIFEST`
  3. if the requested profile is `platform-only`, use the runtime manifest
  4. if a non-runtime profile is explicitly requested, use the app manifest
  5. with no explicit profile, use the app manifest if present, otherwise use the runtime manifest
- Legacy manifests using `{"plugins": [...]}` are still supported.
- Zero-plugin manifests are valid for the runtime-owned `platform-only` profile.
- Zero-plugin app manifests are only accepted when the selected profile is explicitly intended to be empty.
- If a non-empty selected profile references a missing or broken plugin module, startup fails immediately with the profile name and module name in the error.

Ownership boundary:

- `AINDY/platform_layer/registry.py` owns manifest parsing, profile selection, and plugin loading.
- `apps/bootstrap.py` is app-owned and remains an optional plugin target selected by the app manifest, not a module owned or hardcoded by the runtime package.
- In the future split:
  - the runtime repo should carry `AINDY/runtime_plugins.json`
  - the apps repo should carry its own `aindy_plugins.json` (or supply `AINDY_APP_PLUGIN_MANIFEST`)
  - runtime-only boot must not depend on the apps manifest existing at all
- the concrete apps-repo landing zone is documented in
  [Apps Monolith Repo Shape](../apps/APPS_MONOLITH_REPO_SHAPE.md)

Platform-only behavior:

- Operators can boot this mode intentionally with `aindy-runtime`, `python -m AINDY.runtime_only`, `uvicorn AINDY.runtime_only:app`, or `AINDY_BOOT_MODE=runtime-only`.
- `create_app()` still mounts runtime-owned routes such as `/health`, `/ready`, `/platform/*`, and runtime primitives under `/apps/*`.
- App-domain routers from `apps/*` are absent because no app plugins are loaded.
- Runtime startup still initializes platform flow definitions and registry-owned surfaces.
- Runtime-owned standalone agent defaults remain available: planner context, memory tool catalog, capability definitions, trigger evaluation, and a no-op completion hook.
- App-owned startup hooks, app-owned syscalls, app-owned cross-domain flows, and `apps/agent` enrichment registrations are unavailable until an app-enabled profile is selected.
- For an installed runtime dependency, the default app-manifest lookup starts
  from the current working directory and walks upward before falling back to
  the monolith source-tree default.

For the exact supported runtime-only surface, use the runtime repo's
`RUNTIME_ONLY_DEPLOYMENT.md` as the authoritative contract.

For the future app-profile repo shape, use
[Apps Monolith Repo Shape](../apps/APPS_MONOLITH_REPO_SHAPE.md) as the
authoritative planning document.

`apps/agent` classification:

- `apps/agent` is no longer a core domain.
- The runtime-owned agent API, models, helper syscalls, and default planner/tool behavior live in `AINDY`.
- `apps/agent` now contributes optional enrichment inside `default-apps`: extra tools, async job handlers, capability bundles, KPI-aware planner context, and completion hooks.

Failure semantics:

- `runtime-only` is the supported operator-facing boot mode and maps to the `platform-only` profile.
- Missing runtime manifests or missing app manifests are startup failures when that manifest was explicitly selected by mode, profile, or manifest override.
- `default-apps` and any other non-empty profile are strict at the requested plugin-module boundary. Missing `apps.bootstrap`, import errors inside a requested plugin module, and bootstrap exceptions are startup failures.
- Inside `apps.bootstrap`, only apps marked core abort the startup. Peripheral apps such as `agent` may degrade if their own bootstrap fails.
- If an operator intended a no-app runtime but forgot to select `runtime-only`, the startup error now tells them to choose an explicit zero-plugin path instead of silently continuing.
