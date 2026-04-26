---
title: "API Contracts"
last_verified: "2026-04-18"
api_version: "1.0"
status: current
owner: "platform-team"
---
# API Contracts

This document formalizes the current FastAPI HTTP interface based strictly on implemented routes. It separates current behavior from policy requirements and does not introduce new endpoints.

## 1. Route Inventory

Routers are registered in `AINDY/main.py` using three mount groups defined in `AINDY/routes/__init__.py`.
The **final URL** is `mount_prefix + router_prefix + route_path`.

### Root (mounted at `/` — no prefix)

These paths are stable infrastructure. Never add an app or platform prefix here.

- `AINDY/routes/health_router.py` (no router prefix) **[public]** ? `/health`, `/health/`, `/ready`, `/health/details`
- `AINDY/routes/auth_router.py` (router prefix `/auth`) **[public — provides tokens]** ? `/auth/register`, `/auth/login`

### Platform layer (mounted at `/platform`)

Stable runtime API for external integrations and tooling. Breaking changes require a version bump.

- `AINDY/routes/platform_router.py` (router prefix `/platform`, mounted at root) **[JWT or Platform API key]** ? `/platform/flows/*`, `/platform/nodes/*`, `/platform/webhooks/*`, `/platform/keys/*`
- `AINDY/routes/flow_router.py` (router prefix `/flows`) **[JWT auth required]** ? `/platform/flows/runs`, `/platform/flows/runs/{id}`, `/platform/flows/registry`, etc.
- `AINDY/routes/observability_router.py` (router prefix `/observability`) **[JWT auth required]** ? `/platform/observability/scheduler/status`, `/platform/observability/requests`, `/platform/observability/dashboard`, etc.
- `AINDY/routes/system_state_router.py` (router prefix `/system`) **[JWT auth required]** ? `/platform/system/state`
- `AINDY/routes/db_verify_router.py` (router prefix `/db`) **[API key required]** ? `/platform/db/verify`

### Apps layer (mounted at `/apps`)

Mutable domain features. All paths below are prefixed with `/apps`.

- `AINDY/routes/agent_router.py` (router prefix `/agent`) **[JWT auth required]** ? `/apps/agent/run`, `/apps/agent/runs`, etc.
- `AINDY/routes/arm_router.py` (router prefix `/arm`) **[JWT auth required]** ? `/apps/arm/analyze`, `/apps/arm/generate`, etc.
- `AINDY/routes/autonomy_router.py` (router prefix `/autonomy`) **[JWT auth required]** ? `/apps/autonomy/decisions`
- `AINDY/routes/task_router.py` (router prefix `/tasks`) **[JWT auth required]** ? `/apps/tasks/create`, `/apps/tasks/start`, etc.
- `AINDY/routes/goals_router.py` (router prefix `/goals`) **[JWT auth required]** ? `/apps/goals/`
- `AINDY/routes/masterplan_router.py` (router prefix `/masterplans`) **[JWT auth required]** ? `/apps/masterplans/`
- `AINDY/routes/genesis_router.py` (router prefix `/genesis`) **[JWT auth required]** ? `/apps/genesis/session`, `/apps/genesis/message`, etc.
- `AINDY/routes/automation_router.py` (router prefix `/automation`) **[JWT auth required]** ? `/apps/automation/logs`, etc.
- `AINDY/routes/memory_router.py` (router prefix `/memory`) **[JWT auth required]** ? `/apps/memory/nodes`, `/apps/memory/recall`, etc.
- `AINDY/routes/memory_metrics_router.py` (router prefix `/memory`) **[JWT auth required]** ? `/apps/memory/metrics`, etc.
- `AINDY/routes/memory_trace_router.py` (router prefix `/memory`) **[JWT auth required]** ? `/apps/memory/traces`, etc.
- `AINDY/routes/bridge_router.py` (router prefix `/bridge`) **[JWT auth required for /nodes and /link; API key for /user_event]** ? `/apps/bridge/*`
- `AINDY/routes/freelance_router.py` (router prefix `/freelance`) **[JWT auth required]** ? `/apps/freelance/*`
- `AINDY/routes/leadgen_router.py` (router prefix `/leadgen`) **[JWT auth required]** ? `/apps/leadgen/`
- `AINDY/routes/analytics_router.py` (router prefix `/analytics`) **[JWT auth required]** ? `/apps/analytics/*`
- `AINDY/routes/social_router.py` (router prefix `/social`) **[JWT auth required]** ? `/apps/social/*`
- `AINDY/routes/score_router.py` (router prefix `/scores`) **[JWT auth required]** ? `/apps/scores/me`, `/apps/scores/feedback`, etc.
- `AINDY/routes/identity_router.py` (router prefix `/identity`) **[JWT auth required]** ? `/apps/identity/boot`, `/apps/identity/evolution`, etc.
- `AINDY/routes/watcher_router.py` (router prefix `/watcher`) **[API key required]** ? `/apps/watcher/signals`
- `AINDY/routes/coordination_router.py` (router prefix `/coordination`) **[JWT auth required]** ? `/apps/coordination/agents`, `/apps/coordination/graph`
- `AINDY/routes/dashboard_router.py` (router prefix `/dashboard`) **[JWT auth required]** ? `/apps/dashboard/overview`
- `AINDY/routes/health_dashboard_router.py` (router prefix `/dashboard`) **[JWT auth required]** ? `/apps/dashboard/health`
- `AINDY/routes/seo_routes.py` (router prefix `/seo`) **[JWT auth required]** ? `/apps/seo/analyze`, `/apps/seo/meta`, `/apps/seo/suggest`, etc.
- `AINDY/routes/research_results_router.py` (router prefix `/research`) **[JWT auth required]** ? `/apps/research/`
- `AINDY/routes/authorship_router.py` (router prefix `/authorship`) **[JWT auth required]** ? `/apps/authorship/reclaim`
- `AINDY/routes/rippletrace_router.py` (router prefix `/rippletrace`) **[JWT auth required]** ? `/apps/rippletrace/*`
- `AINDY/routes/network_bridge_router.py` (router prefix `/network_bridge`) **[API key required]** ? `/apps/network_bridge/*`
- `AINDY/routes/main_router.py` (router prefix `/compute`) **[JWT auth required]** ? `/apps/compute/calculate_twr`, `/apps/compute/calculate_engagement`, etc. (legacy KPI surface)
- `AINDY/routes/legacy_surface_router.py` (no router prefix, env-gated) **[compatibility surface]** ? `/apps/*` (old ripple/strategy/playbook endpoints; enabled via `AINDY_ENABLE_LEGACY_SURFACE=true`)

**Authentication model:**

Three principals are supported. All three work on any route that uses the `get_authenticated_principal()` or `require_scope()` dependency.

- **JWT Bearer token** — obtain via `POST /auth/login`; pass as `Authorization: Bearer <token>`. Full trust — no scope restrictions. Required on all `/apps/*` routes and most `/platform/*` routes.

- **Platform API key** (`X-Platform-Key: aindy_<token>` header) — issued via `POST /platform/keys`. Carries explicit capability scopes. Intended for external integrations and machine clients. Valid scopes:
  - `flow.read` — list/get flows and their definitions
  - `flow.execute` — run any registered flow via `POST /platform/flows/{name}/run`
  - `memory.read` — read memory nodes, recall, search
  - `memory.write` — create/update/delete memory nodes
  - `agent.run` — create and monitor agent runs
  - `webhook.manage` — create/delete webhook subscriptions
  - `platform.admin` — full platform access (implies all scopes)
  - Keys are SHA-256 hashed at rest; plaintext returned exactly once on creation.
  - Implementation: `auth/api_key_auth.py` — `require_scope("flow.execute")` dependency pattern.

- **Service API key** (`X-API-Key` header) — required on: `network_bridge_router` (Node.js gateway), `db_verify_router` (admin schema inspection), `/apps/bridge/user_event`. Key value from `AINDY_API_KEY` env var.

- **HMAC permission** — deprecated. `/bridge` write routes rely on JWT; `permission` is ignored if provided.

- **Public routes** (no auth): `/auth/*`, `/health`, `/health/`, `/ready`, `/health/details`, `GET /`.

- Zero unprotected non-public routes as of Sprint 4 (2026-03-18).

**Platform API (Sprint N+10/N+11 — 2026-03-31):**

Flow management (`/platform/flows/*`):
- `POST /platform/flows` — register a dynamic flow at runtime (no restart). Body: `FlowDefinition {name, nodes[], edges{}, start, end[], overwrite?}`. Persisted to DB.
- `GET /platform/flows` — list dynamically registered flows.
- `GET /platform/flows/{name}` — get a flow definition.
- `POST /platform/flows/{name}/run` — execute any registered flow. Body: `{state: {...}}`. Returns full execution envelope.
- `DELETE /platform/flows/{name}` — remove a dynamic flow (soft-delete in DB).

Node management (`/platform/nodes/*`):
- `POST /platform/nodes/register` — register an external node (webhook or plugin). Body: `NodeRegistration {name, type, handler, timeout_seconds?, secret?, overwrite?}`. Persisted to DB.
- `GET /platform/nodes` — list dynamic nodes.
- `GET /platform/nodes/{name}` — get node metadata.
- `DELETE /platform/nodes/{name}` — remove a dynamic node.

Webhook subscriptions (`/platform/webhooks/*`):
- `POST /platform/webhooks` — subscribe to a `SystemEvent` type. Body: `{event_type, callback_url, secret?}`. Supports exact (`"execution.completed"`), prefix wildcard (`"execution.*"`), and global wildcard (`"*"`). Persisted to DB.
- `GET /platform/webhooks` — list current user's subscriptions.
- `GET /platform/webhooks/{id}` — get subscription details (ownership-enforced).
- `DELETE /platform/webhooks/{id}` — cancel a subscription (soft-delete in DB).
- Delivery: async, up to 3 retries with exponential backoff (1 s ? 2 s ? 4 s). HMAC-SHA256 signed when `secret` is provided (`X-AINDY-Signature: sha256=<hex>`).

API key management (`/platform/keys/*`):
- `POST /platform/keys` — create a scoped API key. Body: `{name, scopes[], expires_at?}`. Returns plaintext key **once** — store it immediately.
- `GET /platform/keys` — list keys (prefix/scopes/stats; no plaintext).
- `GET /platform/keys/{id}` — get single key metadata.
- `DELETE /platform/keys/{id}` — revoke a key.

Persistence: All dynamic flows, nodes, and webhook subscriptions are persisted to `dynamic_flows`, `dynamic_nodes`, and `webhook_subscriptions` tables and **restored automatically on server restart** via `services/platform_loader.py` (startup loader).

**OS Isolation Layer (2026-04-01):**

Tenant usage (`/platform/tenants/*`):
- `GET /platform/tenants/{tenant_id}/usage` — JWT or Platform API key required. Returns quota usage for a tenant's active execution unit: `{tenant_id, quota_group, syscall_count, cpu_time_ms, memory_bytes, priority}`. 404 if no active unit found.

**Memory Address Space (MAS) — (2026-04-01):**

MAS path-addressable memory (`/platform/memory/*`):
- `GET /platform/memory` — JWT or Platform API key required. Hybrid list endpoint. Query params: `path` (MAS expression — exact, `/*`, or `/**`), `query` (text search), `tags` (comma-separated), `limit` (default 20). Returns `{nodes: [...], count: int, path: str|null}`.
- `GET /platform/memory/tree` — JWT or Platform API key required. Hierarchical tree from path prefix. Query params: `path` (required), `limit` (default 100). Returns `{tree: {...}, flat: [...], count: int, root: str}`.
- `GET /platform/memory/trace` — JWT or Platform API key required. Causal chain following `source_event_id` links backward from an exact node path. Query params: `path` (required), `depth` (default 5, max 10). Returns `{chain: [...], count: int, root_path: str}`.

See `docs/architecture/MEMORY_ADDRESS_SPACE.md` for path structure and wildcard rules.

**Syscall Registry Introspection (2026-04-01):**

- `GET /platform/syscalls` — JWT or Platform API key required. Query param: `version` (optional filter, e.g. `v1`). Returns the versioned registry with full ABI schemas: `{versions: ["v1", "v2"], syscalls: {v1: {action: {name, capability, description, stable, deprecated, input_schema, output_schema}}, ...}, total_count: int}`.

See `docs/architecture/SYSCALL_SYSTEM.md` for the full syscall system reference.

**Nodus Runtime (2026-04-01):**

Flow compiler (`/platform/nodus/flow/*`):
- `POST /platform/nodus/flow` — compile and optionally run a Nodus flow from `flow.step()` DSL. Body: `{source: str, run?: bool, state?: dict}`. Returns compiled graph or execution result.

Scheduler (`/platform/nodus/schedule/*`):
- `POST /platform/nodus/schedule` — schedule a Nodus flow. Body: `{name, flow_name, cron_expr, state?}`.
- `GET /platform/nodus/schedule` — list scheduled jobs for the current user.
- `DELETE /platform/nodus/schedule/{name}` — cancel a scheduled job.

Trace (`/platform/nodus/trace/*`):
- `GET /platform/nodus/trace/{execution_id}` — retrieve all `NodusTraceEvent` rows for an execution, ordered chronologically.

**Sprint 5 User Isolation (2026-03-18):**
- Freelance, research, and rippletrace routes now scope all reads and writes to the authenticated user's `user_id` (extracted from JWT `sub` claim).
- `GET /freelance/orders`, `GET /freelance/feedback` — return only records belonging to the current user.
- `POST /freelance/order`, `POST /freelance/feedback` — set `user_id` from JWT on creation.
- `POST /freelance/deliver/{id}` — returns 404 if order does not belong to current user.
- `GET /research/`, `POST /research/` — scoped to current user.
- All `/rippletrace/*` routes — scoped to current user.
- Cross-user data is never returned; wrong-owner requests return 404 (not 403 — existence must not be revealed).

**Rate limits (Phase 3):**
- `POST /leadgen/` — 10 requests/minute per IP
- `POST /genesis/message` — 20 requests/minute per IP
- `POST /genesis/synthesize` — 5 requests/minute per IP
- `POST /genesis/audit` — 5 requests/minute per IP
- `POST /arm/analyze` — 10 requests/minute per IP
- `POST /arm/generate` — 10 requests/minute per IP
- Enforced via `@limiter.limit()` decorator from `services/rate_limiter.py`; HTTP 429 on excess.

**Search System summary (current implementation):**
- SEO: `POST /apps/seo/analyze`, `POST /apps/seo/meta`.
- LeadGen: `POST /apps/leadgen/` (query param), `GET /apps/leadgen/`.
- Research: `POST /apps/research/`, `POST /apps/research/query`, `GET /apps/research/`.
- Memory search: `POST /apps/memory/nodes/search`, `POST /apps/memory/recall`.
- Note: LeadGen uses external retrieval with structured parsing; research routes now invoke `apps/search/services/research_engine.web_search()` + `ai_analyze()`.

**External interaction contract (current implementation):**
- Outbound OpenAI/LLM, HTTP, watcher-delivery, and health-probe calls are wrapped by `services/external_call_service.py`.
- Required `SystemEvent` types:
  - `external.call.started`
  - `external.call.completed`
  - `external.call.failed`
  - `error.external_call`
- Event payload includes:
  - `service_name`
  - `endpoint`
  - `model` when applicable
  - `method`
  - `status`
  - `latency_ms`
  - `error` when applicable
- Event persistence is fail-closed for the outbound interaction: a required event-emission failure raises rather than silently continuing.

**Successful operational-path eventing (current implementation):**
- `POST /auth/register` emits required `identity.created` during signup initialization
- `POST /auth/register` emits `auth.register.completed`
- `POST /auth/login` emits `auth.login.completed`
- `GET /identity/boot` emits required `identity.boot`
- `GET /health` and `GET /health/` emit `health.liveness.completed`
- `GET /ready` emits `health.readiness.completed`
- Async heavy-execution jobs use `automation_log_id` as `trace_id` and emit:
  - `execution.started` on submission
  - `async_job.started` when the queued worker begins
  - `async_job.completed` or `async_job.failed` for queued-worker outcome
  - `execution.completed` or `execution.failed` as the canonical execution result
- Required event persistence failures attempt `error.system_event_failure` and then raise fail-closed.
- Additional route-layer execution coverage:
  - `auth_router.py`
  - `analytics_router.py`
  - `arm_router.py`
  - `main_router.py`
  - `memory_router.py`
  now execute through `core/execution_pipeline.py` / `core/execution_helper.py`, which preserves their existing body shapes by default while adding request-scoped `trace_id`, best-effort `SystemEvent` lifecycle emission, and response `X-Trace-ID` headers.

**Freelancing summary (current implementation):**
- Orders: `POST /apps/freelance/order`, `POST /apps/freelance/deliver/{order_id}`, `GET /apps/freelance/orders`.
- Feedback: `POST /apps/freelance/feedback`, `GET /apps/freelance/feedback`.
- Metrics: `GET /apps/freelance/metrics/latest`, `POST /apps/freelance/metrics/update`.

**Social Layer summary (current implementation):**
- Profiles: `POST /apps/social/profile`, `GET /apps/social/profile/{username}`.
- Posts/Feed: `POST /apps/social/post`, `GET /apps/social/feed`.

**Masterplan SaaS summary (current implementation):**
- Genesis: `/apps/genesis/*` supports draft, synthesize, audit, and lock flows.
- MasterPlans: `/apps/masterplans/*` supports list, lock, and activate.
- Note: Masterplan anchor/ETA projection and dependency cascade outputs are not exposed as APIs.

**Memory Bridge Phase 1 additions (2026-03-18):**
- `POST /apps/memory/nodes` — JWT required. Body: `CreateNodeRequest {content, source?, tags?, node_type?, extra?}`. Persists a memory node. Returns node dict. Status 201.
- `GET /apps/memory/nodes/{node_id}` — JWT required. Returns node dict or 404.
- `GET /apps/memory/nodes/{node_id}/links` — JWT required. Query param: `direction` (`in`|`out`|`both`, default `both`). Returns `{"nodes": [...]}`. 404 if node not found, 422 if direction invalid.
- `GET /apps/memory/nodes` — JWT required. Query params: `tags` (comma-separated), `mode` (`AND`|`OR`, default `AND`), `limit` (default 50). Returns `{"nodes": [...]}`.
- `POST /apps/memory/links` — JWT required. Body: `CreateLinkRequest {source_id, target_id, link_type?}`. Returns link dict. Status 201. 422 if nodes don't exist or same ID.

**Memory Bridge Phase 2 additions (2026-03-18):**
- `POST /apps/memory/nodes/search` — JWT required. Body: `SimilaritySearchRequest {query, limit?, node_type?, min_similarity?}`. Returns `{"query", "results", "count"}` with semantic `similarity` and `distance`.
- `POST /apps/memory/recall` — JWT required. Body: `RecallRequest {query?, tags?, limit?, node_type?}`. Returns resonance-scored results and scoring metadata (`scoring_version: "v2"`, `formula: {...}`). 400 if neither `query` nor `tags` provided.

**Memory Bridge v3 additions (2026-03-18):**
- `PUT /apps/memory/nodes/{node_id}` — JWT required. Body: `UpdateNodeRequest {content?, tags?, node_type?, source?}`. Updates a memory node and records history (previous values).
- `GET /apps/memory/nodes/{node_id}/history` — JWT required. Query: `limit` (default 20). Returns `{node_id, history, count}` ordered by `changed_at DESC`.
- `GET /apps/memory/nodes/{node_id}/traverse` — JWT required. Query: `max_depth` (default 3, capped at 5), `link_type` (optional), `min_strength` (default 0.0). Returns DFS chain plus narrative.
- `POST /apps/memory/nodes/expand` — JWT required. Body: `ExpandRequest {node_ids, include_linked?, include_similar?, limit_per_node?}`. Returns expanded context graph; max 10 input nodes.
- `POST /memory/recall/v3` — JWT required. Body: `RecallV3Request {query?, tags?, limit?, node_type?, expand_results?}`. Returns standard recall or expanded context when `expand_results=true`.

**Memory Bridge v4 additions (2026-03-18):**
- `POST /memory/nodes/{node_id}/feedback` — JWT required. Body: `FeedbackRequest {outcome, context?}`. Records feedback and adjusts adaptive weight.
- `GET /memory/nodes/{node_id}/performance` — JWT required. Returns performance metrics for a node.
- `POST /memory/suggest` — JWT required. Body: `SuggestRequest {query?, tags?, context?, limit?}`. Returns recommendations based on past high-performing memories.

**Memory Bridge v5 Phase 3 additions (2026-03-19):**
- `POST /memory/federated/recall` — JWT required. Body: `FederatedRecallRequest {query?, tags?, agent_namespaces?, limit?}`. Returns merged, ranked results across agents.
- `GET /memory/agents` — JWT required. Returns list of agents and per-user memory stats.
- `GET /memory/agents/{namespace}/recall` — JWT required. Query params: `query`, `limit`. Returns shared memories from a specific agent namespace.
- `POST /memory/nodes/{node_id}/share` — JWT required. Shares a private node across all agents (one-way).

**Memory Bridge v5 Phase 4 additions (2026-03-21):**
- `GET /memory/metrics` ? JWT required. Returns summary impact metrics.
- `GET /memory/metrics/detail` ? JWT required. Returns recent impact runs.
- `GET /memory/metrics/dashboard` ? JWT required. Returns summary + recent runs + insights.

**Memory Bridge v5 Phase 5 additions (2026-03-21):**
- `POST /memory/traces` ? JWT required. Creates a new trace.
- `POST /memory/traces/{trace_id}/append` ? JWT required. Appends a node to a trace.
- `GET /memory/traces` ? JWT required. Lists traces for the user.
- `GET /memory/traces/{trace_id}` ? JWT required. Returns trace metadata.
- `GET /memory/traces/{trace_id}/nodes` ? JWT required. Returns ordered trace nodes.

**Memory Bridge execution contract (current):**
- `POST /memory/execute` — JWT required. Runs through the canonical flow/observability pipeline and returns the standardized execution envelope.
- `POST /memory/execute/complete` — deprecated compatibility path and no longer part of the active contract.
- `POST /memory/nodus/execute` — JWT required. Restricted executor surface with source validation, allowed-operation registration, and scoped capability-token enforcement for write-capable operations.
- When `AINDY_ASYNC_HEAVY_EXECUTION=true`, `POST /memory/nodus/execute` returns `202` and the background job emits `execution.started` / `execution.completed` or `execution.failed` with `trace_id == automation_log_id`.

**Agent route input validation (current):**
- `GET /agent/runs/{run_id}`
- `POST /agent/runs/{run_id}/approve`
- `POST /agent/runs/{run_id}/reject`
- `POST /agent/runs/{run_id}/recover`
- `POST /agent/runs/{run_id}/replay`
- `GET /agent/runs/{run_id}/steps`
- `GET /agent/runs/{run_id}/events`
- Invalid `run_id` values fail cleanly with HTTP `400` and do not fall through to a `500`.

**Genesis Block 4-6 additions (2026-03-17):**
- `POST /genesis/audit` — JWT required. Body: `{"session_id": int}`. Loads `session.draft_json`,
  runs GPT-4o strategic integrity audit. Returns: `{audit_passed, findings, overall_confidence, audit_summary}`.
  422 if no draft available.
- `POST /masterplans/lock` — JWT required. Body: `{"session_id": int, "draft": {}}`. Creates and
  locks a MasterPlan from a completed Genesis session. Returns: `{masterplan_id, version, posture,
  posture_description, status}`. 400 if session not found/already locked. 422 if synthesis_ready=False.
- `GET /masterplans/` — response shape updated to `{"plans": [...]}` (was plain array).

Root route registered directly in `AINDY/main.py`:
- `GET /`

Legacy compatibility routes are registered in `AINDY/routes/legacy_surface_router.py` and include:
- `/dashboard`
- `/top_drop_points`
- `/analyze_ripple/{drop_point_id}`
- `/ripple_deltas/{drop_point_id}`
- `/emerging_drops`
- `/predict/{drop_point_id}`
- `/prediction_summary`
- `/recommend/{drop_point_id}`
- `/recommendations_summary`
- `/influence_graph`
- `/influence_chain/{drop_point_id}`
- `/causal_graph`
- `/causal_chain/{drop_point_id}`
- `/narrative/{drop_point_id}`
- `/narrative_summary`
- `/strategies`
- `/strategy/{strategy_id}`
- `/strategy_match/{drop_point_id}`
- `/build_playbook/{strategy_id}`
- `/playbooks`
- `/playbook/{playbook_id}`
- `/playbook_match/{drop_point_id}`
- `/generate_content/{playbook_id}`
- `/generate_content_for_drop/{drop_point_id}`
- `/generate_variations/{playbook_id}`
- `/learning_stats`
- `/evaluate/{drop_point_id}`

## 2. Per-Route Contract Definition (Current Implementation)

### Auth Routes (`AINDY/routes/auth_router.py`) — PUBLIC
`POST /auth/login`
Method: POST
Request Body: `{ "email": str, "password": str }`
Query Params: None
Response: `{ "access_token": str, "token_type": "bearer" }`
Status Codes: 200, 401
Errors: 401 if credentials invalid.
Auth: None (public endpoint — use this to obtain a token)
Observability: route runs through the route execution pipeline and emits `auth.login.completed` on success.

`POST /auth/register`
Method: POST
Request Body: `{ "email": str, "password": str, "username": str | null }`
Query Params: None
Response: `{ "access_token": str, "token_type": "bearer" }`
Status Codes: 201, 409
Errors: 409 if email already registered.
Auth: None (public endpoint)
Notes:
- `username` is optional. When omitted, the backend derives a unique username from the email local-part.
- Successful signup seeds:
  - an initial memory node with `content = "User account created"` and `extra.context = "identity_init"`
  - a baseline score row with `master_score = 0.0`
  - an initialized execution placeholder via `AgentRun`
  - a blank `UserIdentity` row when absent
Observability:
- route runs through the route execution pipeline
- emits required `identity.created` on successful signup initialization
- emits `auth.register.completed` on success

### Root Route (`AINDY/main.py`)
`GET /`
Method: GET
Request Body: None
Query Params: None
Response: `{ "message": "A.I.N.D.Y. API is running!" }`
Status Codes: 200
Errors: Not explicitly defined.

### SEO Routes (`AINDY/routes/seo_routes.py`)
`POST /seo/analyze`
Method: POST
Request Body: `SEOInput` (`AINDY/services/seo.py`)
Query Params: None
Response: Dict returned by `seo_analysis`, includes at least `readability`, `word_count`, and `keyword_densities` as used by the route.
Status Codes: 200
Errors: Not explicitly defined.

`POST /seo/meta`
Method: POST
Request Body: `MetaInput` (`AINDY/services/seo.py`)
Query Params: None
Response: `{ "meta_description": str }`
Status Codes: 200
Errors: Not explicitly defined.

### Task Routes (`AINDY/routes/task_router.py`, prefix `/tasks`)
  `POST /tasks/create`
  Method: POST
  Request Body: `TaskCreate` (`AINDY/schemas/task_schemas.py`)
  Query Params: None
  Response: ORM `Task` model serialized by FastAPI (fields from `AINDY/db/models/task.py`).
  Auth: JWT required; task is owned by `current_user["sub"]`.
  Status Codes: 200
  Errors: Not explicitly defined.

`POST /tasks/start`
Method: POST
Request Body: `TaskAction`
Query Params: None
Response: String message from `task_services.start_task`.
Status Codes: 200
Errors: Not explicitly defined.

`POST /tasks/pause`
Method: POST
Request Body: `TaskAction`
Query Params: None
Response: String message from `task_services.pause_task`.
Status Codes: 200
Errors: Not explicitly defined.

`POST /tasks/complete`
Method: POST
Request Body: `TaskAction`
Query Params: None
Response: String message from `task_services.complete_task`.
Status Codes: 200
Errors: Not explicitly defined.

  `GET /tasks/list`
  Method: GET
  Request Body: None
  Query Params: None
  Response: List of dicts with `task_name`, `status`, `time_spent`.
  Auth: JWT required; returns tasks scoped to `current_user["sub"]`.
  Status Codes: 200
  Errors: Not explicitly defined.

  `POST /tasks/recurrence/check`
  Method: POST
  Request Body: None
  Query Params: None
  Response: `{ "message": "Recurrence job started in background." }`
  Auth: JWT required.
  Status Codes: 200
  Errors: Not explicitly defined.

### Bridge Routes (`AINDY/routes/bridge_router.py`, prefix `/bridge`)
  `POST /bridge/nodes`
  Method: POST
  Request Body: `NodeCreateRequest` (inline Pydantic model) with fields:
  - `content: str`
  - `tags: List[str]`
  - `node_type: str`
  - `extra: dict`
  - `permission: TracePermission` (optional, ignored)
  Query Params: None
  Response: `NodeResponse` with `id`, `content`, `tags`, `node_type`, `extra`.
  Auth: JWT required; `user_id` enforced from `current_user["sub"]` (payload user_id is ignored).
  Status Codes: 201
Errors: Not explicitly defined.

`GET /bridge/nodes`
Method: GET
Request Body: None
Query Params: `tag` (list), `mode` (default "OR"), `limit` (default 100)
Response: `NodeSearchResponse` with `nodes: [NodeResponse]`.
  Auth: JWT required; results filtered by `current_user[\"sub\"]`.
Status Codes: 200
Errors: Not explicitly defined.

`POST /bridge/link`
Method: POST
Request Body: `LinkCreateRequest` (inline Pydantic model) with fields:
- `source_id: str`
- `target_id: str`
- `link_type: str`
- `permission: TracePermission` (optional, ignored)
Query Params: None
Response: `LinkResponse` with `id`, `source_node_id`, `target_node_id`, `link_type`, `strength`, `created_at`.
  Auth: JWT required; link creation is rejected if either node is not owned by `current_user[\"sub\"]`.
Status Codes: 201
Errors: 400 on invalid IDs (from `ValueError`) is not explicitly mapped.

`POST /bridge/user_event`
Method: POST
Request Body: `UserEvent` (inline Pydantic model with `user`, `origin`, optional `timestamp`)
Query Params: None
Response: `{ "status": "logged", "user": str, "origin": str, "timestamp": str }`
Persistence: Writes to `bridge_user_events` with `user_name`, `origin`, `raw_timestamp`, `occurred_at`.
Status Codes: 200
Errors: Not explicitly defined.

### Authorship Routes (`AINDY/routes/authorship_router.py`, prefix `/authorship`)
`POST /authorship/reclaim`
Method: POST
Request Body: None (parameters are plain function arguments)
Query Params: `content`, `author` (default), `motto` (default)
Response: Output of `domain.authorship_services.reclaim_authorship` (schema not explicitly defined).
Status Codes: 200
Errors: Not explicitly defined.

### RippleTrace Routes (`AINDY/routes/rippletrace_router.py`, prefix `/rippletrace`)
`POST /rippletrace/drop_point`
Method: POST
Request Body: `DropPoint` (inline Pydantic model)
Query Params: None
Response: ORM `DropPointDB` serialized by FastAPI.
Status Codes: 200
Errors: Not explicitly defined.

`POST /rippletrace/ping`
Method: POST
Request Body: `Ping` (inline Pydantic model)
Query Params: None
Response: ORM `PingDB` serialized by FastAPI.
Status Codes: 200
Errors: Not explicitly defined.

`GET /rippletrace/ripples/{drop_point_id}`
Method: GET
Request Body: None
Query Params: None
Response: List of `PingDB` ORM objects serialized by FastAPI.
Status Codes: 200
Errors: Not explicitly defined.

`GET /rippletrace/drop_points`
Method: GET
Request Body: None
Query Params: None
Response: List of `DropPointDB` ORM objects.
Status Codes: 200
Errors: Not explicitly defined.

`GET /rippletrace/pings`
Method: GET
Request Body: None
Query Params: None
Response: List of `PingDB` ORM objects.
Status Codes: 200
Errors: Not explicitly defined.

`GET /rippletrace/recent`
Method: GET
Request Body: None
Query Params: `limit` (default 10)
Response: List of recent `PingDB` objects.
Status Codes: 200
Errors: Not explicitly defined.

`POST /rippletrace/event`
Method: POST
Request Body: `RippleEvent` (inline Pydantic model)
Query Params: None
Response: `{ "status": "logged", "event": <event_dict> }`
Status Codes: 200
Errors: Not explicitly defined.

### Network Bridge Routes (`AINDY/routes/network_bridge_router.py`, prefix `/network_bridge`)
`POST /network_bridge/connect`
Method: POST
Request Body: `NetworkHandshake`
Query Params: None
Response: `{ "status": "connected", "author_id": str, "platform": str, "timestamp": str }`
Status Codes: 200
Errors: Not explicitly defined.

`POST /network_bridge/user_event`
Method: POST
Request Body: `NetworkUser`
Query Params: None
Response: `{ "status": "logged", "user": str, "tagline": str, "record_id": str }`
Status Codes: 200
Errors: Not explicitly defined.

`GET /network_bridge/authors`
Method: GET
Request Body: None
Query Params: `platform` (optional), `limit` (optional, default 100)
Response: `{ "authors": [ { "id": str, "name": str, "platform": str, "notes": str|null, "joined_at": str|null, "last_seen": str|null } ], "count": int, "platform": str|null }`
Status Codes: 200
Errors: Not explicitly defined.

### DB Verify Routes (`AINDY/routes/db_verify_router.py`, prefix `/db`)
`GET /db/verify`
Method: GET
Request Body: None
Query Params: None
Response: `{ "database_schema": { "table": [ {"name": str, "type": str, "nullable": bool}, ... ] } }`
Status Codes: 200
Errors: Not explicitly defined.

### Research Routes (`AINDY/routes/research_results_router.py`, prefix `/research`)
`POST /research/`
Method: POST
Request Body: `ResearchResultCreate` (`AINDY/schemas/research_results_schema.py`)
Query Params: None
Response: `ResearchResultResponse` (includes `source`, `data`, and top-level `search_score`)
Status Codes: 200
Errors: Not explicitly defined.

`GET /research/`
Method: GET
Request Body: None
Query Params: None
Response: `list[ResearchResultResponse]`
Status Codes: 200
Errors: Not explicitly defined.

`POST /research/query`
Method: POST
Request Body: `ResearchResultCreate`
Query Params: None
Response: `ResearchResultResponse` (includes `source`, `data`, and top-level `search_score`)
Status Codes: 200
Errors: Not explicitly defined.

### Main Calculation & Masterplan Routes (`AINDY/routes/main_router.py`, no prefix)
Route execution note:
- These routes now enter the route execution pipeline and preserve their existing JSON/ORM body shapes rather than returning the generic execution envelope.

`POST /calculate_twr`
Method: POST
Request Body: `TaskInput` (`AINDY/schemas/analytics_inputs.py`)
Query Params: None
Response: Dict with `task_name`, `TWR`, and optionally `active_projection` and `origin_projection` if masterplans exist.
Status Codes: 200, 422
Errors: 200 with message if no masterplans; 422 if `task_difficulty <= 0` (rejected at Pydantic validator in `TaskInput` and guarded in `calculate_twr()`).

`POST /calculate_effort`
Method: POST
Request Body: `TaskInput`
Query Params: None
Response: `{ "task_name": str, "Effort Score": number }`
Status Codes: 200
Errors: Not explicitly defined.

`POST /calculate_productivity`
Method: POST
Request Body: `TaskInput`
Query Params: None
Response: `{ "task_name": str, "Productivity Score": number }`
Status Codes: 200
Errors: Not explicitly defined.

`POST /calculate_virality`
Method: POST
Request Body: `ViralityInput`
Query Params: None
Response: `{ "Virality Score": number }`
Status Codes: 200
Errors: Not explicitly defined.

`POST /calculate_engagement`
Method: POST
Request Body: `EngagementInput`
Query Params: None
Response: `{ "Engagement Score": number }`
Status Codes: 200
Errors: Not explicitly defined.

`POST /calculate_ai_efficiency`
Method: POST
Request Body: `AIEfficiencyInput`
Query Params: None
Response: `{ "AI Efficiency Score": number }`
Status Codes: 200
Errors: Not explicitly defined.

`POST /calculate_impact_score`
Method: POST
Request Body: `ImpactInput`
Query Params: None
Response: `{ "Impact Score": number }`
Status Codes: 200
Errors: Not explicitly defined.

`POST /income_efficiency`
Method: POST
Request Body: `EfficiencyInput`
Query Params: None
Response: `{ "Income Efficiency": number }`
Status Codes: 200
Errors: Not explicitly defined.

`POST /revenue_scaling`
Method: POST
Request Body: `RevenueScalingInput`
Query Params: None
Response: `{ "Revenue Scaling": number }`
Status Codes: 200
Errors: Not explicitly defined.

`POST /execution_speed`
Method: POST
Request Body: `ExecutionSpeedInput`
Query Params: None
Response: `{ "Execution Speed": number }`
Status Codes: 200
Errors: Not explicitly defined.

`POST /attention_value`
Method: POST
Request Body: `AttentionValueInput`
Query Params: None
Response: `{ "Attention Value": number }`
Status Codes: 200
Errors: Not explicitly defined.

`POST /engagement_rate`
Method: POST
Request Body: `EngagementRateInput`
Query Params: None
Response: `{ "Engagement Rate": number }`
Status Codes: 200
Errors: Not explicitly defined.

`POST /business_growth`
Method: POST
Request Body: `BusinessGrowthInput`
Query Params: None
Response: `{ "Business Growth": number }`
Status Codes: 200
Errors: Not explicitly defined.

`POST /monetization_efficiency`
Method: POST
Request Body: `MonetizationEfficiencyInput`
Query Params: None
Response: `{ "Monetization Efficiency": number }`
Status Codes: 200
Errors: Not explicitly defined.

`POST /ai_productivity_boost`
Method: POST
Request Body: `AIProductivityBoostInput`
Query Params: None
Response: `{ "AI Productivity Boost": number }`
Status Codes: 200
Errors: Not explicitly defined.

`POST /lost_potential`
Method: POST
Request Body: `LostPotentialInput`
Query Params: None
Response: `{ "Lost Potential": number }`
Status Codes: 200
Errors: Not explicitly defined.

`POST /decision_efficiency`
Method: POST
Request Body: `DecisionEfficiencyInput`
Query Params: None
Response: `{ "Decision Efficiency": number }`
Status Codes: 200
Errors: Not explicitly defined.

`POST /batch_calculations`
Method: POST
Request Body: `BatchInput` (`AINDY/schemas/batch.py`)
Query Params: None
Response: Dict of metric names to values as returned by `analytics.calculations.process_batch`.
Status Codes: 200
Errors: Not explicitly defined.

`GET /results`
Method: GET
Request Body: None
Query Params: None
Response: List of `CalculationResult` ORM objects.
Status Codes: 200
Errors: Not explicitly defined.

`GET /masterplans`
Method: GET
Request Body: None
Query Params: None
Response: List of `MasterPlan` ORM objects.
Status Codes: 200
Errors: Not explicitly defined.

`POST /create_masterplan`
Method: POST
Request Body: `MasterPlanInput` (`AINDY/schemas/masterplan.py`)
Query Params: None
Response: ORM `MasterPlan` object.
Status Codes: 200
Errors: Not explicitly defined.

### Freelance Routes (`AINDY/routes/freelance_router.py`, prefix `/freelance`)
`POST /freelance/order`
Method: POST
Request Body: `FreelanceOrderCreate`
Query Params: None
Response: `FreelanceOrderResponse`
Status Codes: 201, 500 on service errors.
Errors: HTTP 500 on create failure.

`POST /freelance/deliver/{order_id}`
Method: POST
Request Body: `ai_output: str` (query parameter; not defined as body model)
Query Params: `order_id` path param, `ai_output` query param
Response: `FreelanceOrderResponse`
Status Codes: 200, 404 if order not found, 500 on errors.

`POST /freelance/feedback`
Method: POST
Request Body: `FeedbackCreate`
Query Params: None
Response: `FeedbackResponse`
Status Codes: 200, 404 if order not found, 500 on errors.

`GET /freelance/orders`
Method: GET
Request Body: None
Query Params: None
Response: `list[FreelanceOrderResponse]`
Status Codes: 200
Errors: Not explicitly defined.

`GET /freelance/feedback`
Method: GET
Request Body: None
Query Params: None
Response: `list[FeedbackResponse]`
Status Codes: 200
Errors: Not explicitly defined.

`GET /freelance/metrics/latest`
Method: GET
Request Body: None
Query Params: None
Response: `RevenueMetricsResponse`
Status Codes: 200, 404 if no metrics.

`POST /freelance/metrics/update`
Method: POST
Request Body: None
Query Params: None
Response: `RevenueMetricsResponse`
Status Codes: 200, 500 on errors.

### ARM Routes (`AINDY/routes/arm_router.py`, prefix `/arm`) — Phase 1 (2026-03-17)
Auth: JWT Bearer required on all endpoints (router-level dependency).
Route execution note:
- ARM routes now enter the route execution pipeline. Sync responses preserve existing payload shape; queued async-heavy responses still return the existing `202` queued body unchanged.
Rate limits: POST /arm/analyze and POST /arm/generate — 10 requests/minute per IP.

`POST /arm/analyze`
Method: POST
Request Body: `AnalyzeRequest`
  - `file_path`: str (required) — absolute or relative path to file to analyze
  - `complexity`: float | null — Infinity Algorithm input (default: config value)
  - `urgency`: float | null — Infinity Algorithm input (default: config value)
  - `context`: str | null — additional context sent to GPT-4o
Query Params: None
Response (200):
  ```json
  {
    "summary": "executive summary string",
    "architecture_score": 1-10,
    "performance_score": 1-10,
    "integrity_score": 1-10,
    "findings": [
      {
        "category": "architecture|performance|integrity|improvement",
        "severity": "critical|high|medium|low",
        "title": "string",
        "description": "string",
        "recommendation": "string"
      }
    ],
    "overall_recommendation": "string",
    "session_id": "uuid",
    "analysis_id": "uuid",
    "file": "filename",
    "execution_seconds": float,
    "input_tokens": int,
    "output_tokens": int,
    "task_priority": float,
    "execution_speed": float
  }
  ```
Status Codes: 200 (success), 401 (no auth), 403 (blocked path or sensitive content),
  404 (file not found), 422 (unsupported extension or file too large), 429 (rate limit),
  500 (OpenAI error after retries exhausted).
Security: SecurityValidator runs before OpenAI call. Path traversal blocked. .env,
  venv, .git, secrets directories blocked. API keys, private keys, AWS keys detected
  in content ? 403.

`POST /arm/generate`
Method: POST
Request Body: `GenerateRequest`
  - `prompt`: str (required) — natural-language generation or refactor instructions
  - `original_code`: str | null — existing code to refactor (optional)
  - `language`: str (default "python")
  - `generation_type`: str (default "generate") — "generate" | "refactor" | "explain"
  - `analysis_id`: str | null — UUID linking to a prior analysis session (optional)
  - `complexity`: float | null
  - `urgency`: float | null
Query Params: None
Response (200):
  ```json
  {
    "generated_code": "string",
    "language": "string",
    "explanation": "string",
    "quality_notes": "string",
    "confidence": 1-10,
    "session_id": "uuid",
    "generation_id": "uuid",
    "execution_seconds": float,
    "input_tokens": int,
    "output_tokens": int,
    "task_priority": float
  }
  ```
Status Codes: 200, 401, 403 (sensitive content in original_code), 422, 429, 500.
Security: `original_code` validated via `SecurityValidator.validate_code_input()`
  before being sent to OpenAI.

`GET /arm/logs`
Method: GET
Query Params: `limit` (int, default 20) — max records per category
Response (200):
  ```json
  {
    "analyses": [
      {
        "session_id": "uuid",
        "file": "filename",
        "status": "success|failed|blocked",
        "execution_seconds": float,
        "input_tokens": int,
        "output_tokens": int,
        "task_priority": float,
        "execution_speed": float,
        "summary": "string",
        "created_at": "ISO datetime"
      }
    ],
    "generations": [
      {
        "session_id": "uuid",
        "language": "string",
        "generation_type": "string",
        "execution_seconds": float,
        "input_tokens": int,
        "output_tokens": int,
        "created_at": "ISO datetime"
      }
    ],
    "summary": {
      "total_analyses": int,
      "total_generations": int,
      "total_tokens_used": int
    }
  }
  ```
Status Codes: 200, 401.
Note: Returns only records for the authenticated user (filtered by user_id).

`GET /arm/config`
Method: GET
Request Body: None
Query Params: None
Response (200): Flat dict — current ARM configuration (all 16 DEFAULT_CONFIG keys
  merged with any persisted overrides from `deepseek_config.json`).
  Example keys: `model`, `analysis_model`, `generation_model`, `temperature`,
  `generation_temperature`, `max_chunk_tokens`, `max_output_tokens`, `retry_limit`,
  `retry_delay_seconds`, `max_file_size_bytes`, `task_complexity_default`,
  `task_urgency_default`, `resource_cost_default`.
Status Codes: 200, 401.

`PUT /arm/config`
Method: PUT
Request Body: `ConfigUpdateRequest`
  - `updates`: dict — key/value pairs to update. Unknown keys silently ignored.
Query Params: None
Response (200):
  ```json
  { "status": "updated", "config": { ...full updated config dict... } }
  ```
Status Codes: 200, 401, 422 (Pydantic validation error).
Note: Changes persist to `deepseek_config.json`. Analyzer singleton is reset after
  update so the next request picks up the new configuration.
Errors: Not explicitly defined.

`GET /arm/metrics` — Phase 2 (2026-03-17)
Method: GET
Request Body: None
Query Params: `window` (int, default 30) — lookback period in days
Response (200):
  ```json
  {
    "window_days": 30,
    "total_sessions": int,
    "execution_speed": {
      "current": float, "average": float, "peak": float,
      "unit": "tokens/sec", "total_tokens": int, "total_seconds": float
    },
    "decision_efficiency": {
      "score": float, "successful": int, "failed": int, "total": int, "unit": "%"
    },
    "ai_productivity_boost": {
      "ratio": float, "input_tokens": int, "output_tokens": int,
      "rating": "excellent|good|moderate|low — prompts may be too verbose"
    },
    "lost_potential": {
      "failed_sessions": int, "wasted_tokens": int, "wasted_seconds": float,
      "waste_percentage": float, "rating": str
    },
    "learning_efficiency": {
      "trend": "improving|stable|declining|insufficient data",
      "delta_tokens_per_sec": float, "delta_percentage": float,
      "early_avg_speed": float, "recent_avg_speed": float
    },
    "summary": str
  }
  ```
Status Codes: 200, 401.
Note: Returns empty metrics structure (not 404) when user has no ARM sessions.
  Decision Efficiency and Lost Potential use analysis_results only (CodeGeneration
  has no status column). Execution Speed and AI Productivity Boost include both tables.

`GET /arm/config/suggest` — Phase 2 (2026-03-17)
Method: GET
Request Body: None
Query Params: `window` (int, default 30) — lookback period in days
Response (200):
  ```json
  {
    "suggestions": [
      {
        "priority": "critical|warning|info",
        "metric": str,
        "current_value": str,
        "threshold": str,
        "issue": str,
        "suggestion": str,
        "config_change": { ...key/value pairs... },
        "expected_impact": str,
        "risk": "low|medium|high|none"
      }
    ],
    "auto_apply_safe": [ ...low-risk suggestions with config_change... ],
    "requires_approval": [ ...medium/high-risk suggestions... ],
    "combined_suggested_config": { ...merged config_change from all suggestions... },
    "apply_instruction": str,
    "metrics_snapshot": {
      "decision_efficiency": float,
      "execution_speed_avg": float,
      "ai_productivity_ratio": float,
      "waste_percentage": float,
      "learning_trend": str,
      "total_sessions": int
    }
  }
  ```
Status Codes: 200, 401.
Note: Advisory only — never auto-applies. User must call PUT /arm/config with
  combined_suggested_config or individual changes to apply. config_change keys are
  validated against DEFAULT_CONFIG allowlist in ConfigManager.update().

### Leadgen Routes (`AINDY/routes/leadgen_router.py`, prefix `/leadgen`)
`POST /leadgen/`
Method: POST
Request Body: None
Query Params: `query` (required)
Response: `{ "query": str, "count": int, "results": [ {company, url, fit_score, intent_score, data_quality_score, overall_score, reasoning, search_score, created_at} ] }`
Status Codes: 200
Errors: Not explicitly defined.

`GET /leadgen/`
Method: GET
Request Body: None
Query Params: None
Response: List of dicts with lead fields.
Auth: JWT required; results filtered by `current_user["sub"]`.
Status Codes: 200
Errors: Not explicitly defined.

### Dashboard Routes (`AINDY/routes/dashboard_router.py`, prefix `/dashboard`)
`GET /dashboard/overview`
Method: GET
Request Body: None
Query Params: None
Response: `{ "status": "ok", "overview": { "system_timestamp": str, "author_count": int, "recent_authors": [...], "recent_ripples": [...] } }`
Status Codes: 200
Errors: Not explicitly defined.

### Health Routes (`AINDY/routes/health_router.py`)
`GET /health` and `GET /health/`
Method: GET
Request Body: None
Query Params: None
Response: `{ "status": "ok", "service": "aindy-api", "timestamp": str, "components": { "api": "alive" } }`
Status Codes: 200
Observability: emits `health.liveness.completed` on success. Event persistence is best-effort so liveness remains a liveness check.

`GET /ready`
Method: GET
Request Body: None
Query Params: None
Response: `{ "status": "ready", "timestamp": str, "components": { "database": "ready", ... } }`
Status Codes: 200, 503
Observability: emits `health.readiness.completed` on success. Event persistence is best-effort so readiness remains a readiness check.

`GET /health/details`
Method: GET
Request Body: None
Query Params: None
Auth: API key required
Response: detailed component status object
Status Codes: 200

### Health Dashboard Routes (`AINDY/routes/health_dashboard_router.py`, prefix `/dashboard`)
`GET /dashboard/health`
Method: GET
Request Body: None
Query Params: `limit` (default 20)
Response: `{ "count": int, "logs": [ {timestamp, status, avg_latency_ms, components, api_endpoints} ] }`
Status Codes: 200
Auth: JWT required
Errors: Not explicitly defined.

### Social Routes (`AINDY/routes/social_router.py`, prefix `/social`)
`POST /social/profile`
Method: POST
Request Body: `SocialProfile` (`AINDY/db/models/social_models.py`)
Query Params: None
Response: success envelope with profile payload in `data`
Status Codes: 200
Errors: Not explicitly defined.

`GET /social/profile/{username}`
Method: GET
Request Body: None
Query Params: None
Response: success envelope with profile payload in `data`
Status Codes: 200, 404 if profile not found.

`POST /social/post`
Method: POST
Request Body: `SocialPost` (`AINDY/db/models/social_models.py`)
Query Params: None
Response: success envelope with post payload in `data`
Status Codes: 200
Errors: Not explicitly defined; memory bridge logging errors are swallowed.

`GET /social/feed`
Method: GET
Request Body: None
Query Params: `limit` (default 20), `trust_filter` (optional)
Response: success envelope with `list[FeedItem]` in `data`
Status Codes: 200
Errors: Not explicitly defined.

`POST /social/posts/{post_id}/interact`
Method: POST
Request Body: `SocialInteractionRequest`
Query Params: None
Response: success envelope with interaction metrics payload in `data`
Status Codes: 200, 404 if post not found, 422 if action invalid.

`GET /social/analytics`
Method: GET
Request Body: None
Query Params: None
Response: success envelope with analytics summary payload in `data`
Status Codes: 200

### Analytics Routes (`AINDY/routes/analytics_router.py`, prefix `/analytics`)
`POST /analytics/linkedin/manual`
Method: POST
Request Body: `LinkedInRawInput` (`AINDY/schemas/analytics.py`)
Query Params: None
Response: ORM `CanonicalMetricDB` object.
Status Codes: 200, 404 if MasterPlan not found.
Notes: route now enters the route execution pipeline but preserves the ORM response shape.

`GET /analytics/masterplan/{masterplan_id}`
Method: GET
Request Body: None
Query Params: `period_type`, `platform`, `scope_type`
Response: List of `CanonicalMetricDB` ORM objects.
Status Codes: 200
Errors: Not explicitly defined.
Notes: route now enters the route execution pipeline but preserves the list response shape.

`GET /analytics/masterplan/{masterplan_id}/summary`
Method: GET
Request Body: None
Query Params: `group_by` (optional, e.g., "period")
Response: Summary dict; schema depends on `group_by` and record availability.
Status Codes: 200
Errors: Not explicitly defined.
Notes: route now enters the route execution pipeline and preserves the existing summary payload shape.

### Genesis Routes (`AINDY/routes/genesis_router.py`, prefix `/genesis`) **[JWT auth required]** — Genesis Blocks 1-3 (2026-03-17)

`POST /genesis/session`
Method: POST
Request Body: None
Auth: JWT Bearer (user_id bound from token sub)
Response: success envelope with `{ "session_id": int }` in `data`
Status Codes: 200

`POST /genesis/message`
Method: POST
Request Body: `dict` with `session_id` (int) and `message` (str)
Auth: JWT Bearer
Response: standardized execution envelope from the canonical execution pipeline, with Genesis reply data contained in `result`.
Status Codes: 200, 400 on missing fields, 404 if session not found or not owned by user.
Notes: `synthesis_ready` is a one-way flag — once True, never reverts to False.

`GET /genesis/session/{session_id}`
Method: GET
Auth: JWT Bearer
Response: success envelope with session payload in `data`
Status Codes: 200, 404 if not found or not owned.

`GET /genesis/draft/{session_id}`
Method: GET
Auth: JWT Bearer
Response: success envelope with draft payload in `data`
Status Codes: 200, 404 if no draft yet (run /synthesize first) or session not owned.

`POST /genesis/synthesize`
Method: POST
Request Body: `dict` with `session_id` (int)
Auth: JWT Bearer
Response: success envelope with `{ "draft": <synthesis object> }` in `data`, or queued envelope on async execution
Status Codes: 200, 400 on missing session_id, 404 if session not owned, 422 if `synthesis_ready` is False.
Notes: Persists draft to `session.draft_json`. Rate limited: 5/minute.

`POST /genesis/lock`
Method: POST
Request Body: `dict` with `session_id` (int) and `draft` (object)
Auth: JWT Bearer
Response: success envelope with masterplan lock payload in `data`
Status Codes: 200, 400 on missing fields or session already locked.

`POST /genesis/{plan_id}/activate`
Method: POST
Request Body: None
Auth: JWT Bearer
Response: `{ "status": "activated" }`
Status Codes: 200, 404 if plan not found or not owned by user.
Notes: Deactivates all other plans for the user first (single active plan invariant).

### MasterPlan Routes (`AINDY/routes/masterplan_router.py`, prefix `/masterplans`) **[JWT auth required]** — Genesis Block 1 (2026-03-17)

`GET /masterplans/`
Method: GET
Auth: JWT Bearer
Response: Array of `{ id, version_label, posture, status, is_active, created_at, locked_at, activated_at }`
Status Codes: 200
Notes: Returns only plans owned by current user.

`GET /masterplans/{plan_id}`
Method: GET
Auth: JWT Bearer
Response: `{ id, version_label, posture, status, is_active, structure_json, created_at, locked_at, activated_at, linked_genesis_session_id }`
Status Codes: 200, 404 if not found or not owned.

`POST /masterplans/{plan_id}/lock`
Method: POST
Auth: JWT Bearer
Response: `{ "plan_id": int, "status": "locked" }`
Status Codes: 200, 400 if already locked, 404 if not found or not owned.

`POST /masterplans/{plan_id}/activate`
Method: POST
Auth: JWT Bearer
Response: `{ "status": "activated", "plan_id": int }`
Status Codes: 200, 404 if not found or not owned.
Notes: Deactivates all other user plans first.

### Identity Routes (`AINDY/routes/identity_router.py`, prefix `/identity`) **[JWT auth required]** — Memory Bridge v5 Phase 2 (2026-03-19)

`GET /identity/boot`
Method: GET
Auth: JWT Bearer
Response:
```json
{
  "user_id": "uuid",
  "memory": [
    {
      "id": "uuid",
      "content": "string",
      "tags": [],
      "node_type": "decision|outcome|insight|relationship",
      "source_agent": "string|null",
      "extra": {
        "context": "identity_boot"
      },
      "context": "identity_boot",
      "created_at": "iso8601",
      "updated_at": "iso8601"
    }
  ],
  "runs": [ ...recent AgentRun summaries... ],
  "metrics": {
    "user_id": "uuid",
    "score": 0.0,
    "trajectory": "baseline",
    "master_score": 0.0,
    "kpis": { ... },
    "metadata": { ... }
  },
  "flows": [ ...active FlowRun summaries... ],
  "system_state": {
    "memory_count": 0,
    "active_runs": 0,
    "score": 0.0,
    "active_flows": 0
  }
}
```
Status Codes: 200, 401, 500.
Notes:
- This is the canonical post-auth hydration endpoint for the React app.
- Memory is user-scoped, recent, and deterministically ordered by `created_at DESC, id DESC`.
- Returned memory rows are tagged with `context = "identity_boot"`.
- Immediately after signup, boot should include the seeded memory node, one initialized run, and baseline metrics.
- A required `identity.boot` `SystemEvent` is emitted before success is returned; event-persistence failure is fail-closed.

`GET /identity/`
Method: GET
Auth: JWT Bearer
Response: Identity profile summary with communication, tools, decision_making, learning, evolution blocks.
Status Codes: 200, 401.

`PUT /identity/`
Method: PUT
Auth: JWT Bearer
Request Body: `UpdateIdentityRequest` (inline Pydantic model)
- `tone`, `preferred_languages`, `preferred_tools`, `avoided_tools`
- `risk_tolerance`, `speed_vs_quality`
- `learning_style`, `detail_preference`
- `communication_notes`, `decision_notes`, `learning_notes`
Response: `{ "changes_recorded": int, "changes": [...], "profile": {...} }`
Status Codes: 200, 401, 422.
Notes: Invalid enum values are silently ignored in service validation.

`GET /identity/evolution`
Method: GET
Auth: JWT Bearer
Response: Evolution summary with observation_count, total_changes, dimensions_evolved, recent_changes.
Status Codes: 200, 401.

`GET /identity/context`
Method: GET
Auth: JWT Bearer
Response: `{ "context": str, "is_empty": bool, "message": str }`
Status Codes: 200, 401.

### Observability Routes (`AINDY/routes/observability_router.py`, prefix `/observability`) **[JWT auth required]**

`GET /observability/requests`
Method: GET
Query Params:
- `limit` (int, default 50, max 200)
- `error_limit` (int, default 25, max 200)
- `window_hours` (int, default 24, max 168)
Response:
```
{
  "summary": {
    "total_requests": int,
    "window_hours": int,
    "window_requests": int,
    "total_errors": int,
    "window_errors": int,
    "avg_latency_ms": float
  },
  "recent": [ { request_id, method, path, status_code, duration_ms, created_at } ],
  "recent_errors": [ { request_id, method, path, status_code, duration_ms, created_at } ]
}
```
Status Codes: 200, 401.

## 3. Genesis API Contract (Current Implementation — Genesis Blocks 1-3)
- `POST /genesis/session` binds `user_id` (UUID) from JWT `sub`. All subsequent queries scoped to that user.
- `POST /genesis/message` persists `synthesis_ready` as one-way flag (True ? never False). `synthesis_ready` returned reflects DB value, not LLM flag.
- `POST /genesis/synthesize` requires `synthesis_ready == True`; returns 422 otherwise. Persists `draft_json` to session. Calls real GPT-4o.
- Posture is one of `Stable | Accelerated | Aggressive | Reduced` (determined by `ambition_score` + `time_horizon_years`).
- `POST /genesis/lock` validates session ownership before delegating to `create_masterplan_from_genesis(user_id=...)`.
- `masterplan_router` manages plans independently; all queries user-scoped.

## 4. Memory Bridge API Contract (Current Implementation)
- `POST /bridge/nodes` and `POST /bridge/link` no longer require HMAC permissions; JWT is the write guard. `permission` is accepted but ignored for backward compatibility.
- Signature enforcement: deprecated; JWT is the write guard.
- `GET /bridge/nodes` supports tag search with `mode` and `limit` parameters.

## 5. Network Gateway Integration (Current Implementation)
- `POST /network_bridge/connect` expects `NetworkHandshake` with:
- `author_name` (required)
- `platform` (required)
- `connection_type` (default `BridgeHandshake`)
- `notes` (optional)
- No explicit validation beyond Pydantic schema.

## 6. ARM / DeepSeek / Research Routes (Current Implementation)
- ARM endpoints are synchronous from the HTTP caller perspective; underlying analysis/generation functions call the OpenAI API synchronously and may be long-running (typically 5–30s depending on file size and model load).
- ARM `POST /arm/analyze` and `POST /arm/generate` are rate-limited to 10/min per IP to prevent cost runaway.
- ARM responses include Infinity Algorithm metrics: `task_priority` (TP = C×U/R) and `execution_speed` (tokens/second).
- ARM DB persistence: `analysis_results` table records every call (including failures) for audit trail; `code_generations` table records every generation. Both use UUID PKs.
- ARM runtime uses OpenAI GPT-4o via `apps/arm/services/deepseek/deepseek_code_analyzer.py` (legacy "DeepSeek" namespace; `services/deepseek_arm_service.py` is not used by the router).
- Research endpoints are synchronous and persist results; they do not implement async or background execution.
- ARM, Genesis, Research, LeadGen, Embedding, YouTube, Watcher delivery, and Health probe outbound calls now emit required external-call `SystemEvent` records.

## 7. Error Response Shape (Current Implementation)
- Core app-level exception handlers normalize errors into JSON with `error`, `message`, and `details`.
- Route-level `HTTPException(detail=...)` payloads still vary by endpoint, but they no longer rely purely on FastAPI default string handling at the app boundary.
- Unhandled exceptions are converted to a structured 500 response by `main.py`.

## 8. Response Consistency Rules (Policy Requirements)
- All API responses must be JSON (no HTML error pages).
- All errors must follow the standardized structure defined in `docs/governance/ERROR_HANDLING_POLICY.md`.
- Response schema changes require:
- Update to this document.
- Route-level integration test updates.
- Human approval if breaking change.

### Frontend Consumer Guardrails
- The React client applies a defensive normalization pass in `client/src/api.js` after `JSON.parse(...)` succeeds.
- Known array fields such as `items`, `results`, `runs`, `steps`, `nodes`, `logs`, `plans`, `suggestions`, `recent_*`, and related list payloads are coerced to `[]` when the server returns `null`, `undefined`, or another non-array shape.
- This does not change the server contract. It is a frontend hardening layer to prevent `TypeError: .map is not a function` during rendering.
- Frontend components are expected to use `safeMap(...)` from `client/src/utils/safe.js` rather than direct `.map(...)` calls on API-derived values.

## 9. Known Gaps
- Many routes do not declare response models and return ORM objects or dicts without schema enforcement.
- Error handling is still not perfectly uniform at the route level, but silent-failure `pass` blocks have been removed from active production execution paths.
- Some endpoints accept query parameters where request bodies might be expected (e.g., `/authorship/reclaim`, `/freelance/deliver/{order_id}`).
- Masterplan SaaS provides Genesis and MasterPlan lifecycle endpoints only; no API exists for masterplan anchors, ETA projection, or dependency cascade outputs.
- Not every domain has a first-class `ExecutionRecord` table yet; external-call event coverage is broader than full execution-envelope coverage.

## Appendix: Route-to-Schema Map
This appendix lists request schemas where they are explicitly defined.

- `AINDY/routes/analytics_router.py` ? `AINDY/schemas/analytics.py` (`LinkedInRawInput`)
- `AINDY/routes/arm_router.py` ? inline Pydantic models in `AINDY/routes/arm_router.py` (`AnalyzeRequest`, `GenerateRequest`, `ConfigUpdateRequest`) — updated Phase 1 (2026-03-17)
- `AINDY/routes/bridge_router.py` ? inline Pydantic models in `AINDY/routes/bridge_router.py` (`NodeCreateRequest`, `LinkCreateRequest`, `TracePermission`)
- `AINDY/routes/freelance_router.py` ? `AINDY/schemas/freelance.py` (`FreelanceOrderCreate`, `FeedbackCreate`)
- `AINDY/routes/genesis_router.py` ? untyped `dict` payloads (no Pydantic models defined)
- `AINDY/routes/leadgen_router.py` ? query parameter only (`query`); no Pydantic body model
- `AINDY/routes/main_router.py` ? `AINDY/schemas/analytics_inputs.py` (`TaskInput`, `EngagementInput`, etc.), `AINDY/schemas/batch.py` (`BatchInput`), `AINDY/schemas/masterplan.py` (`MasterPlanInput`)
- `AINDY/routes/research_results_router.py` ? `AINDY/schemas/research_results_schema.py` (`ResearchResultCreate`)
- `AINDY/routes/seo_routes.py` ? `AINDY/services/seo.py` (`SEOInput`, `MetaInput`)
- `AINDY/routes/social_router.py` ? `AINDY/db/models/social_models.py` (`SocialProfile`, `SocialPost`, `FeedItem`)
- `AINDY/routes/task_router.py` ? `AINDY/schemas/task_schemas.py` (`TaskCreate`, `TaskAction`)

Response schema sources (routes with `response_model`):
- `AINDY/routes/bridge_router.py` ? inline models (`NodeResponse`, `NodeSearchResponse`, `LinkResponse`)
- `AINDY/routes/freelance_router.py` ? `AINDY/schemas/freelance.py` (`FreelanceOrderResponse`, `FeedbackResponse`, `RevenueMetricsResponse`)
- `AINDY/routes/research_results_router.py` ? `AINDY/schemas/research_results_schema.py` (`ResearchResultResponse`)
- `AINDY/routes/social_router.py` ? `AINDY/db/models/social_models.py` (`SocialProfile`, `SocialPost`, `FeedItem`)

Routes returning ORM objects without `response_model` declarations:
- `AINDY/routes/analytics_router.py`:
- `POST /analytics/linkedin/manual` returns `CanonicalMetricDB`
- `GET /analytics/masterplan/{masterplan_id}` returns list of `CanonicalMetricDB`
- `AINDY/routes/main_router.py`:
- `GET /results` returns list of `CalculationResult`
- `POST /create_masterplan` returns `MasterPlan` (both duplicate handlers)
- `GET /masterplans` returns list of `MasterPlan`
- `AINDY/routes/rippletrace_router.py`:
- `POST /rippletrace/drop_point` returns `DropPointDB`
- `POST /rippletrace/ping` returns `PingDB`
- `GET /rippletrace/ripples/{drop_point_id}` returns list of `PingDB`
- `GET /rippletrace/drop_points` returns list of `DropPointDB`
- `GET /rippletrace/pings` returns list of `PingDB`
- `GET /rippletrace/recent` returns list of `PingDB`

Serialization note (current behavior):
- These routes rely on FastAPI's default serialization of SQLAlchemy ORM objects.
- Potential issues include:
- Datetime fields being serialized to strings implicitly (format is not explicitly controlled).
- Relationship fields (if present on returned models) may not serialize as intended or may be omitted.
- If lazy-loaded relationships are accessed during serialization, it can trigger additional DB queries.
- Higher-risk models with relationship fields:
- `MasterPlan` (`AINDY/db/models/masterplan.py`) includes `canonical_metrics` relationship; endpoints returning `MasterPlan` or lists of `MasterPlan` may trigger lazy-load or serialization issues.
- Other ORM relationships present (lower risk based on current route returns):
- `MasterPlan.parent` (self-referential) in `AINDY/db/models/masterplan.py`; same risk surface as above.
- `ARMRun.logs` and `ARMLog.run` in `AINDY/db/models/arm_models.py` (legacy models, no longer used by ARM router); `AnalysisResult.generations` and `CodeGeneration.analysis` (Phase 1 models); ARM routes return dicts, not ORM objects.
- `ClientFeedback.order` in `AINDY/apps/freelance/models/freelance.py`; freelance routes use `response_model` schemas that do not expose the relationship.
### Watcher Routes (`AINDY/routes/watcher_router.py`, prefix `/watcher`)
`POST /watcher/signals`
Method: POST
Request Body:
```json
{
  "signals": [
    {
      "signal_type": "session_started|session_ended|distraction_detected|focus_achieved|context_switch|heartbeat",
      "session_id": "uuid-string",
      "timestamp": "ISO-8601 timestamp",
      "app_name": "string",
      "window_title": "string",
      "activity_type": "work|communication|distraction|idle|unknown",
      "metadata": {},
      "user_id": "optional user UUID"
    }
  ]
}
```
Auth: API key required
Response:
```json
{
  "accepted": 1,
  "session_ended_count": 0,
  "orchestration": {
    "eta_recalculated": false,
    "score_orchestrated": false,
    "next_action": null
  }
}
```
Status Codes: 201, 401, 422, 500
Notes:
- The route validates signal type, activity type, timestamp, and optional `user_id` before execution.
- Persistence and orchestration run through the canonical `watcher_ingest` flow internally.
- Public response shape is an explicit ingestion contract, not the generic execution envelope.

`GET /watcher/signals`
Method: GET
Query Params: `session_id`, `signal_type`, `user_id`, `limit`, `offset`
Auth: API key required
Response: `SignalResponse[]`
Status Codes: 200, 401, 422

