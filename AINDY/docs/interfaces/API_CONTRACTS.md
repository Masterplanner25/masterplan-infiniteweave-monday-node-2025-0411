# API Contracts

This document formalizes the current FastAPI HTTP interface based strictly on implemented routes. It separates current behavior from policy requirements and does not introduce new endpoints.

## 1. Route Inventory

Routers registered in `AINDY/main.py` via `AINDY/routes/__init__.py`:
- `AINDY/routes/seo_routes.py` (no router prefix)
- `AINDY/routes/task_router.py` (prefix `/tasks`) **[JWT auth required]**
- `AINDY/routes/bridge_router.py` (prefix `/bridge`) **[HMAC auth required for writes]**
- `AINDY/routes/authorship_router.py` (prefix `/authorship`)
- `AINDY/routes/rippletrace_router.py` (prefix `/rippletrace`)
- `AINDY/routes/network_bridge_router.py` (prefix `/network_bridge`)
- `AINDY/routes/db_verify_router.py` (prefix `/db`)
- `AINDY/routes/research_results_router.py` (prefix `/research`)
- `AINDY/routes/main_router.py` (no router prefix)
- `AINDY/routes/freelance_router.py` (prefix `/freelance`)
- `AINDY/routes/arm_router.py` (prefix `/arm`)
- `AINDY/routes/leadgen_router.py` (prefix `/leadgen`) **[JWT auth required]**
- `AINDY/routes/dashboard_router.py` (prefix `/dashboard`)
- `AINDY/routes/health_router.py` (prefix `/health`) **[public]**
- `AINDY/routes/health_dashboard_router.py` (prefix `/dashboard`)
- `AINDY/routes/social_router.py` (prefix `/social`)
- `AINDY/routes/analytics_router.py` (prefix `/analytics`) **[JWT auth required]**
- `AINDY/routes/genesis_router.py` (prefix `/genesis`) **[JWT auth required]**
- `AINDY/routes/auth_router.py` (prefix `/auth`) **[public — provides tokens]**

**Authentication model (Phase 2):**
- JWT Bearer token — obtain via `POST /auth/login`; pass as `Authorization: Bearer <token>`
- Routes without auth annotation are currently unprotected (Phase 3 target)
- Bridge writes use HMAC permission model (separate from JWT)

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

### ARM Routes (`AINDY/routes/arm_router.py`, prefix `/arm`)
`POST /arm/analyze`
Method: POST
Request Body: `AnalyzeInput` (file_path, analysis_type)
Query Params: None
Response: `{ "status": "success", "analysis": str }`
Status Codes: 200, 500 on errors.

`POST /arm/generate`
Method: POST
Request Body: `GenerateInput` (file_path, instructions)
Query Params: None
Response: `{ "status": "success", "generated_code": str }`
Status Codes: 200, 500 on errors.

`GET /arm/logs`
Method: GET
Request Body: None
Query Params: None
Response: List of dicts `{ timestamp, message, level }`.
Status Codes: 200
Errors: Not explicitly defined.

`GET /arm/config`
Method: GET
Request Body: None
Query Params: None
Response: `{ "runtime_config": <dict>, "last_saved": <datetime|None> }`
Status Codes: 200
Errors: Not explicitly defined.

`PUT /arm/config`
Method: PUT
Request Body: `ConfigUpdate` (parameter, value)
Query Params: None
Response: `{ "status": "updated", "parameter": str, "value": <any> }`
Status Codes: 200
Errors: Not explicitly defined.

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

### Genesis Routes (`AINDY/routes/genesis_router.py`, prefix `/genesis`)
`POST /genesis/session`
Method: POST
Request Body: None
Query Params: None
Response: `{ "session_id": int }`
Status Codes: 200
Errors: Not explicitly defined.

`POST /genesis/message`
Method: POST
Request Body: `dict` with `session_id` and `message`
Query Params: None
Response: `{ "reply": str, "synthesis_ready": bool }`
Status Codes: 200, 400 on missing fields, 404 if session not found.

`POST /genesis/synthesize`
Method: POST
Request Body: `dict` with `session_id`
Query Params: None
Response: `{ "draft": <object> }` (shape from `call_genesis_synthesis_llm`)
Status Codes: 200, 400 on missing session_id, 404 if session not found.

`POST /genesis/lock`
Method: POST
Request Body: `dict` with `session_id` and `draft`
Query Params: None
Response: `{ "masterplan_id": int, "version": str, "posture": str }`
Status Codes: 200, 400 on missing fields or lock errors.

`POST /genesis/{plan_id}/activate`
Method: POST
Request Body: None
Query Params: None
Response: `{ "status": "activated" }`
Status Codes: 200, 404 if plan not found.

## 3. Genesis API Contract (Current Implementation)
- `POST /genesis/session` initializes a `GenesisSessionDB` row with a `summarized_state` dict and returns `session_id`.
- `POST /genesis/message` requires `session_id` and `message`; response includes `reply` and `synthesis_ready` from model output.
- Session state is updated by merging `state_update` into `summarized_state`; `confidence` is clamped to [0,1].
- `POST /genesis/synthesize` returns `{ "draft": <object> }` from `call_genesis_synthesis_llm`.
- `POST /genesis/lock` creates a masterplan from a session and marks it locked.

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
- ARM endpoints are synchronous from the HTTP caller perspective; underlying analysis/generation functions are synchronous and may be long-running.
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
- `AINDY/routes/arm_router.py` → inline Pydantic models in `AINDY/routes/arm_router.py` (`AnalyzeInput`, `GenerateInput`, `ConfigUpdate`)
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
- `ARMRun.logs` and `ARMLog.run` in `AINDY/db/models/arm_models.py`; current `/arm/*` routes return dicts, not ORM objects.
- `ClientFeedback.order` in `AINDY/db/models/freelance.py`; freelance routes use `response_model` schemas that do not expose the relationship.
