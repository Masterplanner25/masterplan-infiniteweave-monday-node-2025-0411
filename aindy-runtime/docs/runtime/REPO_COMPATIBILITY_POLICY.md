---
title: "Repo Compatibility Policy"
last_verified: "2026-05-10"
api_version: "1.0"
status: current
owner: "platform-team"
---
# Repo Compatibility Policy

This document defines the compatibility contract between the future
`aindy-runtime` repo and the future `aindy-apps-monolith` repo.

## Policy

Compatibility is expressed through two layers:

- normal Python package dependency constraints on `aindy-runtime`
- the runtime HTTP/API contract version exposed through `GET /api/version`

The runtime does not attempt active negotiation with the apps repo. The apps
repo declares which runtime versions it supports by pinning or range-bounding
its `aindy-runtime` dependency.

## Required Apps Repo Declaration

The future apps repo should declare `aindy-runtime` using a PEP 440 range with
an explicit upper bound before the next MAJOR release.

Recommended pattern:

```toml
dependencies = [
  "aindy-runtime>=1.0,<2.0",
]
```

Rules:

- use an explicit upper bound at the next runtime MAJOR version
- widening the supported range is an apps-repo release decision
- do not depend on unbounded `>=` requirements for runtime

## Runtime Compatibility Boundary

The runtime publishes compatibility metadata through `GET /api/version`:

- `compatibility.runtime_package.name`
- `compatibility.runtime_package.version`
- `compatibility.apps_repo_contract.declaration_format`
- `compatibility.apps_repo_contract.recommended_runtime_requirement`
- `compatibility.apps_repo_contract.compatible_runtime_major`
- `compatibility.apps_repo_contract.compatible_api_major`
- `compatibility.apps_repo_contract.policy`

This metadata is descriptive, not a handshake protocol. It tells operators and
tooling what range shape the apps repo should declare.

## Version Meaning

- runtime package version:
  the installable `aindy-runtime` package version from packaging metadata
- API version:
  the runtime HTTP/API contract version exposed at `/api/version`

Compatibility expectations:

- runtime package MAJOR changes may break the apps repo dependency contract
- API MAJOR changes may break frontend or app-to-runtime HTTP assumptions
- MINOR and PATCH changes are expected to remain compatible within the same
  MAJOR series unless explicitly documented otherwise

## Operational Guidance

When the runtime repo releases a new version:

1. the apps repo updates its `aindy-runtime` dependency within the supported
   range
2. the apps repo runs its app-profile CI against that runtime version
3. if the apps repo needs newly introduced runtime features, it widens or bumps
   its lower bound deliberately

When the runtime crosses a MAJOR version boundary:

- the runtime must document the breaking change
- the apps repo must update its dependency range explicitly
- compatibility should be treated as opt-in, not assumed
