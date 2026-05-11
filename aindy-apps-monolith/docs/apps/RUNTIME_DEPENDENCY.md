---
title: "Runtime Dependency"
last_verified: "2026-05-11"
api_version: "1.0"
status: current
owner: "platform-team"
---
# Runtime Dependency

`aindy-apps-monolith` depends on the separately packaged `aindy-runtime`
distribution.

This repo does not own `AINDY/`, runtime-only entrypoints, or runtime-only
documentation. Those live in the `aindy-runtime` repo and are consumed here as
published contracts.

## Package Contract

Recommended dependency range:

```toml
aindy-runtime>=1.0,<2.0
```

The upper bound is required. The apps repo should not accept unbounded runtime
upgrades.

Validated on `2026-05-11`:

- installed runtime version: `1.0.0`
- apps repo dependency: `aindy-runtime>=1.0,<2.0`
- runtime `/api/version` recommendation: `>=1.0,<2.0`

## Startup Contract

The apps repo owns:

- `aindy_plugins.json`
- `apps.bootstrap`
- app bootstrap ordering and degraded-domain policy

The runtime package owns:

- `aindy-runtime-api`
- `aindy-runtime`
- manifest parsing and profile selection
- plugin loading
- runtime-only boot

Canonical app-profile startup from this repo root:

```bash
aindy-runtime-api
```

Equivalent explicit-manifest form:

```bash
AINDY_APP_PLUGIN_MANIFEST=./aindy_plugins.json aindy-runtime-api
```

## Runtime Docs

When this repo references runtime contracts such as the public API boundary,
runtime-only deployment, DB ownership, or compatibility policy, treat those as
living in the separate `aindy-runtime` repo.
