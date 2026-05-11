---
title: "Apps Monolith Repo Shape"
last_verified: "2026-05-10"
api_version: "1.0"
status: current
owner: "platform-team"
---
# Apps Monolith Repo Shape

This document defines the target structure for the future
`aindy-apps-monolith` repo while the current combined repo still exists.

The goal is not to split individual apps into separate packages. The goal is
to move the existing `apps/` monolith into its own repo that depends on the
installed `aindy-runtime` package.

## Target Repo Layout

Proposed top-level shape:

```text
aindy-apps-monolith/
  apps/
    bootstrap.py
    _bootstrap_validator.py
    _adapters.py
    agent/
    analytics/
    arm/
    authorship/
    automation/
    autonomy/
    bridge/
    dashboard/
    freelance/
    identity/
    masterplan/
    network_bridge/
    rippletrace/
    search/
    social/
    tasks/
  tests/
    fixtures/
    helpers/
    unit/
    integration/
    system/
    api/
  client/
  alembic/
  docs/
    apps/
    architecture/
    platform/
  aindy_plugins.json
  pyproject.toml
  pytest.ini
  alembic.ini
```

Keep the apps repo as one Python project with one `apps/` package. Do not
introduce per-domain packaging boundaries as part of the runtime split.

## Runtime Dependency Contract

The future apps repo should depend on installed `aindy-runtime`, not on a
sibling checkout of `AINDY/`.

Expected dependency shape:

- `aindy-runtime` is installed through normal Python packaging
- app code imports only the runtime modules allowed by
  [Runtime Public API Contract](../runtime/PUBLIC_API_CONTRACT.md)
- anything else under `AINDY.*` remains internal runtime implementation unless
  explicitly documented as transitional

The apps repo should not vendor runtime code under its own tree once the split
is complete.

## App Manifest Ownership

The apps repo owns `aindy_plugins.json`.

Expected manifest contents:

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

Ownership rules:

- `apps.bootstrap` remains the top-level app plugin entrypoint
- the apps repo may add more top-level plugins later, but the default split
  assumes one app bootstrap aggregator
- the runtime package may discover this manifest from the current working tree
  or from `AINDY_APP_PLUGIN_MANIFEST`

## App Bootstrap Expectations

`apps/bootstrap.py` moves with the apps repo and remains responsible for:

- resolving app bootstrap order
- loading app bootstrap modules
- publishing degraded-domain state through runtime-owned registry calls
- exposing `bootstrap()` and `bootstrap_models()` as the app-side integration
  entrypoints expected by the runtime

The runtime package remains responsible for:

- selecting the manifest and active profile
- importing the requested plugin module
- enforcing strict startup failure for missing or broken requested plugins

So the future boot contract is:

1. runtime entrypoint starts
2. runtime selects the app manifest when an app profile is requested
3. runtime imports the plugin module named by that manifest, typically `apps.bootstrap`
4. `apps.bootstrap.bootstrap()` registers app-owned routes, flows, jobs,
   syscalls, startup hooks, and enrichments

## App Entrypoint Expectations

The apps repo does not need to replace the runtime server entrypoints. It needs
to provide configuration and manifests that make the installed runtime boot the
app profile cleanly.

Canonical app-profile startup patterns after the split:

- `aindy-runtime-api`
  with the process started from the apps repo root so `aindy_plugins.json` is
  discoverable
- `AINDY_APP_PLUGIN_MANIFEST=/abs/path/to/aindy_plugins.json aindy-runtime-api`
- `uvicorn AINDY.main:app`
  with `aindy-runtime` installed and the working directory rooted in the apps
  repo

The apps repo does not own `aindy-runtime` or `aindy-runtime-api`; it owns the
manifest and plugin modules those runtime entrypoints load.

## What Moves To The Apps Repo

Move with `aindy-apps-monolith`:

- `apps/`
- `client/`
- repo-root `aindy_plugins.json`
- app-profile tests under `tests/` that require `apps.bootstrap`, app fixtures,
  or app-owned routes and enrichments
- app docs under `docs/apps/`
- shared docs that are more app-facing than runtime-facing once split
- app migrations and app-owned schema evolution assets that still belong to the
  monolith deployment

In the current combined repo, this at least includes:

- `apps/bootstrap.py`
- `client/src/App.jsx`
- `client/src/components/shared/AppShell.jsx`
- `client/src/context/SystemContext.jsx`
- `client/src/api/version.ts`
- all app domain packages under `apps/*`
- `tests/helpers/bootstrap.py`
- `tests/fixtures/client.py`
- app-profile tests such as `test_bootstrap_completeness.py`,
  `test_runtime_agent_api_ownership.py`, app-profile cases in
  `test_plugin_profiles.py`, and app-profile enrichment tests

## What Stays Runtime-Owned

Stay in `aindy-runtime`:

- `AINDY/`
- runtime manifests under `AINDY/`
- runtime-only entrypoints and packaging
- runtime CI and runtime-only tests
- runtime public API contract docs

The apps repo should consume these as dependencies and contracts, not move or
duplicate them.

## Test Ownership After Split

App-owned tests:

- tests that require `apps.bootstrap`
- tests using `client` / `app` fixtures from `tests/fixtures/client.py`
- tests that validate app-owned routes, jobs, syscalls, flow registration, KPI
  enrichment, or degraded app boot behavior

Runtime-owned tests:

- tests marked `runtime_only`
- package-install smoke tests for `aindy-runtime`
- runtime startup, runtime-only boot, runtime public API contract shape, and
  runtime version surface checks

The current monolith should keep both sets until extraction, but the ownership
boundary should now be treated as explicit.

## Current Monolith Compatibility

Nothing in this document changes the current combined repo boot shape:

- app-profile boot still works through repo-root `aindy_plugins.json`
- runtime-only boot still works through `AINDY/runtime_plugins.json`
- tests may still run in one repo

This document only defines the target landing zone for the future apps repo so
the extraction path is concrete rather than implied.

For the explicit frontend ownership decision, use
[Client Ownership](./CLIENT_OWNERSHIP.md).
