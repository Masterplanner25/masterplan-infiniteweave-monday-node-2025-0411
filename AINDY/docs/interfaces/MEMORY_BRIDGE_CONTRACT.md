# Memory Bridge Contract

This document defines the Memory Bridge API contract and its security boundary based strictly on current implementation.

## 1. Overview

### Current Behavior
- Memory Bridge is implemented in `AINDY/routes/bridge_router.py` with persistence in `AINDY/services/memory_persistence.py`.
- Database tables involved:
- `memory_nodes`
- `memory_links`
- File-based traces exist in:
- `AINDY/memoryevents/`
- `AINDY/memorytraces/`
- The file-based traces are not directly referenced by the Memory Bridge API code; they are separate artifacts.

### Policy Requirements
- Memory Bridge remains a security boundary for symbolic memory persistence.

## 2. Endpoints

### `POST /bridge/nodes`
- Request body: `NodeCreateRequest` (inline Pydantic model in `AINDY/routes/bridge_router.py`)
- Required fields:
- `content: str`
- `permission: TracePermission`
- Optional fields:
- `tags: List[str]` (default `[]`)
- `node_type: str` (default `"generic"`)
- `extra: dict` (default `{}`)
- HMAC requirement: required (`TracePermission` must validate).
- TTL behavior: request rejected if `permission.ts + permission.ttl < now`.
- Response: `NodeResponse` with `id`, `content`, `tags`, `node_type`, `extra`.
- Error conditions:
- 403 if signature invalid or TTL expired.
- Other DB or validation errors are not explicitly handled.

### `GET /bridge/nodes`
- Request body: none.
- Query params:
- `tag` (list of strings)
- `mode` (`OR` default)
- `limit` (default 100)
- HMAC requirement: none (read-only).
- Response: `NodeSearchResponse` with `nodes: [NodeResponse]`.
- Error conditions: not explicitly defined.

### `POST /bridge/link`
- Request body: `LinkCreateRequest` (inline Pydantic model in `AINDY/routes/bridge_router.py`)
- Required fields:
- `source_id: str`
- `target_id: str`
- `permission: TracePermission`
- Optional fields:
- `link_type: str` (default `"related"`)
- HMAC requirement: required (`TracePermission` must validate).
- TTL behavior: request rejected if `permission.ts + permission.ttl < now`.
- Response: `LinkResponse` with `id`, `source_node_id`, `target_node_id`, `link_type`, `strength`, `created_at`.
- Error conditions:
- 403 if signature invalid or TTL expired.
- Duplicate link or missing nodes can raise `ValueError` in `AINDY/services/memory_persistence.py` but are not explicitly translated into HTTP errors.

### `POST /bridge/user_event`
- Request body: `UserEvent` (inline Pydantic model)
- Required fields: `user`, `origin`
- Optional fields: `timestamp`
- HMAC requirement: none.
- TTL behavior: not applicable.
- Response: `{ "status": "logged", "user": str, "origin": str, "timestamp": str }`
- Error conditions: not explicitly defined.

### Endpoint Model Map (Reference)
| Endpoint | Request Model | Response Model |
|---|---|---|
| `POST /bridge/nodes` | `NodeCreateRequest` (`AINDY/routes/bridge_router.py`); includes `permission: TracePermission(nonce, ts, ttl, scopes, signature)` | `NodeResponse` (`AINDY/routes/bridge_router.py`) |
| `GET /bridge/nodes` | None | `NodeSearchResponse` (`AINDY/routes/bridge_router.py`) |
| `POST /bridge/link` | `LinkCreateRequest` (`AINDY/routes/bridge_router.py`); includes `permission: TracePermission(nonce, ts, ttl, scopes, signature)` | `LinkResponse` (`AINDY/routes/bridge_router.py`) |
| `POST /bridge/user_event` | `UserEvent` (`AINDY/routes/bridge_router.py`) | Inline dict response |

## 3. Permission Model

### Current Implementation
- HMAC signature validation is performed in `AINDY/routes/bridge_router.py: verify_permission_or_403`.
- Signature payload: `nonce|ts|ttl|sorted(scopes)` hashed with `PERMISSION_SECRET` using SHA-256.
- Payload construction detail: scopes are sorted and joined with commas before hashing (`','.join(sorted(scopes))`).
- Secret source: `PERMISSION_SECRET` from environment with fallback to `"dev-secret-must-change"` (`AINDY/routes/bridge_router.py`).
- TTL enforcement: `permission.ts + permission.ttl < now` triggers HTTP 403.
- Invalid signature: HTTP 403.

### Policy Requirements
- No mutation endpoints without signature validation.
- No bypass of HMAC checks.
- Any change to permission model requires:
- Update to `docs/governance/INVARIANTS.md`.
- Human approval.
- Errors must conform to `docs/governance/ERROR_HANDLING_POLICY.md`.

## 4. Data Integrity Rules

### Current Implementation
- Uniqueness constraint on `memory_links` (`source_node_id`, `target_node_id`, `link_type`) exists at DB level (via migrations and `MemoryLinkModel` indexes).
- Referential integrity enforced via foreign keys in migrations (`memory_links` → `memory_nodes`).
- Duplicate handling: DB will reject duplicates; `MemoryNodeDAO.create_link` does not catch uniqueness violations.

### Policy Requirements
- Uniqueness and FK constraints must not be removed without approval.

## 5. Failure Handling

### Current Implementation
- Invalid permission: HTTP 403 via `verify_permission_or_403`.
- Duplicate link: results in DB error if unique index is enforced; no explicit HTTP mapping.
- DB failure during node or link creation: `MemoryNodeDAO` rolls back and re-raises; route does not explicitly convert to HTTP error.

### Policy Requirements
- All mutation failures must return JSON error responses per `docs/governance/ERROR_HANDLING_POLICY.md`.

## 6. Policy Requirements
- No mutation endpoints without signature validation.
- No silent bypass of HMAC checks.
- Any change to permission model requires:
- Update to `docs/governance/INVARIANTS.md`.
- Human approval.
- Response errors must follow `docs/governance/ERROR_HANDLING_POLICY.md`.

## 7. Known Risks
- Secret rotation is not documented in code.
- No rate limiting in `AINDY/routes/bridge_router.py`.
- TTL validation is the only replay defense; short TTLs reduce risk but are not enforced by policy in code.
- File-system trace desynchronization risk: `AINDY/memoryevents/` and `AINDY/memorytraces/` are not automatically updated by API writes.
