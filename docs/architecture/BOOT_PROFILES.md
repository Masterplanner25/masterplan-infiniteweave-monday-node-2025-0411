---
title: Boot Profiles
last_verified: "2026-05-02"
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
- `AINDY_BOOT_PROFILE` selects a named profile at runtime.
- `AINDY_PLUGIN_PROFILE` is accepted as a backward-compatible alias.
- Legacy manifests using `{"plugins": [...]}` are still supported.
- Empty plugin lists are only accepted when the zero-plugin profile is explicitly selected.
- If a non-empty selected profile references a missing or broken plugin module, startup fails immediately with the profile name and module name in the error.

Ownership boundary:

- `AINDY/platform_layer/registry.py` owns manifest parsing, profile selection, and plugin loading.
- `apps/bootstrap.py` remains an optional plugin target selected by profile, not the runtime's hardcoded boot entrypoint.

Platform-only behavior:

- `create_app()` still mounts runtime-owned routes such as `/health`, `/ready`, `/platform/*`, and runtime primitives under `/apps/*`.
- App-domain routers from `apps/*` are absent because no app plugins are loaded.
- Runtime startup still initializes platform flow definitions and registry-owned surfaces.
- Runtime-owned standalone agent defaults remain available: planner context, memory tool catalog, capability definitions, trigger evaluation, and a no-op completion hook.
- App-owned startup hooks, app-owned syscalls, and app-owned cross-domain flows are unavailable until an app-enabled profile is selected.

Failure semantics:

- `platform-only` is an intentional no-app boot path. Use it when the runtime should start without loading app plugins.
- `default-apps` and any other non-empty profile are strict. Missing `apps.bootstrap`, import errors inside a requested plugin module, and bootstrap exceptions are startup failures.
- If an operator intended a no-app runtime but forgot to select `platform-only`, the startup error now tells them to choose an explicit zero-plugin profile instead of silently continuing.
