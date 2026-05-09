---
title: Boot Profiles
last_verified: "2026-05-08"
api_version: "1.0"
status: current
owner: "platform-team"
---

# Boot Profiles

`aindy_plugins.json` is now runtime-owned boot configuration, not just a flat app plugin list.

Current manifest shape:

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

- `default-apps` preserves the existing modular-monolith startup path.
- `platform-only` is the explicit no-app boot profile.
- `AINDY_BOOT_MODE=runtime-only` is the first-class runtime-only selector and resolves to `platform-only`.
- `AINDY_BOOT_PROFILE` selects a named profile at runtime.
- `AINDY_PLUGIN_PROFILE` is accepted as a backward-compatible alias.
- Precedence is: explicit profile argument, `AINDY_BOOT_PROFILE`, `AINDY_PLUGIN_PROFILE`, `AINDY_BOOT_MODE`, then manifest `default_profile`.
- Legacy manifests using `{"plugins": [...]}` are still supported.
- Empty plugin lists are only accepted when the zero-plugin profile is explicitly selected.
- If a non-empty selected profile references a missing or broken plugin module, startup fails immediately with the profile name and module name in the error.

Ownership boundary:

- `AINDY/platform_layer/registry.py` owns manifest parsing, profile selection, and plugin loading.
- `apps/bootstrap.py` remains an optional plugin target selected by profile, not the runtime's hardcoded boot entrypoint.

Platform-only behavior:

- Operators can boot this mode intentionally with `uvicorn AINDY.runtime_only:app` or `AINDY_BOOT_MODE=runtime-only`.
- `create_app()` still mounts runtime-owned routes such as `/health`, `/ready`, `/platform/*`, and runtime primitives under `/apps/*`.
- App-domain routers from `apps/*` are absent because no app plugins are loaded.
- Runtime startup still initializes platform flow definitions and registry-owned surfaces.
- Runtime-owned standalone agent defaults remain available: planner context, memory tool catalog, capability definitions, trigger evaluation, and a no-op completion hook.
- App-owned startup hooks, app-owned syscalls, app-owned cross-domain flows, and `apps/agent` enrichment registrations are unavailable until an app-enabled profile is selected.

For the exact supported runtime-only surface, use
[Runtime-Only Deployment](../runtime/RUNTIME_ONLY_DEPLOYMENT.md) as the
authoritative contract.

`apps/agent` classification:

- `apps/agent` is no longer a core domain.
- The runtime-owned agent API, models, helper syscalls, and default planner/tool behavior live in `AINDY`.
- `apps/agent` now contributes optional enrichment inside `default-apps`: extra tools, async job handlers, capability bundles, KPI-aware planner context, and completion hooks.

Failure semantics:

- `runtime-only` is the supported operator-facing boot mode and maps to the `platform-only` profile.
- `default-apps` and any other non-empty profile are strict at the requested plugin-module boundary. Missing `apps.bootstrap`, import errors inside a requested plugin module, and bootstrap exceptions are startup failures.
- Inside `apps.bootstrap`, only apps marked core abort the startup. Peripheral apps such as `agent` may degrade if their own bootstrap fails.
- If an operator intended a no-app runtime but forgot to select `runtime-only`, the startup error now tells them to choose an explicit zero-plugin path instead of silently continuing.
