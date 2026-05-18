# Archive Status

This repository is archived as historical reference.

It is not the primary active development or deployment repo.

Use the extracted repos instead:

- `C:\dev\aindy-runtime`
  - runtime code under `AINDY/`
  - runtime packaging, entrypoints, runtime-only deployment docs, runtime CI
- `C:\dev\aindy-apps-monolith`
  - `apps/`, `client/`, `aindy_plugins.json`, `alembic/`, app-profile docs and tests

Use this archive for:

- historical split context
- monolith-era implementation reference
- migration comparison against the extracted repos
- older docs, runbooks, and design notes that remain useful as background material

Do not treat this repo as the operational source of truth for:

- runtime-only deployment
- app-profile deployment
- runtime packaging or release flow
- app manifest ownership
- Alembic ownership for the extracted apps repo
- GitHub Actions ownership or release-gating decisions for the extracted repos

Current operational routing:

1. Runtime work:
   use `C:\dev\aindy-runtime`
2. App/profile work:
   use `C:\dev\aindy-apps-monolith`
3. Historical comparison only:
   use this archive

CI note:

- `.github/workflows/ci.yml` and `.github/workflows/runtime-ci.yml` in this
  archive are historical combined-repo workflows
- they are useful for comparison only
- authoritative CI ownership now lives in:
  - `C:\dev\aindy-runtime\docs\runtime\CI_OWNERSHIP.md`
  - `C:\dev\aindy-apps-monolith\docs\apps\CI_OWNERSHIP.md`
