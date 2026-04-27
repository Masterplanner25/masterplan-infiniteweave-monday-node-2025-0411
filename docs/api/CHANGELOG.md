---
title: "HTTP REST API Changelog"
last_verified: "2026-04-26"
api_version: "1.0"
status: current
owner: "platform-team"
---
# HTTP REST API Changelog

This document tracks **breaking and additive changes** to the A.I.N.D.Y.
HTTP REST API surface.

For the programmatic syscall ABI, see [docs/syscalls/CHANGELOG.md](../syscalls/CHANGELOG.md).
For implementation internals and sprint history, see
[docs/platform/governance/CHANGELOG.md](../platform/governance/CHANGELOG.md).

## Breaking Change Policy
- **Breaking change**: removing an endpoint, removing a required field, changing a field type, changing an auth requirement, changing a status code for an existing success path, or renaming a path.
- **Additive change**: new endpoint, new optional field, new optional response key.
- Breaking changes require a **major version increment** in `AINDY/version.json`, the `X-API-Version` response header, and `GET /api/version`.
- Clients can detect compatibility risk by calling `GET /api/version` and by watching `X-Version-Warning` when they send `X-Client-Version`.

## How to Detect Breaking Changes
```bash
curl -s http://localhost:8000/api/version | jq '.api_version, .min_client_version, .breaking_change_policy'
```

If the `api_version` major version differs from the version your client was built
against, review this changelog from your version forward.

## Unreleased

Changes merged to `develop` but not yet documented in a tagged API contract release.

*(none)*

---

## [1.0.0] - 2026-04-26

Current stable REST contract consolidated from the pre-1.0 development history
and verified against the live route tree on 2026-04-26.

### Added

- `GET /api/version` - returns `api_version`, `min_client_version`, `breaking_change_policy`, and `changelog_url`.
- `POST /platform/keys`, `GET /platform/keys`, `GET /platform/keys/{key_id}`, `DELETE /platform/keys/{key_id}` - manage platform API keys. The plaintext key is returned only on creation.
- `GET /platform/syscalls` - returns the live platform registry with version, input schema, output schema, stability, and deprecation metadata.
- `POST /agent/runs/{run_id}/recover` - manual recovery endpoint for stuck agent runs. Supports `force=true` as a query parameter.
- `POST /agent/runs/{run_id}/replay` - replays an existing run using its saved plan.
- `POST /masterplans/lock` - locks a synthesized genesis draft into a masterplan.
- `GET /observability/scheduler/status` - scheduler leader status and registered job state, including watchdog scheduling.
- `GET /observability/dead-letter` - lists flow runs that timed out while waiting for resume events. Query params: `limit` (default `50`), `user_id` (optional).
- `GET /observability/dead-letter/{flow_run_id}` - returns a single dead-lettered flow run. Returns `404` when the run is missing or not in `dead_letter` status.
- `GET /observability/rippletrace/status` - returns per-engine RippleTrace circuit-breaker health.
- `POST /masterplans/{plan_id}/activate-cascade` - evaluates task dependencies and activates ready tasks. Response includes `activated`, `count`, and `masterplan_id`.
- Internal worker health probes were added on dedicated worker ports (`GET /health` on 8001, 8002, and 8003). These are process liveness endpoints, not part of the authenticated FastAPI REST surface.

### Changed

- `/agent/runs*` responses now include `flow_run_id` and `replayed_from_run_id` in the serialized run payload.
- All HTTP responses now include `X-API-Version`. Clients that send `X-Client-Version` below the configured minimum may receive `X-Version-Warning`.

### Breaking

- `GET /masterplans/` - response shape changed from a bare JSON list to `{"plans": [...]}`.
  Migration: update clients to read `response.plans` instead of treating the response body as the list itself.

### Deprecated

- Legacy routes exposed without the `/apps` compatibility prefix should be treated as transitional only when `AINDY_ENABLE_LEGACY_SURFACE=true`.
  Migration: move integrations to the documented `/apps/...` or `/platform/...` paths.
  Removal timeline: not yet scheduled; do not build new integrations on the legacy surface.

### Security

- `/platform/*` routes now support scoped machine-to-machine authentication through `X-Platform-Key`. Bearer JWT authentication remains valid for user-driven access. See [getting-started/api-keys.md](../getting-started/api-keys.md).
- JWT authentication is now required for the primary domain application route families under `/apps/tasks/*`, `/apps/leadgen/*`, `/apps/genesis/*`, and `/apps/analytics/*`. Unauthenticated requests now return `401`.
  Migration: add `Authorization: Bearer <token>` to existing integrations.
- Additional application routers, including ARM, RippleTrace, Freelance, Authorship, search/SEO, research results, dashboard, and social, now require JWT authentication.
  Migration: add `Authorization: Bearer <token>` to existing integrations.
- `POST /bridge/nodes`, `GET /bridge/nodes`, and `POST /bridge/link` now require JWT authentication. `POST /bridge/user_event` requires API key authentication.
  Migration: add `Authorization: Bearer <token>` for interactive bridge calls and the configured service API key for `POST /bridge/user_event`.
