---
title: "Client Ownership"
last_verified: "2026-05-10"
api_version: "1.0"
status: current
owner: "platform-team"
---
# Client Ownership

The current `client/` tree belongs to the future `aindy-apps-monolith` repo.

That is a deliberate product decision, not an accident of the current
monolith.

## Decision

Keep `client/` with `aindy-apps-monolith` for now.

Why:

- the current frontend is one mixed React/Vite SPA
- it contains app-profile navigation, app-domain pages, auth flows, and runtime
  mode awareness in the same shell
- runtime-only mode is supported, but the UI is still an apps-hosted shell
  consuming runtime APIs rather than a separately deployable runtime console

## What This Means

After the split, the apps repo should own:

- `client/`
- frontend tests under `client/src/test/` and `client/e2e/`
- app-shell routing and auth flows
- runtime-only UI behavior that adapts to runtime boot state through API data

The runtime repo should own:

- the HTTP/API surfaces the client reads
- the runtime mode/version metadata exposed by `/api/version` and
  `/apps/identity/boot`
- the backend compatibility and startup contracts those UI flows consume

## Runtime-Only UI Interpretation

Runtime-only mode does not make the client a runtime product.

Current interpretation:

- the apps-hosted SPA detects runtime-only boot from runtime API metadata
- the SPA hides app-profile navigation and redirects app-profile routes away
- the SPA still ships as part of the broader monolith/app frontend

That is sufficient for the repo split. It is not a commitment to publish the
same frontend as the runtime repo's own console.

## What Would Need To Change Later

If a separate runtime frontend becomes desirable later, that should be treated
as a new product boundary and not bundled into the current repo split.

That future step would require at least:

- a runtime-owned frontend entrypoint or separate SPA package
- a reduced route map containing only runtime-owned surfaces
- a distinct release and deployment story from the apps SPA
- explicit UI/API contracts for runtime-only administration and observability
- a decision on whether shared components remain duplicated, shared, or moved
  to a separate package

Until then, `client/` remains app-owned.
