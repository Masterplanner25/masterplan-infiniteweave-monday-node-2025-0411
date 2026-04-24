# SECRET_KEY Rotation Runbook

## When to rotate SECRET_KEY
- Suspected compromise of the signing key.
- Regular rotation schedule: at least every 90 days.

## How to rotate SECRET_KEY (global — invalidates all active sessions)
1. Generate a new key:
   ```bash
   python3 -c "import secrets; print(secrets.token_hex(32))"
   ```
2. Update `SECRET_KEY` in `AINDY/.env`. Do not commit this file.
3. Restart all API instances. Existing JWTs signed with the old key will fail validation on the next request.
4. Notify users: `You have been logged out. Please log in again.`
   The frontend should handle `401` responses by redirecting to `/login`.

## How to invalidate a single user's sessions (no restart required)
`POST /auth/admin/invalidate-sessions/{user_id}`

Requires: admin Bearer token or an admin-scoped platform key.

Effect: increments `users.token_version`. All active JWTs for that user become invalid immediately and the user must log in again.

## How a user can log themselves out
`POST /auth/logout`

Requires: valid Bearer token.

Effect: increments the caller's `token_version`. The current token becomes invalid immediately.

## Token lifetime
JWTs expire after 24 hours (`ACCESS_TOKEN_EXPIRE_MINUTES = 1440`).

After a global `SECRET_KEY` rotation, stale tokens are rejected immediately because the signature is invalid.

After a per-user `token_version` bump, stale tokens are rejected immediately because the JWT `tv` claim no longer matches the value stored in the database.
