# Memory Bridge Contract

This document defines the Memory Bridge API contract and its security boundary based strictly on current implementation.

## 1. Overview

### Current Behavior
- Canonical architecture reference: `docs/architecture/MEMORY_BRIDGE.md`.
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

---

## 8. Memory Router — Phase 2 Endpoints (`/memory/*`)

Added in Memory Bridge Phase 2 (2026-03-18). Authentication: JWT Bearer (`Depends(get_current_user)`). Defined in `AINDY/routes/memory_router.py`. DAO: `AINDY/db/dao/memory_node_dao.py`.

### `POST /memory/nodes` (status 201)
- Auth: JWT required.
- Request body: `CreateNodeRequest`
  - `content: str` (required)
  - `source: Optional[str]`
  - `tags: Optional[List[str]]` (default `[]`)
  - `node_type: Optional[Literal["decision", "outcome", "insight", "relationship"]]` (default `None`)
  - `extra: Optional[dict]` (default `{}`)
- Behavior: calls `MemoryNodeDAO.save()`, which generates an embedding via `embedding_service.generate_embedding()` and persists to `memory_nodes`. Returns node dict.
- Response: node dict with `id`, `content`, `tags`, `node_type`, `source`, `user_id`, `extra`, `created_at`, `updated_at`.

### `GET /memory/nodes/{node_id}`
- Auth: JWT required.
- Path param: `node_id` (UUID string).
- Response: node dict or 404.

### `GET /memory/nodes/{node_id}/links`
- Auth: JWT required.
- Query params: `direction` (`in` | `out` | `both`, default `both`).
- Response: `{"nodes": [...]}` — neighbors of the given node.
- Error: 404 if node not found; 422 if direction invalid.

### `GET /memory/nodes`
- Auth: JWT required.
- Query params: `tags` (comma-separated string), `mode` (`AND` | `OR`, default `AND`), `limit` (default 50).
- Response: `{"nodes": [...]}` — tag-filtered flat list (unranked).

### `POST /memory/links` (status 201)
- Auth: JWT required.
- Request body: `CreateLinkRequest`
  - `source_id: str` (required)
  - `target_id: str` (required)
  - `link_type: Optional[str]` (default `"related"`)
- Response: link dict or 422 on validation failure.

### `POST /memory/nodes/search`
- Auth: JWT required.
- Request body: `SimilaritySearchRequest`
  - `query: str` (required)
  - `limit: Optional[int]` (default 5)
  - `node_type: Optional[Literal[...]]`
  - `min_similarity: Optional[float]` (default 0.0)
- Behavior: generates query embedding via `generate_query_embedding(body.query)`, calls `MemoryNodeDAO.find_similar()` using pgvector `<=>` cosine distance. Filters NULL embeddings, user_id, node_type.
- Response: `{"query": str, "results": [...], "count": int}`. Each result includes `similarity` and `distance` fields.

### `POST /memory/recall`
- Auth: JWT required.
- Request body: `RecallRequest`
  - `query: Optional[str]`
  - `tags: Optional[List[str]]`
  - `limit: Optional[int]` (default 5)
  - `node_type: Optional[Literal[...]]`
- Validation: at least one of `query` or `tags` must be provided; returns 400 otherwise.
- Behavior: routes recall through `MemoryOrchestrator.get_context()` which delegates to `MemoryNodeDAO.recall()`. Combines semantic path (via `find_similar()`) and tag path (via `get_by_tags()`), deduplicates, scores by resonance formula, and enforces token budgets.
- Response: `{"query", "tags", "results", "count", "scoring_version": "v2", "formula": {...}}`.
- Each result includes: `resonance_score`, `semantic_score`, `graph_score`, `recency_score`, `success_rate`, `usage_frequency`, `adaptive_weight`, `tag_score`.

### Resonance Scoring Formula (v2)
```
resonance = (semantic * 0.40)
          + (graph * 0.15)
          + (recency * 0.15)
          + (success_rate * 0.20)
          + (usage_frequency * 0.10)

resonance = min(1.0, resonance * adaptive_weight)
resonance = min(1.0, resonance + (tag_match * 0.1))

recency   = exp(-age_days / 30.0)   # half-life: 30 days
tag_match = |node_tags ∩ query_tags| / |query_tags|
```

## 9. Memory Router — v3 Endpoints (`/memory/*`)

Added in Memory Bridge v3 (2026-03-18). Authentication: JWT Bearer (`Depends(get_current_user)`).

### `PUT /memory/nodes/{node_id}`
- Auth: JWT required.
- Request body: `UpdateNodeRequest`
  - `content: Optional[str]`
  - `tags: Optional[List[str]]`
  - `node_type: Optional[Literal["decision","outcome","insight","relationship"]]`
  - `source: Optional[str]`
- Behavior: updates a memory node and records previous values in `memory_node_history` when changes occur.
- Response: node dict.

### `GET /memory/nodes/{node_id}/history`
- Auth: JWT required.
- Query params: `limit` (int, default 20)
- Response: `{ "node_id": str, "history": [...], "count": int }`

### `GET /memory/nodes/{node_id}/traverse`
- Auth: JWT required.
- Query params: `max_depth` (default 3, capped at 5), `link_type` (optional), `min_strength` (default 0.0)
- Response: traversal dict with `chain`, `nodes_visited`, `narrative`

### `POST /memory/nodes/expand`
- Auth: JWT required.
- Request body: `ExpandRequest`
  - `node_ids: List[str]` (max 10)
  - `include_linked: bool` (default True)
  - `include_similar: bool` (default True)
  - `limit_per_node: int` (default 3)
- Response: `{ original_node_ids, expanded_nodes, expansion_count, expansion_map }`

### `POST /memory/recall/v3`
- Auth: JWT required.
- Request body: `RecallV3Request`
  - `query: Optional[str]`
  - `tags: Optional[List[str]]`
  - `limit: Optional[int]`
  - `node_type: Optional[Literal[...]]`
  - `expand_results: Optional[bool]`
- Behavior: when `expand_results=true`, returns results plus expanded context.
- Response includes the same `scoring_version` and `formula` metadata as `/memory/recall`.

### `POST /memory/nodes/{node_id}/feedback`
- Auth: JWT required.
- Request body: `FeedbackRequest`
  - `outcome: "success" | "failure" | "neutral"`
  - `context: Optional[str]` (freeform note)
- Behavior: records feedback on the node, increments usage, adjusts adaptive weight.
- Response: outcome summary with counts, adaptive weight, success rate.
- Errors: 404 if node not found; 422 on invalid outcome.

### `GET /memory/nodes/{node_id}/performance`
- Auth: JWT required.
- Response: performance metrics for the node (success/failure counts, usage, success rate, adaptive weight, graph connectivity).
- Errors: 404 if node not found.

### `POST /memory/suggest`
- Auth: JWT required.
- Request body: `SuggestRequest`
  - `query: Optional[str]`
  - `tags: Optional[List[str]]`
  - `context: Optional[str]`
  - `limit: Optional[int]` (default 3)
- Behavior: returns suggestions based on high-performing past memories.
- Errors: 400 if neither `query` nor `tags` provided.

## 10. Memory Router — v5 Phase 3 Endpoints (`/memory/*`)

Added in Memory Bridge v5 Phase 3 (2026-03-19). Authentication: JWT Bearer (`Depends(get_current_user)`).

### `POST /memory/federated/recall`
- Auth: JWT required.
- Request body: `FederatedRecallRequest`
  - `query: Optional[str]`
  - `tags: Optional[List[str]]`
  - `agent_namespaces: Optional[List[str]]`
  - `limit: Optional[int]` (default 5)
- Validation: at least one of `query` or `tags` required; 400 otherwise.
- Response: merged, ranked results across requested agents, plus per-agent grouping.

### `GET /memory/agents`
- Auth: JWT required.
- Response: list of active agents with per-user memory stats (total/shared/private).

### `GET /memory/agents/{namespace}/recall`
- Auth: JWT required.
- Query params: `query` (optional), `limit` (default 5).
- Response: shared memories for the specified agent namespace.

### `POST /memory/nodes/{node_id}/share`
- Auth: JWT required.
- Behavior: flips `is_shared=True` (one-way). Once shared, node is visible to all agents.
- Response: `{ node_id, is_shared, source_agent, message }`.

## 11. Memory Router ? v5 Phase 4 Metrics Endpoints (`/memory/*`)

Added in Memory Bridge v5 Phase 4 (2026-03-21). Authentication: JWT Bearer (`Depends(get_current_user)`).

### `GET /memory/metrics`
- Auth: JWT required.
- Response: summary impact metrics `{avg_impact_score, positive_impact_rate, zero_impact_rate, negative_impact_rate, total_runs}`.

### `GET /memory/metrics/detail`
- Auth: JWT required.
- Response: list of recent runs with `impact_score`, `memory_count`, `avg_similarity`, `task_type`, `created_at`.

### `GET /memory/metrics/dashboard`
- Auth: JWT required.
- Response: `{summary, recent_runs, insights}` for lightweight dashboard rendering.

### Endpoint Model Map (Phase 2 additions)
| Endpoint | Request Model | Response |
|---|---|---|
| `POST /memory/nodes` | `CreateNodeRequest` (`routes/memory_router.py`) | node dict |
| `GET /memory/nodes/{id}` | none | node dict or 404 |
| `GET /memory/nodes/{id}/links` | none | `{"nodes": [...]}` |
| `GET /memory/nodes` | query params | `{"nodes": [...]}` |
| `POST /memory/links` | `CreateLinkRequest` | link dict |
| `POST /memory/nodes/search` | `SimilaritySearchRequest` | `{"query", "results", "count"}` |
| `POST /memory/recall` | `RecallRequest` | `{"query", "tags", "results", "count", "scoring_version", "formula"}` |
| `POST /memory/nodes/{node_id}/feedback` | `FeedbackRequest` | outcome + counts + weight |
| `GET /memory/nodes/{node_id}/performance` | None | performance metrics |
| `POST /memory/suggest` | `SuggestRequest` | suggestions list |
