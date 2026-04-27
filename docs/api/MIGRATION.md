---
title: "HTTP API Migration Guide"
last_verified: "2026-04-26"
status: current
owner: "platform-team"
---
# HTTP API Migration Guide

## 0.x -> 1.0.0

### Step 1: Add version checks

Call `GET /api/version` during startup or deploy verification:

```bash
curl http://your-host/api/version
```

The response includes:
- `api_version`
- `min_client_version`
- `breaking_change_policy`

If your client sends `X-Client-Version`, watch for `X-Version-Warning` in responses.

### Step 2: Add JWT authentication where public access no longer exists

The authenticated application route families now require Bearer JWT credentials.
At minimum, review integrations that call:

- `/apps/tasks/*`
- `/apps/leadgen/*`
- `/apps/genesis/*`
- `/apps/analytics/*`
- `/apps/arm/*`
- `/apps/rippletrace/*`
- `/apps/freelance/*`

Example:

```bash
curl http://your-host/apps/tasks/ \
  -H "Authorization: Bearer $JWT"
```

For bridge routes:
- `POST /bridge/nodes`, `GET /bridge/nodes`, and `POST /bridge/link` require Bearer JWT
- `POST /bridge/user_event` requires API key authentication

### Step 3: Add `X-Platform-Key` support for `/platform/*` machine clients

If your integration already uses a Bearer JWT, no change is required.
If you need scoped machine-to-machine access, create a platform API key:

```bash
curl -X POST http://your-host/platform/keys \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{"name":"my-integration","scopes":["memory.read","flow.execute"]}'
```

Use the returned key in `X-Platform-Key` on subsequent `/platform/*` calls:

```bash
curl http://your-host/platform/syscalls \
  -H "X-Platform-Key: aindy_your_key"
```

### Step 4: Update `GET /masterplans/` response parsing

The masterplan list response changed from a raw list to an object wrapper:

```json
{"plans": [...]}
```

Update clients to read `response.plans`.

### Step 5: Adopt new recovery and observability endpoints where useful

The following endpoints are available in `1.0.0` and are safe additions for
operators and integrators:

- `POST /agent/runs/{run_id}/recover`
- `POST /agent/runs/{run_id}/replay`
- `GET /observability/scheduler/status`
- `GET /observability/dead-letter`
- `GET /observability/dead-letter/{flow_run_id}`
- `GET /observability/rippletrace/status`
- `POST /masterplans/{plan_id}/activate-cascade`
