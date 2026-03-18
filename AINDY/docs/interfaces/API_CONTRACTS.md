# API Contracts

This document formalizes the current FastAPI HTTP interface based strictly on implemented routes. It separates current behavior from policy requirements and does not introduce new endpoints.

## 1. Route Inventory

Routers registered in `AINDY/main.py` via `AINDY/routes/__init__.py`:
- `AINDY/routes/seo_routes.py` (no router prefix) **[JWT auth required]**
- `AINDY/routes/task_router.py` (prefix `/tasks`) **[JWT auth required]** · `/tasks/recurrence/check` public
- `AINDY/routes/bridge_router.py` (prefix `/bridge`) **[JWT auth required for /nodes and /link; API key required for /user_event]**
- `AINDY/routes/authorship_router.py` (prefix `/authorship`) **[JWT auth required]**
- `AINDY/routes/rippletrace_router.py` (prefix `/rippletrace`) **[JWT auth required]**
- `AINDY/routes/network_bridge_router.py` (prefix `/network_bridge`) **[API key required]**
- `AINDY/routes/db_verify_router.py` (prefix `/db`) **[API key required]**
- `AINDY/routes/research_results_router.py` (prefix `/research`) **[JWT auth required]**
- `AINDY/routes/main_router.py` (no router prefix) **[JWT auth required]** — calculation math API, secured Sprint 4
- `AINDY/routes/freelance_router.py` (prefix `/freelance`) **[JWT auth required]**
- `AINDY/routes/arm_router.py` (prefix `/arm`) **[JWT auth required]**
- `AINDY/routes/leadgen_router.py` (prefix `/leadgen`) **[JWT auth required]**
- `AINDY/routes/dashboard_router.py` (prefix `/dashboard`) **[JWT auth required]**
- `AINDY/routes/health_router.py` (prefix `/health`) **[public]**
- `AINDY/routes/health_dashboard_router.py` (prefix `/dashboard`) **[public]**
- `AINDY/routes/social_router.py` (prefix `/social`) **[JWT auth required]**
- `AINDY/routes/analytics_router.py` (prefix `/analytics`) **[JWT auth required]**
- `AINDY/routes/genesis_router.py` (prefix `/genesis`) **[JWT auth required]**
- `AINDY/routes/auth_router.py` (prefix `/auth`) **[public — provides tokens]**
- `AINDY/routes/masterplan_router.py` (prefix `/masterplans`) **[JWT auth required]**
- `AINDY/routes/memory_router.py` (prefix `/memory`) **[JWT auth required]**

**Authentication model (Sprint 4 Auth Hardening — complete as of 2026-03-18):**
- **JWT Bearer token** — obtain via `POST /auth/login`; pass as `Authorization: Bearer <token>`. Required on: tasks, leadgen, genesis, analytics, seo, authorship, arm, rippletrace, freelance, research, dashboard, social, memory, **all calculation math routes** (`/calculate_twr`, `/calculate_engagement`, etc.), `/bridge/nodes`, `/bridge/link`.
- **API key** (`X-API-Key` header) — required on: `network_bridge_router` (service-to-service from Node.js gateway), `db_verify_router` (admin schema inspection), `/bridge/user_event`. Key value from `AINDY_API_KEY` env var.
- **HMAC permission** — no longer used as the sole write guard on `/bridge`. JWT is the primary auth on bridge write routes.
- **Public routes** (no auth): `/auth/*`, `/health/*`, `/dashboard/health`, `GET /`, `/tasks/recurrence/check`.
- Zero unprotected non-public routes as of Sprint 4 (2026-03-18).

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

**Memory Bridge Phase 1 additions (2026-03-18):**
- `POST /memory/nodes` — JWT required. Body: `CreateNodeRequest {content, source?, tags?, node_type?, extra?}`. Persists a memory node. Returns node dict. Status 201.
- `GET /memory/nodes/{node_id}` — JWT required. Returns node dict or 404.
- `GET /memory/nodes/{node_id}/links` — JWT required. Query param: `direction` (`in`|`out`|`both`, default `both`). Returns `{"nodes": [...]}`. 404 if node not found, 422 if direction invalid.
- `GET /memory/nodes` — JWT required. Query params: `tags` (comma-separated), `mode` (`AND`|`OR`, default `AND`), `limit` (default 50). Returns `{"nodes": [...]}`.
- `POST /memory/links` — JWT required. Body: `CreateLinkRequest {source_id, target_id, link_type?}`. Returns link dict. Status 201. 422 if nodes don't exist or same ID.

**Memory Bridge Phase 2 additions (2026-03-18):**
- `POST /memory/nodes/search` — JWT required. Body: `SimilaritySearchRequest {query, limit?, node_type?, min_similarity?}`. Returns `{"query", "results", "count"}` with semantic `similarity` and `distance`.
- `POST /memory/recall` — JWT required. Body: `RecallRequest {query?, tags?, limit?, node_type?}`. Returns resonance-scored results and scoring metadata. 400 if neither `query` nor `tags` provided.

**Memory Bridge v3 additions (2026-03-18):**
- `PUT /memory/nodes/{node_id}` — JWT required. Body: `UpdateNodeRequest {content?, tags?, node_type?, source?}`. Updates a memory node and records history (previous values).
- `GET /memory/nodes/{node_id}/history` — JWT required. Query: `limit` (default 20). Returns `{node_id, history, count}` ordered by `changed_at DESC`.
- `GET /memory/nodes/{node_id}/traverse` — JWT required. Query: `max_depth` (default 3, capped at 5), `link_type` (optional), `min_strength` (default 0.0). Returns DFS chain plus narrative.
- `POST /memory/nodes/expand` — JWT required. Body: `ExpandRequest {node_ids, include_linked?, include_similar?, limit_per_node?}`. Returns expanded context graph; max 10 input nodes.
- `POST /memory/recall/v3` — JWT required. Body: `RecallV3Request {query?, tags?, limit?, node_type?, expand_results?}`. Returns standard recall or expanded context when `expand_results=true`.

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

`POST /auth/register`
Method: POST
Request Body: `{ "email": str, "password": str, "username": str }`
Query Params: None
Response: `{ "access_token": str, "token_type": "bearer" }`
Status Codes: 201, 409
Errors: 409 if email already registered.
Auth: None (public endpoint)

### Root Route (`AINDY/main.py`)
`GET /`
Method: GET
Request Body: None
Query Params: None
Response: `{ "message": "A.I.N.D.Y. API is running!" }`
Status Codes: 200
Errors: Not explicitly defined.

### SEO Routes (`AINDY/routes/seo_routes.py`)
`POST /analyze_seo/`
Method: POST
Request Body: `ContentInput` (inline Pydantic model with `content: str`)
Query Params: None
Response: `{ "word_count": int, "readability": number, "top_keywords": [str], "keyword_densities": {str: number} }`
Status Codes: 200
Errors: Not explicitly defined.

`POST /generate_meta/`
Method: POST
Request Body: `ContentInput`
Query Params: None
Response: `{ "meta_description": str }`
Status Codes: 200
Errors: Not explicitly defined.

`POST /suggest_improvements/`
Method: POST
Request Body: `ContentInput`
Query Params: None
Response: `{ "seo_suggestions": str }`
Status Codes: 200
Errors: Not explicitly defined.

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
Status Codes: 200
Errors: Not explicitly defined.

`POST /tasks/recurrence/check`
Method: POST
Request Body: None
Query Params: None
Response: `{ "message": "Recurrence job started in background." }`
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
- `permission: TracePermission`
Query Params: None
Response: `NodeResponse` with `id`, `content`, `tags`, `node_type`, `extra`.
Status Codes: 201
Errors: 403 on invalid HMAC signature or expired TTL.

`GET /bridge/nodes`
Method: GET
Request Body: None
Query Params: `tag` (list), `mode` (default "OR"), `limit` (default 100)
Response: `NodeSearchResponse` with `nodes: [NodeResponse]`.
Status Codes: 200
Errors: Not explicitly defined.

`POST /bridge/link`
Method: POST
Request Body: `LinkCreateRequest` (inline Pydantic model) with fields:
- `source_id: str`
- `target_id: str`
- `link_type: str`
- `permission: TracePermission`
Query Params: None
Response: `LinkResponse` with `id`, `source_node_id`, `target_node_id`, `link_type`, `strength`, `created_at`.
Status Codes: 201
Errors: 403 on invalid HMAC signature or expired TTL; 400 on invalid IDs (from `ValueError`) is not explicitly mapped.

`POST /bridge/user_event`
Method: POST
Request Body: `UserEvent` (inline Pydantic model with `user`, `origin`, optional `timestamp`)
Query Params: None
Response: `{ "status": "logged", "user": str, "origin": str, "timestamp": str }`
Status Codes: 200
Errors: Not explicitly defined.

### Authorship Routes (`AINDY/routes/authorship_router.py`, prefix `/authorship`)
`POST /authorship/reclaim`
Method: POST
Request Body: None (parameters are plain function arguments)
Query Params: `content`, `author` (default), `motto` (default)
Response: Output of `services.authorship_services.reclaim_authorship` (schema not explicitly defined).
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
Response: `ResearchResultResponse`
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
Response: `ResearchResultResponse`
Status Codes: 200
Errors: Not explicitly defined.

### Main Calculation & Masterplan Routes (`AINDY/routes/main_router.py`, no prefix)
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
Response: Dict of metric names to values as returned by `services.calculations.process_batch`.
Status Codes: 200
Errors: Not explicitly defined.

`GET /results`
Method: GET
Request Body: None
Query Params: None
Response: List of `CalculationResult` ORM objects.
Status Codes: 200
Errors: Not explicitly defined.

`POST /create_masterplan`
Method: POST
Request Body: `MasterPlanCreate` (`AINDY/schemas/masterplan.py`)
Query Params: None
Response: ORM `MasterPlan` object.
Status Codes: 200, 400 if origin plan already exists.
Errors: HTTP 400 for duplicate origin; other errors not explicitly handled.

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
Note: There are two `POST /create_masterplan` definitions in `AINDY/routes/main_router.py`. Behavior depends on FastAPI routing order; contract is ambiguous.

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
  in content → 403.

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
Response: `{ "query": str, "count": int, "results": [ {company, url, fit_score, intent_score, data_quality_score, overall_score, reasoning, created_at} ] }`
Status Codes: 200
Errors: Not explicitly defined.

`GET /leadgen/`
Method: GET
Request Body: None
Query Params: None
Response: List of dicts with lead fields.
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

### Health Routes (`AINDY/routes/health_router.py`, prefix `/health`)
`GET /health/`
Method: GET
Request Body: None
Query Params: None
Response: Status dict with `timestamp`, `version`, `components`, `api_endpoints`, `status`, `avg_latency_ms`.
Status Codes: 200
Errors: Not explicitly defined; failures are embedded in response fields.

### Health Dashboard Routes (`AINDY/routes/health_dashboard_router.py`, prefix `/dashboard`)
`GET /dashboard/health`
Method: GET
Request Body: None
Query Params: `limit` (default 20)
Response: `{ "count": int, "logs": [ {timestamp, status, avg_latency_ms, components, api_endpoints} ] }`
Status Codes: 200
Errors: Not explicitly defined.

### Social Routes (`AINDY/routes/social_router.py`, prefix `/social`)
`POST /social/profile`
Method: POST
Request Body: `SocialProfile` (`AINDY/db/models/social_models.py`)
Query Params: None
Response: `SocialProfile`
Status Codes: 200
Errors: Not explicitly defined.

`GET /social/profile/{username}`
Method: GET
Request Body: None
Query Params: None
Response: `SocialProfile`
Status Codes: 200, 404 if profile not found.

`POST /social/post`
Method: POST
Request Body: `SocialPost` (`AINDY/db/models/social_models.py`)
Query Params: None
Response: `SocialPost`
Status Codes: 200
Errors: Not explicitly defined; memory bridge logging errors are swallowed.

`GET /social/feed`
Method: GET
Request Body: None
Query Params: `limit` (default 20), `trust_filter` (optional)
Response: `list[FeedItem]`
Status Codes: 200
Errors: Not explicitly defined.

### Analytics Routes (`AINDY/routes/analytics_router.py`, prefix `/analytics`)
`POST /analytics/linkedin/manual`
Method: POST
Request Body: `LinkedInRawInput` (`AINDY/schemas/analytics.py`)
Query Params: None
Response: ORM `CanonicalMetricDB` object.
Status Codes: 200, 404 if MasterPlan not found.

`GET /analytics/masterplan/{masterplan_id}`
Method: GET
Request Body: None
Query Params: `period_type`, `platform`, `scope_type`
Response: List of `CanonicalMetricDB` ORM objects.
Status Codes: 200
Errors: Not explicitly defined.

`GET /analytics/masterplan/{masterplan_id}/summary`
Method: GET
Request Body: None
Query Params: `group_by` (optional, e.g., "period")
Response: Summary dict; schema depends on `group_by` and record availability.
Status Codes: 200
Errors: Not explicitly defined.

### Genesis Routes (`AINDY/routes/genesis_router.py`, prefix `/genesis`) **[JWT auth required]** — Genesis Blocks 1-3 (2026-03-17)

`POST /genesis/session`
Method: POST
Request Body: None
Auth: JWT Bearer (user_id_str bound from token sub)
Response: `{ "session_id": int }`
Status Codes: 200

`POST /genesis/message`
Method: POST
Request Body: `dict` with `session_id` (int) and `message` (str)
Auth: JWT Bearer
Response: `{ "reply": str, "synthesis_ready": bool }`
Status Codes: 200, 400 on missing fields, 404 if session not found or not owned by user.
Notes: `synthesis_ready` is a one-way flag — once True, never reverts to False.

`GET /genesis/session/{session_id}`
Method: GET
Auth: JWT Bearer
Response: `{ "session_id": int, "status": str, "synthesis_ready": bool, "summarized_state": object, "created_at": datetime, "updated_at": datetime }`
Status Codes: 200, 404 if not found or not owned.

`GET /genesis/draft/{session_id}`
Method: GET
Auth: JWT Bearer
Response: `{ "session_id": int, "draft": object, "synthesis_ready": bool }`
Status Codes: 200, 404 if no draft yet (run /synthesize first) or session not owned.

`POST /genesis/synthesize`
Method: POST
Request Body: `dict` with `session_id` (int)
Auth: JWT Bearer
Response: `{ "draft": <synthesis object> }` — vision_statement, time_horizon_years, primary_mechanism, ambition_score, core_domains, phases, success_criteria, risk_factors, confidence_at_synthesis
Status Codes: 200, 400 on missing session_id, 404 if session not owned, 422 if `synthesis_ready` is False.
Notes: Persists draft to `session.draft_json`. Rate limited: 5/minute.

`POST /genesis/lock`
Method: POST
Request Body: `dict` with `session_id` (int) and `draft` (object)
Auth: JWT Bearer
Response: `{ "masterplan_id": int, "version": str, "posture": str }`
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

## 3. Genesis API Contract (Current Implementation — Genesis Blocks 1-3)
- `POST /genesis/session` binds `user_id_str` from JWT `sub`. All subsequent queries scoped to that user.
- `POST /genesis/message` persists `synthesis_ready` as one-way flag (True → never False). `synthesis_ready` returned reflects DB value, not LLM flag.
- `POST /genesis/synthesize` requires `synthesis_ready == True`; returns 422 otherwise. Persists `draft_json` to session. Calls real GPT-4o.
- Posture is one of `Stable | Accelerated | Aggressive | Reduced` (determined by `ambition_score` + `time_horizon_years`).
- `POST /genesis/lock` validates session ownership before delegating to `create_masterplan_from_genesis(user_id=...)`.
- `masterplan_router` manages plans independently; all queries user-scoped.

## 4. Memory Bridge API Contract (Current Implementation)
- `POST /bridge/nodes` and `POST /bridge/link` require a `permission` object (`TracePermission`) with `nonce`, `ts`, `ttl`, `scopes`, and `signature`.
- TTL enforcement: `permission.ts + permission.ttl < now` triggers HTTP 403.
- Signature enforcement: HMAC SHA-256 over `nonce|ts|ttl|sorted(scopes)`; mismatches return HTTP 403.
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
- Research endpoints are synchronous and persist results; they do not implement async or background execution.

## 7. Error Response Shape (Current Implementation)
- Errors raised with `HTTPException` return JSON of the form `{ "detail": <message> }` (FastAPI default).
- Many routes do not handle errors explicitly; unhandled exceptions propagate to FastAPI default 500 responses.
- Structured error JSON is not consistently implemented.

## 8. Response Consistency Rules (Policy Requirements)
- All API responses must be JSON (no HTML error pages).
- All errors must follow the standardized structure defined in `docs/governance/ERROR_HANDLING_POLICY.md`.
- Response schema changes require:
- Update to this document.
- Route-level integration test updates.
- Human approval if breaking change.

## 9. Known Gaps
- Duplicate route definitions exist for `POST /create_masterplan` in `AINDY/routes/main_router.py`, making the effective contract ambiguous.
- Many routes do not declare response models and return ORM objects or dicts without schema enforcement.
- Error handling is inconsistent; many routes do not catch exceptions.
- Some endpoints accept query parameters where request bodies might be expected (e.g., `/authorship/reclaim`, `/freelance/deliver/{order_id}`).

## Appendix: Route-to-Schema Map
This appendix lists request schemas where they are explicitly defined.

- `AINDY/routes/analytics_router.py` → `AINDY/schemas/analytics.py` (`LinkedInRawInput`)
- `AINDY/routes/arm_router.py` → inline Pydantic models in `AINDY/routes/arm_router.py` (`AnalyzeRequest`, `GenerateRequest`, `ConfigUpdateRequest`) — updated Phase 1 (2026-03-17)
- `AINDY/routes/bridge_router.py` → inline Pydantic models in `AINDY/routes/bridge_router.py` (`NodeCreateRequest`, `LinkCreateRequest`, `TracePermission`)
- `AINDY/routes/freelance_router.py` → `AINDY/schemas/freelance.py` (`FreelanceOrderCreate`, `FeedbackCreate`)
- `AINDY/routes/genesis_router.py` → untyped `dict` payloads (no Pydantic models defined)
- `AINDY/routes/leadgen_router.py` → query parameter only (`query`); no Pydantic body model
- `AINDY/routes/main_router.py` → `AINDY/schemas/analytics_inputs.py` (`TaskInput`, `EngagementInput`, etc.), `AINDY/schemas/batch.py` (`BatchInput`), `AINDY/schemas/masterplan.py` (`MasterPlanCreate`, `MasterPlanInput`)
- `AINDY/routes/research_results_router.py` → `AINDY/schemas/research_results_schema.py` (`ResearchResultCreate`)
- `AINDY/routes/seo_routes.py` → `AINDY/services/seo.py` (`SEOInput`, `MetaInput`) and inline `ContentInput`
- `AINDY/routes/social_router.py` → `AINDY/db/models/social_models.py` (`SocialProfile`, `SocialPost`, `FeedItem`)
- `AINDY/routes/task_router.py` → `AINDY/schemas/task_schemas.py` (`TaskCreate`, `TaskAction`)

Response schema sources (routes with `response_model`):
- `AINDY/routes/bridge_router.py` → inline models (`NodeResponse`, `NodeSearchResponse`, `LinkResponse`)
- `AINDY/routes/freelance_router.py` → `AINDY/schemas/freelance.py` (`FreelanceOrderResponse`, `FeedbackResponse`, `RevenueMetricsResponse`)
- `AINDY/routes/research_results_router.py` → `AINDY/schemas/research_results_schema.py` (`ResearchResultResponse`)
- `AINDY/routes/social_router.py` → `AINDY/db/models/social_models.py` (`SocialProfile`, `SocialPost`, `FeedItem`)

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
- `ClientFeedback.order` in `AINDY/db/models/freelance.py`; freelance routes use `response_model` schemas that do not expose the relationship.
