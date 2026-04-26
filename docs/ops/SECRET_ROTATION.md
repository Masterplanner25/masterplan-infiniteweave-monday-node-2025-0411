---
title: "Secret Rotation Policy"
last_verified: "2026-04-25"
api_version: "1.0"
status: current
owner: "platform-team"
---

# Secret Rotation Policy

## Secrets Inventory
| Variable Name | What It Protects | Storage Location | Rotation Impact | Minimum Rotation Frequency |
|---|---|---|---|---|
| `SECRET_KEY` | JWT signing key | Deployment env / secret manager | All active JWTs become invalid immediately; all users must log in again | Every 90 days or on suspicion of compromise |
| `AINDY_API_KEY` | Dev bootstrap/service API key | Deployment env; optionally `platform_api_keys` after dev bootstrap | In `verify_api_key()`, env rotation changes service-to-service auth; in `ENV=dev`, restart may create a new admin platform key by hash | Every 90 days or on suspicion of compromise |
| `AINDY_SERVICE_KEY` | `/metrics` bearer auth and service API auth | Deployment env | Callers using the old key receive `403`/`401` after restart | Every 90 days or on suspicion of compromise |
| `OPENAI_API_KEY` | OpenAI provider access | Deployment env / provider console | New outbound OpenAI calls fail until all API instances restart with the new key | Every 90 days or on provider compromise notice |
| `DEEPSEEK_API_KEY` | DeepSeek provider access | Deployment env / provider console | New outbound DeepSeek calls fail until restart with new key | Every 90 days or on provider compromise notice |
| `STRIPE_SECRET_KEY` | Stripe payment API access | Deployment env / Stripe dashboard | Payment operations fail until restart with the new key | Every 90 days or on provider compromise notice |
| `DATABASE_URL` | PostgreSQL credentials and host | Deployment env / secret manager | API and worker DB connectivity switches on process restart; old pooled connections remain on old creds until restart | Every 90 days or on DB credential compromise |
| `REDIS_URL` | Redis credentials and host | Deployment env / secret manager | Redis-backed cache, queue, heartbeat, and event bus use the new creds only after restart | Every 90 days or on Redis credential compromise |

## SECRET_KEY Rotation (High Impact)

### What Breaks on Rotation
`create_access_token()` signs JWTs with one in-process `SECRET_KEY`. `decode_access_token()` verifies with that same single key and returns `401 "Invalid or expired token"` on signature failure. After rotation, every JWT signed with the old key stops verifying, and users are forced to re-authenticate. Token lifetime is 24 hours, but rotation invalidates tokens immediately.

### Rotation Procedure
1. Generate a new key.
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```
2. Schedule a maintenance window or accept a forced logout of all users. There is no dual-key transition in the current implementation.
3. Update `SECRET_KEY` in the deployment environment.
4. Restart all API instances. The startup validators require at least 32 characters outside test/development, and production also rejects the default placeholder with:
```text
SECRET_KEY is using the insecure default placeholder. Set a strong SECRET_KEY in your .env before running in non-development deployments.
```
5. Verify new login works.
```bash
curl -X POST http://localhost:8000/auth/login -H "Content-Type: application/json" -d '{"email":"admin@example.com","password":"your-password"}'
```
6. Confirm an old JWT is rejected.
```bash
curl http://localhost:8000/platform/keys -H "Authorization: Bearer OLD_TOKEN"
```
Expected result: HTTP `401`.

### Why No Zero-Downtime Rotation Currently Exists
The current implementation accepts exactly one signing key. Zero-downtime rotation would require either a grace period where both old and new keys are accepted or a token refresh design that replaces tokens before the old key is removed. Neither exists today. Rotating `SECRET_KEY` is therefore a forced logout event.

## Platform API Key Rotation (Low Impact)

### How Platform Keys Work
Platform API keys are generated once, hashed with `hash_key()`, and stored in `platform_api_keys` as `key_hash`; only `key_prefix` is stored in plaintext. The raw key is returned only by `POST /platform/keys` and cannot be recovered later. Rotation means creating a new key, updating callers, then revoking the old key.

### Rotation Procedure
1. Create a new key.
```bash
curl -X POST http://localhost:8000/platform/keys \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{"name":"rotated-key","scopes":["platform.admin"]}'
```
2. Record the raw `key` from the response immediately. It is shown once only.
3. Update the caller to use the new key in `X-Platform-Key`.
4. Verify the new key works.
```bash
curl http://localhost:8000/health -H "X-Platform-Key: aindy_new_key"
```
5. Revoke the old key.
```bash
curl -X DELETE http://localhost:8000/platform/keys/$OLD_KEY_ID \
  -H "Authorization: Bearer $JWT"
```

### AINDY_API_KEY Special Case
`AINDY_API_KEY` is also used by `_ensure_dev_api_key()` in `ENV=dev`. On startup, if it is set and its hash is not already present, the app creates a `platform.admin` key and may create or elevate a dev user. Rotation procedure: update `AINDY_API_KEY`, restart the dev server, verify the new hash exists, then remove the old DB-backed dev key if needed. The bootstrap is idempotent because it checks by hash first.

## External Provider Key Rotation (Medium Impact)

### Rotation Procedure (applies to OPENAI_API_KEY, DEEPSEEK_API_KEY)
1. Generate a new provider key in the OpenAI or DeepSeek console.
2. Update the environment variable in the deployment environment.
3. Restart API instances. The settings object is loaded at process start; keys are not hot-reloaded.
4. Verify with a small AI-backed request.
5. Revoke the old provider key only after the new key is confirmed working.

In production, `main.py` logs this warning when the OpenAI key uses a project-key prefix:
```text
OPENAI_API_KEY uses the project-key prefix in production; verify rotation after any potential exposure.
```

### Zero-Downtime Pattern (if required)
Hot key reload is not implemented. The only zero-downtime-safe pattern available today is a rolling restart where the new key is deployed to instances before the old provider key is revoked.

## Database Credential Rotation

### Rotation Procedure
1. Create a new PostgreSQL user/password in your database provider.
2. Update `DATABASE_URL` in the deployment environment.
3. Restart all API and worker processes. `AINDY/db/database.py` reads `DATABASE_URL` at process start and builds the pool from that value.
4. Verify connectivity.
```bash
curl http://localhost:8000/health
```
5. Drop the old DB user after the new credentials are confirmed.

For Redis credentials in `REDIS_URL`, follow the same sequence: create new credentials, update the env var, restart API and workers, verify `/health`, then revoke the old credentials.

## Rotation Audit Log
Rotation events are not automatically recorded by the application. `SystemEvent` covers application activity, not infrastructure secret changes. Maintain a manual log:

| Date | Secret | Reason | Engineer | Notes |
|------|--------|--------|----------|-------|
| YYYY-MM-DD | SECRET_KEY | Quarterly rotation | [name] | Forced logout at HH:MM UTC |

## References
- [AINDY/config.py](/C:/dev/masterplan-infiniteweave-monday-node-2025-0411/AINDY/config.py:1)
- [docs/ops/RUNBOOK.md](/C:/dev/masterplan-infiniteweave-monday-node-2025-0411/docs/ops/RUNBOOK.md:1)
- [docs/platform/engineering/TECH_DEBT.md](/C:/dev/masterplan-infiniteweave-monday-node-2025-0411/docs/platform/engineering/TECH_DEBT.md:1)
