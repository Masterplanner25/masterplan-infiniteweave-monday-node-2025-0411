# Technical Debt Inventory

This document inventories current technical debt based strictly on the existing implementation. It does not propose redesigns or new systems.

## Current Audit Alignment

This section is the canonical current-state view. Historical notes below are retained for traceability, but any stale statuses should be interpreted through this section first.

### Current Priority Summary

#### Critical

- No current critical debt item is newly confirmed in this audit section. Historical critical items remain below for traceability.

#### High

- **UNRESOLVED:** Real Nodus execution is not the primary execution path for Agentics. Core agent execution still runs through `runtime/flow_engine.py` via `runtime/nodus_adapter.py`, while embedded Nodus execution remains isolated behind `runtime/nodus_execution_service.py`. Primary files: `runtime/nodus_adapter.py`, `runtime/flow_engine.py`, `runtime/nodus_execution_service.py`.
- **UNRESOLVED:** Dual execution surfaces continue to drift architecturally. The internal flow engine and embedded Nodus execution expose different runtime models, semantics, and observability envelopes. Primary files: `runtime/flow_engine.py`, `runtime/nodus_adapter.py`, `runtime/nodus_execution_service.py`, `routes/memory_router.py`.
- **PARTIAL:** Search is materially more unified now that `domain/search_service.py` fronts SEO, LeadGen, and Research, but result history/reuse and full system-wide orchestration are still incomplete. Primary files: `domain/search_service.py`, `domain/leadgen_service.py`, `routes/seo_routes.py`, `routes/research_results_router.py`, `routes/memory_router.py`.
- **PARTIAL:** Execution normalization is still incomplete at the system boundary. Research, LeadGen, Freelance, Agent, Automation, Task, Goals, and Genesis now run through the centralized execution wrapper or canonical execution envelopes, and `/system/state` now returns the shared success envelope, but other route groups in the repo still return raw JSON or direct route-level envelopes outside the same wrapper/event lifecycle. Primary files: `core/execution_service.py`, `routes/research_results_router.py`, `routes/leadgen_router.py`, `routes/freelance_router.py`, `routes/system_state_router.py`, `routes/agent_router.py`, `routes/automation_router.py`, `routes/task_router.py`, `routes/goals_router.py`, `routes/genesis_router.py`.

#### Medium

- **PARTIAL:** RippleTrace now includes execution-causality structure on top of `SystemEvent`, including parent-child edges, event->memory links, and a proofboard-style viewer, but broader productization and deeper scenario coverage remain incomplete. Primary files: `core/system_event_service.py`, `domain/rippletrace_service.py`, `db/models/ripple_edge.py`, `client/src/components/RippleTraceViewer.jsx`.
- **PARTIAL:** Freelancing remains incomplete. AI delivery generation, execution metrics, and external email/webhook delivery now exist, but payment-provider integration is still stubbed and broader commercial workflow automation remains incomplete. Primary files: `domain/freelance_service.py`, `routes/freelance_router.py`, `db/models/freelance.py`, `domain/automation_execution_service.py`.
- **PARTIAL:** Infinity is now memory-weighted, system-state-aware, goal-aware, and expected-vs-actual-aware, but optimization depth remains shallow. Watcher, feedback, ranked memory signals, and prediction accuracy now feed decisions, yet KPI-weight learning and broader policy adaptation are still missing. Primary files: `domain/infinity_service.py`, `domain/infinity_loop.py`, `memory/memory_scoring_service.py`, `platform_layer/system_state_service.py`, `routes/main_router.py`.
- **UNRESOLVED:** ARM analyzer config updates remain process-local across instances. Primary file: `routes/arm_router.py`.
- **RESOLVED:** Mongo is now a fail-fast runtime dependency. `config.py` rejects missing `MONGO_URL`, `db/mongo_setup.py` eagerly pings on startup, and `main.py` initializes Mongo during lifespan. Primary files: `config.py`, `db/mongo_setup.py`, `main.py`.
- **UNRESOLVED:** Logging is still not fully standardized. `print(...)` remains in database/bootstrap paths. Primary files: `db/database.py`, `db/create_all.py`.
- **RESOLVED:** Memory embedding generation is now asynchronous and retryable. Memory writes persist immediately with `embedding_status`, enqueue background embedding work, and retrieval falls back when embeddings are not ready. Primary files: `db/dao/memory_node_dao.py`, `memory/embedding_jobs.py`, `platform_layer/async_job_service.py`, `memory/memory_persistence.py`.
- **PARTIAL:** Multi-agent coordination primitives now exist, including registry, coordinator, message bus, cross-agent trace fields, and coordination endpoints, but real distributed execution and conflict-heavy runtime behavior remain immature. Primary files: `agents/agent_coordinator.py`, `agents/agent_message_bus.py`, `agents/agent_runtime.py`, `db/models/agent_registry.py`, `routes/coordination_router.py`.
- **PARTIAL:** Rust/C++ memory scoring acceleration is now integrated into the runtime hot path with Python fallback, but release-build deployment and broader traversal-side acceleration are still incomplete. Primary files: `runtime/memory/scorer.py`, `runtime/memory/native_scorer.py`, `bridge/memory_bridge_rs/src/lib.rs`.
- **RESOLVED:** Memory auto-link tag lookup is now cross-dialect aware. PostgreSQL keeps native tag containment queries, while SQLite/non-PostgreSQL backends fall back to Python-side tag filtering for consistent auto-link candidate lookup. Primary files: `memory/memory_capture_engine.py`, `db/dao/memory_node_dao.py`, `memory/memory_persistence.py`.
- **PARTIAL:** Live route-level learning behavior is not yet consistently visible even though the causal-learning loop tests pass. Repeated real API executions can succeed without showing recalled memory in route payload context. Primary files: `routes/research_results_router.py`, `runtime/memory/*`, `memory/memory_scoring_service.py`, `domain/infinity_orchestrator.py`.

#### Low

- **PARTIAL:** Cache backend is configurable for Redis, but in-memory remains the default and multi-instance correctness still depends on explicit deployment configuration. Primary files: `config.py`, `routes/health_router.py`.
- **UNRESOLVED:** No documented secret rotation policy. Primary files: `config.py`, bridge/auth deployment settings.
- **UNRESOLVED:** Legacy/archive residue remains under `bridge/archive/` and similar compatibility paths, increasing maintenance drag.

### Stale Historical Entries Corrected By This Audit

The following historical items below should now be treated as resolved or updated:

- MasterPlan anchor and ETA projection are implemented.
- RippleTrace pattern engine, graph layer, and frontend viewer are implemented.
- Observability frontend dashboard is implemented.
- Agent approval inbox is implemented.
- `IdentityService.get_evolution_summary()` now returns a normalized new-user shape and should no longer be treated as open.
- `WatcherSignal.user_id` is now UUID-backed with a foreign key, so the older String-based note is stale.

## 1. Structural Debt
- ? **FULLY RESOLVED (2026-03-22 Flow Engine Phase A):** All 3 daemon threads (`threading.Thread(daemon=True)`) eliminated from `task_services.py`. Replaced with APScheduler `BackgroundScheduler` + tenacity retry. `AutomationLog` model provides full audit trail and replay via `POST /automation/logs/{id}/replay`. System jobs (`task_reminder_check`, `cleanup_stale_logs`, `task_recurrence_check`) registered in `scheduler_service._register_system_jobs()`.
- ? **RESOLVED (Flow Engine Phase A):** Long-running loop variants in `task_services.py` replaced by APScheduler scheduled jobs.
- ? **RESOLVED (2026-03-22):** Gateway (`AINDY/server.js`) now reads persisted authors via `/network_bridge/authors` (no in-memory user array).
- ? **RESOLVED (2026-03-22):** Gateway state durability now backed by `authors` table via `/network_bridge/authors`.
-
- ? **PARTIALLY RESOLVED (2026-03-22):** Cache backend can be configured for Redis via `AINDY_CACHE_BACKEND=redis` and `REDIS_URL`. Default remains in-memory, so multi-instance consistency requires explicit config.
- ARM analyzer config updates are process-local; multi-instance propagation requires restarts or explicit reload across instances (`AINDY/routes/arm_router.py`).
- Search System remains fragmented across SEO, LeadGen, and Research modules; Memory Orchestrator recall is integrated in LeadGen + Research query flow. Leadgen uses best-effort external retrieval with minimal structured parsing; richer provider-backed parsing is still missing. Canonical reference: `docs/roadmap/SEARCH_SYSTEM.md`.
- Freelancing System lacks automation and AI generation; metrics are incomplete. Canonical reference: `docs/roadmap/FREELANCING_SYSTEM.md`.
- ? **RESOLVED (2026-03-21):** Social Layer visibility scoring + bridge event persistence implemented; social posts now log to Memory Bridge with DB session. Canonical reference: `docs/roadmap/SOCIAL_LAYER.md`.
- RippleTrace is **partially implemented** beyond signal capture; pattern services, graph logic, and a frontend viewer now exist, but execution-causality tracing and the full insight layer remain incomplete. Canonical reference: `docs/roadmap/RIPPLETRACE.md`.
- Masterplan SaaS no longer lacks anchor/ETA support; the remaining debt is dependency cascade modeling and execution automation on top of the existing planning + activation layer. Canonical reference: `docs/roadmap/MASTERPLAN_SAAS.md`.
- ? **FIXED (2026-03-18 Sprint 4):** `main.py` deprecated `@app.on_event("startup")` handlers replaced with a single `@asynccontextmanager lifespan` function. Both startup handlers (cache init + system identity seeder) merged into one lifespan. Deprecation warnings eliminated (11 ? 7 warnings in test suite).
- ? **FIXED (2026-03-18 Sprint 4 Auth Hardening):** Pydantic v1 deprecations removed — `schemas/freelance.py` (3× `class Config: orm_mode = True` ? `model_config = ConfigDict(from_attributes=True)`), `schemas/analytics_inputs.py` (`@validator` ? `@field_validator` with `@classmethod`), `schemas/research_results_schema.py` (`class Config: from_attributes = True` ? `model_config = ConfigDict(from_attributes=True)`). Deprecation warnings reduced from 7 ? 1.
- ? **FIXED (2026-03-18 Sprint 6):** SQLAlchemy 2.0 migration complete. `db/database.py:9` `from sqlalchemy.ext.declarative import declarative_base` ? `from sqlalchemy.orm import declarative_base`. The final deprecation warning is eliminated. Deprecation warnings: 0. No other files used the old import path (`Base` was defined once and all models import it from `db.database`).
- ? **FIXED (2026-03-18 Sprint 4):** `main.py` startup DB session leak resolved. The unused `db = SessionLocal()` at startup has been removed. The system identity seeder now uses a proper `try/finally` block with `db.close()`.
- ? **FIXED (2026-03-18 Sprint 4):** Duplicate `get_db()` definitions removed from `main_router.py` and `analytics_router.py`. Both now import `get_db` from `db.database`. Single canonical definition.
- ? **FIXED (2026-03-20 Security Sprint):** `health_router.py` now imports `seo_services` and `memory_persistence` from `services.*`, avoiding `ModuleNotFoundError` when `PYTHONPATH` does not include `AINDY/services/` directly.
- ? **FIXED (2026-03-18 Sprint 4):** `bridge_router.py` duplicate `create_engine`/`sessionmaker` imports removed.
- ? **RESOLVED (2026-03-21):** `services/master_index_service.py2.py` renamed to `services/master_index_service.py`.
- ? **FIXED (2026-03-18 Sprint 4):** `task_router.py POST /tasks/complete` now passes `user_id=current_user["sub"]` to `complete_task()`. Memory Bridge Phase 3 task completion hook now fires from the API.
- ? **RESOLVED (2026-03-21):** `POST /social/post` now uses `MemoryCaptureEngine` with SQLAlchemy session and `current_user["sub"]` for persistent memory capture.
- ? **RESOLVED (2026-03-21):** `services/research_results_service.py::log_to_memory_bridge()` now uses `MemoryCaptureEngine` with DB session and `user_id` (no transient memory nodes).
- ? **RESOLVED (2026-03-21):** `services/freelance_service.py` now logs via `MemoryCaptureEngine` (removes legacy DAO path and invalid node_type usage).
- ? **RESOLVED (2026-03-21):** `services/leadgen_service.py::create_lead_results()` now requires `user_id` and persists owned memory nodes.
- ? **RESOLVED (2026-03-21):** `services/leadgen_service.py::score_lead()` now uses chat `messages` and dead code removed.
- ? **RESOLVED (2026-03-21):** Duplicate `generate_meta_description()` removed in `services/seo_services.py`.
- ? **RESOLVED (2026-03-21):** `RevenueScalingPanel.jsx` now uses `calculateRevenueScaling()` with correct labels.
- ? **FIXED (2026-03-20 Security Sprint):** Frontend auth regressions resolved — all listed components now use `client/src/api.js` functions backed by `authRequest()`.
- ? **FIXED (2026-03-20 Security Sprint):** Frontend/backend contract mismatches resolved — `AnalyticsPanel.jsx` uses `/analytics/masterplan/{id}/summary`, and `LeadGen.jsx` maps `{results}` with `overall_score` + `reasoning`.
- ? **FIXED (2026-03-20 Security Sprint):** `Dashboard.jsx` stray JSX removed.
- Implicit coupling exists between:
- `AINDY/routes/social_router.py` and `AINDY/bridge/bridge.py` (social post logging invokes memory bridge creation).
- `AINDY/routes/health_router.py` pings SEO endpoints via hardcoded paths (now aligned to `/seo/*`).
- Health checks are present (`/health/`, `/dashboard/health`) but no readiness gating is implemented (`AINDY/routes/health_router.py`, `AINDY/routes/health_dashboard_router.py`).
- ? **RESOLVED (2026-03-21):** `POST /bridge/user_event` now persists to `bridge_user_events` table (`AINDY/routes/bridge_router.py`).
- ? **RESOLVED (2026-03-21):** `AINDY/bridge/trace_permission.py` moved to `legacy/trace_permission.py` (deprecated HMAC helper).
- `AINDY/bridge/archive/` contains two files pending team confirmation of deletion: `memory_bridge_core_draft.rs` and `Memorybridgerecognitiontrace.rs`.

## 2. Schema / Migration Debt
- Migration drift risk exists due to multiple overlapping migrations and no automated migration validation in deployment (`AINDY/alembic/versions/`).
- ? **RESOLVED (2026-03-22):** Startup schema drift guard enforced in `main.py` (blocks app start if `alembic current` != `alembic heads`).
- Some application-level constraints are not enforced at DB level (e.g., session locking is application logic in `AINDY/services/masterplan_factory.py`).
- Many tables lack explicit foreign keys, making referential integrity dependent on application logic (`AINDY/db/models/*.py`).
- Cascade rules are sparse; only a subset of relationships define cascades (`AINDY/db/models/arm_models.py`, `AINDY/db/models/masterplan.py`).
- ? **RESOLVED (2026-03-22):** Ownership tables with `user_id` stored as `String` (`research_results`, `freelance_orders`, `client_feedback`, `drop_points`, `pings`) normalized to UUID with FKs to `users.id` (migration `2359cded7445`).
- ? **RESOLVED (2026-03-22):** Legacy rows in `tasks`, `leadgen_results`, and `authors` were checked with `Tools/backfill_user_ids.py` (dry-run) and no NULL `user_id` rows remain.
- ? **RESOLVED (2026-03-21):** `tasks.user_id` added (nullable) with user-scoped routing in `task_router.py` and user_id enforcement in `task_services.py`. Existing legacy rows without `user_id` no longer appear in user-scoped queries.
- ? **RESOLVED (2026-03-22):** Stale TODO comment at `task_router.py:20` ("Scope task to current_user when user_id is added to Task model") — `user_id` is present on the model and all task routes are already scoped. Comment removed.
- ? **RESOLVED (2026-03-21):** `leadgen_results.user_id` added (nullable) with user-scoped routing in `leadgen_router.py`. New writes require `user_id` and are filtered per user.
- ? **RESOLVED (2026-03-22):** `MasterPlan.version` removed; `version_label` is now the only version field (migration `c4f2a9d1e7b3`).
- ? **RESOLVED (2026-03-22):** `GenesisSessionDB` dual user columns removed. `genesis_sessions.user_id` is now UUID with FK to `users.id`; legacy `user_id` (Integer) and `user_id_str` dropped.
- ? **RESOLVED (2026-03-22):** `CanonicalMetricDB.user_id` now uses UUID with FK to `users.id`. Legacy Integer column dropped.
- ? **FIXED (2026-03-18 Sprint 4):** `bridge_router.py` `node_type="generic"` defaults changed to `None` in `NodeCreateRequest` schema and `_NodeLike` inner class. `NodeResponse.node_type` updated to `Optional[str]`. ORM event validator crash eliminated.
- ? **FIXED (2026-03-18 Sprint 4):** `services/memory_persistence.py::MemoryNodeDAO.save_memory_node()` fallback changed from `"generic"` to `None`. ORM event violation path removed.
- ? **RESOLVED (2026-03-21):** `version.json` and `system_manifest.json` updated to `1.0.0` with current metadata.
- ~~**`bridge/bridge.py::create_memory_node()` writes to the wrong table.**~~ ? **FIXED (2026-03-18 Memory Bridge Phase 1):** Fully rewritten to write `MemoryNodeModel` rows via `MemoryNodeDAO` (table: `memory_nodes`). New signature: `(content, source, tags, user_id, db, node_type)`. All three callers updated. Regression tests added and bug-documenting tests flipped.
- ? **RESOLVED (2026-03-22):** Orphan `save_memory_node(self, memory_node)` removed from `AINDY/services/memory_persistence.py` (dead code).
- ? **RESOLVED (2026-03-21):** `AINDY/version.json` and `AINDY/system_manifest.json` updated to `1.0.0`.

## 3. Testing Debt
- Minimal unit coverage in `AINDY/services/`.
- Integration tests are limited to calculation endpoints (`test_calculations.py`, `test_routes.py`).
- No automated migration validation tests (`AINDY/alembic/` has no test harness).
- ? **FIXED (2026-03-18 CI/CD Sprint):** CI pipeline live. GitHub Actions `ci.yml` runs lint (ruff) + tests (pytest + coverage) on every push and PR to `main`. Coverage threshold: 64% (baseline: 69%). Coverage XML uploaded to Codecov. PR template, CODEOWNERS, SECRETS.md, and `.env.example` added.
- ? **FIXED (2026-03-18 CI/CD Sprint):** Coverage metrics tooling configured. `pytest-cov==7.0.0` + `.coveragerc` added. Baseline: 69%. CI threshold: 64% (`--cov-fail-under=64`). XML report generated and uploaded to Codecov on every push/PR.
- ? **RESOLVED (2026-03-22):** Duplicate test names in `test_routes.py` removed (unique identifiers added).
- ? **RESOLVED (2026-03-22):** `AINDY/legacy/bridge_tools/smoke_memory.py` imports fixed and project root path corrected (`db.dao.memory_node_dao.MemoryNodeDAO` + proper root resolution).
- ? **RESOLVED (2026-03-22):** `AINDY/legacy/bridge_tools/Bridgeimport.py` wrapped in a `__main__` guard to prevent import-time execution.

## 3.1 RippleTrace Intelligence Debt (Priority Queue)

### High Priority

* Missing automated test coverage across the ThreadWeaver/Delta/Prediction/Recommendation/Influence/Causal/Narrative/Learning/Strategy/Playbook/Content Generator engines.
* No caching on `/influence_graph` or `/causal_graph`, so each page load hits SQLite directly and risks contention under load.
* Pairwise comparisons inside `analytics.influence_graph` and `analytics.causal_engine` may trigger N+1 behavior as the drop point count grows.
* No dedicated background job system (Celery/Redis/ARQ) to offload scoring, snapshotting, or predictive scans, leaving those tasks on request threads.

### Medium Priority

* Threshold tuning in `analytics.learning_engine.adjust_thresholds` is still heuristic and lacks probabilistic calibration.
* Strategy clustering in `domain.strategy_engine.build_strategies` relies on simple frequency counters rather than semantic similarity or embeddings.
* `domain.content_generator` remains rule-based with no LLM-assisted variation or guardrails yet.

### Low Priority

* Graph UI (`client/src/components/GraphView.jsx`) has no batching / virtualization for >100 nodes, so performance may degrade on larger graphs.
* Snapshot storage (`score_snapshots`) grows without retention policies, increasing sqlite file size if not trimmed.

## 4. Error Handling Debt
- ? **RESOLVED (2026-03-21):** Error classification consistency improved across core routes with structured `detail` payloads for 5xx failures.
- ? **RESOLVED (2026-03-21):** Structured JSON error format enforced via global exception handlers in `main.py`.
- ? **RESOLVED (2026-03-22):** Structured JSON error responses standardized across remaining core routes (analytics, masterplan, genesis, memory, memory_trace, freelance, bridge, social).
- ? **RESOLVED (current workspace):** Silent `except ...: pass` blocks removed from production code under `routes/`, `services/`, `runtime/`, `db/`, `modules/`, and `watcher/`. Replacement behavior is structured logging, observability events, or explicit propagation depending on callsite criticality.
- ? **RESOLVED (current workspace):** Outbound OpenAI/HTTP/watcher/health-probe calls are wrapped by `services/external_call_service.py` and now emit required `SystemEvent` lifecycle records (`external.call.started|completed|failed`, `error.external_call`).
- ~~Missing retry logic for external model providers (`AINDY/services/genesis_ai.py`).~~ **FIXED (2026-03-17 Genesis Block 4):** `validate_draft_integrity()` implements 3-attempt retry loop with fail-safe fallback. ~~`deepseek_arm_service.py`~~ — **FIXED (2026-03-17 ARM Phase 1):** `DeepSeekCodeAnalyzer._call_openai()` implements retry with configurable `retry_limit` and `retry_delay_seconds`.
- Logging is mixed between `print(...)` and logging module; core routes/services now use `logger` but structured logging is not yet standardized (`AINDY/config.py`, multiple routes/services).

## 5. Concurrency Debt
- ? **RESOLVED (2026-03-25 Sprint N+9):** Background task runner uses a DB lease (`background_task_leases`) to gate APScheduler startup — `start_background_tasks()` returns `bool`; `scheduler_service.start()` only called by the leader. Heartbeat job (`background_lease_heartbeat`, 60s interval) keeps the lease alive so it doesn't expire (TTL=120s). `is_background_leader()` public helper + `GET /observability/scheduler/status` endpoint expose current state. APScheduler no longer starts on follower instances.
- ? **RESOLVED (current workspace):** Lease timestamps in `services/task_services.py` now use timezone-aware UTC and normalize loaded DB values before comparison. The worker startup warning `can't compare offset-naive and offset-aware datetimes` is eliminated in live compose startup.
- ? **RESOLVED (2026-03-22):** Process-level singletons in ARM analyzer and embedding client now use thread-safe initialization guards.
- ? **RESOLVED (2026-03-22):** Per-request session reuse warning added to `db/database.py`.
- ? **RESOLVED (2026-03-22):** Daemon threads eliminated — APScheduler replaces all `threading.Thread(daemon=True)` patterns.
- Explicit startup/shutdown coordination now exists in `main.py` via lifespan, but execution still remains in-process and not externally supervised.

## 6. Security Debt
- ? **FIXED (2026-03-17 Phase 2):** Rate limiting added — `SlowAPIMiddleware` registered in `main.py` with per-IP limiting via `slowapi`. AI endpoints (genesis, leadgen) can be rate-limited with `@limiter.limit()` decorator.
- ? **FIXED (2026-03-17 Phase 2):** JWT authentication added to user-facing route groups: `task_router`, `leadgen_router`, `genesis_router`, `analytics_router`. Dependency: `Depends(get_current_user)` from `services/auth_service.py`. Auth routes at `POST /auth/login`, `POST /auth/register` are public.
- ? **FIXED (2026-03-17 Phase 2):** CORS wildcard replaced — `allow_origins=["*"]` replaced with `ALLOWED_ORIGINS` read from `.env` environment variable. Default: localhost origins. No longer uses wildcard + credentials combination.
- ? **FIXED (2026-03-17 Phase 3):** Node gateway auth wired — `server.js` now loads `AINDY_API_KEY` from `.env` via `dotenv` and sends `X-API-Key` header on all FastAPI service calls. `POST /network_bridge/connect` and `POST /network_bridge/user_event` are now API-key protected; gateway sends the key.
- ? **FIXED (2026-03-17 Phase 3):** User ORM model created — `db/models/user.py` (`users` table: UUID PK, unique email/username indexes, `hashed_password`, `is_active`). Migration `37f972780d54` applied. `auth_router.py` replaced in-memory `_USERS` dict with `register_user()` / `authenticate_user()` from `auth_service.py` via `Depends(get_db)`.
- ? **FIXED (2026-03-17 Phase 3):** All remaining unprotected routes secured. JWT (`get_current_user`): `seo_routes`, `authorship_router`, `arm_router`, `rippletrace_router`, `freelance_router`, `research_results_router`, `dashboard_router`, `social_router`. API key (`verify_api_key`): `db_verify_router`, `network_bridge_router`. Zero unprotected non-public routes remain.
- ? **FIXED (2026-03-17 Phase 3):** Rate limiting decorators applied to all AI/cost endpoints — `@limiter.limit()` on `/leadgen/` (10/min), `/genesis/message` (20/min), `/genesis/synthesize` (5/min), `/arm/analyze` (10/min), `/arm/generate` (10/min). Shared `Limiter` extracted to `services/rate_limiter.py`.
- No documented secret rotation policy (`AINDY/routes/bridge_router.py` uses env secret without rotation).
- ? **RESOLVED (2026-03-21):** HMAC protection removed from bridge writes; JWT-only.
- ? **FIXED (2026-03-23 Sprint N+1):** `SECRET_KEY` insecure default hardened. `config.py` validator warns on placeholder; `main.py` lifespan raises `RuntimeError` in production if placeholder is still set. Test env uses strong key via conftest.
- ? **FIXED (2026-03-18 Sprint 4):** `GET /dashboard/health` now requires JWT auth. `dependencies=[Depends(get_current_user)]` added to `health_dashboard_router.py` router level.
- ? **FIXED (2026-03-18 Sprint 4 Auth Hardening):** `GET /bridge/nodes`, `POST /bridge/nodes`, and `POST /bridge/link` now require JWT (`Depends(get_current_user)` added per-endpoint). `POST /bridge/user_event` now requires API key (`Depends(verify_api_key)`). All bridge endpoints are now protected.
- ? **RESOLVED (2026-03-21):** `POST /tasks/recurrence/check` now requires JWT (`Depends(get_current_user)`).
- ? **FIXED (2026-03-18 Sprint 4 Auth Hardening):** All calculation endpoints in `main_router.py` now require JWT. `dependencies=[Depends(get_current_user)]` added at router level. Covers `/calculate_twr`, `/calculate_effort`, all Infinity Algorithm endpoints, `/results`, `/masterplans`, and `/create_masterplan`. Rate-limit bypass vector closed.
- ? **PARTIALLY FIXED (2026-03-18 Sprint 4 Auth Hardening):** `GET /analytics/masterplan/{id}` and `/analytics/masterplan/{id}/summary` now verify MasterPlan ownership via `MasterPlan.user_id == current_user["sub"]` before returning results. Returns 404 for wrong owner.
- ? **FIXED (2026-03-18 Sprint 5):** Freelance cross-user exposure closed. Migration `d37ae6ebc319` adds `user_id` to `freelance_orders` and `client_feedback`. `create_order()` and `collect_feedback()` now set `user_id` from JWT. `get_all_orders()` and `get_all_feedback()` filter by `user_id`. `POST /deliver/{id}` verifies ownership before delegating.
- ? **FIXED (2026-03-18 Sprint 5):** Research cross-user exposure closed. Migration adds `user_id` to `research_results`. `create_research_result()` sets `user_id`. `get_all_research_results()` filters by `user_id`.
- ? **FIXED (2026-03-18 Sprint 5):** Rippletrace cross-user exposure closed. Migration adds `user_id` to `drop_points` and `pings`. All 6 service functions accept `user_id`. All router endpoints pass `current_user["sub"]`. System-internal `log_ripple_event()` calls pass `user_id=None` (system events are unowned).
- ? **RESOLVED (2026-03-21):** `leadgen_results.user_id` added and `GET /leadgen/` is user-scoped.
- ? **FIXED (2026-03-18 Sprint 4 Auth Hardening):** `GET /memory/nodes/{node_id}` now enforces ownership — returns 404 if `node.user_id != current_user["sub"]`. Cross-user node reads blocked.
- ? **FIXED (2026-03-18 Sprint 4):** `.env` orphan bare Google API key on line 7 removed. `.env` now parses cleanly with no floating values.
- ? **RESOLVED (current workspace):** `/memory/nodus/execute` is no longer an unrestricted host-embedding path. Route-level source validation blocks system/file/network primitives, only allowlisted operations are registered, and write-capable operations require a scoped capability token plus execution ID.
- ? **RESOLVED (2026-03-21):** `task_services.complete_task()` now updates MongoDB profile by `user_id` (no hardcoded username).
- ? **FIXED (2026-03-20 Security Sprint):** Memory tag search, link traversal, and link creation are user-scoped. `GET /memory/nodes` and `GET /memory/nodes/{id}/links` filter by `user_id`, and `POST /memory/links` verifies ownership before linking.
- ? **FIXED (2026-03-20 Security Sprint):** `/bridge/nodes` now uses `MemoryCaptureEngine` and sets `user_id` (when provided) plus `source_agent` for federation tagging.
- ? **FIXED (2026-03-20 Security Sprint):** `POST /analytics/linkedin/manual` now verifies `MasterPlan.user_id == current_user["sub"]` and returns 404 when not owned.
- ? **FIXED (2026-03-20 Security Sprint):** `GET /masterplans` and `GET /results` now filter by `user_id`, and `POST /create_masterplan` sets `user_id` from JWT. `calculation_results.user_id` added with migration `c1f2a9d0b7e4`.
- ? **FIXED (2026-03-20 Security Sprint):** `POST /social/profile` upserts are scoped by `user_id` and block cross-user overwrites.
- ? **FIXED (2026-03-18 Sprint 4):** `client/src/api.js` — all protected endpoints now use `authRequest()`. ARM (analyze/generate/logs/config/metrics/suggest), Tasks (create/list/start/complete), Social (profile/feed/post), Research (query), and LeadGen now all send the JWT Bearer token. `runLeadGen` refactored from raw `fetch()` to `authRequest()`. `authRequest` definition moved before first use.
- ? **RESOLVED (2026-03-21):** `GET /calculate_twr` scopes masterplan + calculation history by `user_id`.
- ? **RESOLVED (2026-03-21):** `dashboard_router.py` overview queries are scoped by `current_user["sub"]`; `authors.user_id` added for ownership filtering.
- ? **RESOLVED (2026-03-21):** `GET /bridge/nodes` now filters by `current_user["sub"]` via `MemoryNodeDAO.find_by_tags(..., user_id=...)`.
- ? **RESOLVED (2026-03-21):** `POST /bridge/nodes` now enforces `current_user["sub"]` and ignores caller-supplied `user_id`.
- ? **RESOLVED (2026-03-21):** `InfiniteNetwork.jsx` now uses `authRequestExternal()` with JWT headers for gateway calls.

## 7. Observability Debt
- ? **RESOLVED (2026-03-22):** Core routes/services now use `logger` instead of `print(...)` with structured error details.
- ? **RESOLVED (2026-03-22):** Structured request logging added via middleware with per-request IDs and latency.
- ? **RESOLVED (2026-03-22):** Request metrics persisted to `request_metrics` (basic baseline store).
- ? **RESOLVED (2026-03-22):** Basic observability query endpoint added (`GET /observability/requests`).
- ? **RESOLVED (current workspace):** targeted observability-event logging added for previously silent execution and rollback failures (`services/observability_events.py`).
- ? **RESOLVED (2026-03-25 Sprint N+8):** Agent lifecycle tracing implemented — `AgentEvent` table captures PLAN_CREATED, APPROVED, REJECTED, EXECUTION_STARTED, COMPLETED, EXECUTION_FAILED, RECOVERED, REPLAY_CREATED with `correlation_id` (`run_<uuid4>`) threading through `AgentRun`, `AgentStep`, and `AgentEvent`. `GET /agent/runs/{run_id}/events` merges lifecycle + step events into a chronological timeline.
- ? **RESOLVED (2026-03-25 Sprint N+9):** Request-scoped `request_id` now propagates through async call stacks via `contextvars.ContextVar`. `RequestContextFilter` injects `request_id` into every `LogRecord`; all root-logger handlers upgraded to format `%(asctime)s - %(levelname)s - [%(request_id)s] - %(message)s`. Non-request code paths log `[-]`.
- No system-wide centralized tracing or log aggregation pipeline (OpenTelemetry / external aggregator).
- Infinity Algorithm Support System no longer operates as a score-only open loop. Watcher, explicit feedback capture, and `services/infinity_loop.py` are implemented. Remaining gaps are expanded TWR weighting, ranking, and learned optimization. Canonical reference: `docs/roadmap/INFINITY_ALGORITHM_SUPPORT_SYSTEM.md`.

## 8. C++ Semantic Kernel Debt

The C++ semantic similarity kernel (`bridge/memory_bridge_rs/`) was added in `feature/cpp-semantic-engine`. The following items must be resolved before the kernel is production-ready.

- **Release build blocked by Windows AppControl.** The kernel was built in debug mode because AppControl policy blocks writes to `target/release/`. Debug benchmark (dim=1536, 10k iters): Python 2.753s vs C++ 3.844s — FFI overhead dominates in debug. Release build is expected to show 10–50x improvement. Action: run `maturin develop --release` in an environment without AppControl restrictions (deployment server or CI) and record results (`AINDY/legacy/bridge_tools/benchmark_similarity.py`, `AINDY/bridge/memory_bridge_rs/Cargo.toml`).
- ~~**No vector embeddings on `MemoryNode`.**~~ ? **RESOLVED (2026-03-18 Memory Bridge Phase 2):** `embedding VECTOR(1536)` column added to `MemoryNodeModel` (`services/memory_persistence.py`) and DB via migration `mb2embed0001`. `services/embedding_service.py` generates OpenAI `text-embedding-ada-002` embeddings on every `MemoryNodeDAO.save()` call. C++ kernel (`memory_bridge_rs.semantic_similarity`) wired for cosine similarity with Python fallback. `find_similar()` uses pgvector `<=>` operator. Endpoints: `POST /memory/nodes/search`, `POST /memory/recall`.
- ? **RESOLVED (2026-03-21):** HMAC permissions removed from bridge write path; `PERMISSION_SECRET` no longer used.

## 9. Newly Revealed Bugs (Diagnostic Test Suite — 2026-03-17)

The following bugs were revealed by the comprehensive diagnostic test suite added in `feature/cpp-semantic-engine`. All items below were confirmed by failing tests in `AINDY/tests/`.

### §2 Schema / Migration (additions)
- ~~**`bridge/bridge.py::create_memory_node()` also has a broken import path.**~~ ~~**IMPORT PATH FIXED (2026-03-17):** Import corrected.~~ ? **FULLY FIXED (2026-03-18 Memory Bridge Phase 1):** `CalculationResult` no longer referenced at all. `create_memory_node()` fully rewritten to use `MemoryNodeDAO`. Both the import bug and the wrong-table bug are resolved. Revealed by: `test_memory_bridge.py::TestCreateMemoryNodeWrongTable` (now a regression guard).

### §1 Structural (additions)
- **`routes/genesis_router.py` has three undefined name references.** ~~(1) `POST /genesis/synthesize` calls `call_genesis_synthesis_llm()` — NameError. (2) `POST /genesis/lock` calls `create_masterplan_from_genesis()` — NameError. (3) `POST /genesis/{plan_id}/activate` references `MasterPlan` — NameError.~~ ~~**CRASHES FIXED (2026-03-17):** All three missing imports added. LLM synthesis remains a stub.~~ ? **FULLY RESOLVED (2026-03-17 Genesis Blocks 1-3):** `call_genesis_synthesis_llm()` replaced with real GPT-4o call. `determine_posture()` implemented with real Stable/Accelerated/Aggressive/Reduced logic. All routes user-scoped. Two new GET endpoints added. `masterplan_router.py` created. Migration `a1b2c3d4e5f6` applied. 22 new tests pass.
- **`services/leadgen_service.py::score_lead()` contains dead/unreachable code.** The function has two `try:` blocks, but the second is entirely unreachable because the first block always returns (or raises). The dead block calls `client.chat.completions.create(model="gpt-4o", ...)` — a different model than the live block — which is neither tested nor executed. Fix: remove the dead block (`AINDY/services/leadgen_service.py:104-127`). Revealed by: `test_routes_leadgen.py::TestLeadGenServiceBugs::test_score_lead_has_dead_code_after_return`.
- **`routes/seo_routes.py` defines `analyze_seo()` twice.** The function is defined at line 17 and again at line 39. Python silently uses the second definition, making the first (basic) implementation unreachable. The duplicate also appears in the router — both map to `POST /analyze_seo/`. The second definition (`POST /seo/analyze`) works but shares a name with the dead first one (`AINDY/routes/seo_routes.py:17,39`).
- **`routes/dashboard_router.py` and `routes/health_dashboard_router.py` both use prefix `/dashboard`.** This creates a route collision on `/dashboard/health`. FastAPI registers both but the last-registered takes precedence. The `dashboard_router.py` (overview) path is `/dashboard/overview` and is not directly conflicting, but the shared prefix means any future additions risk silent overrides (`AINDY/routes/__init__.py`).
- ? **RESOLVED (2026-03-18):** Startup handlers consolidated into lifespan; deprecated `@app.on_event` removed (`AINDY/main.py`).

### §6 Security (additions — all resolved 2026-03-17 Phase 2)
- ~~**No authentication or authorization on any API route confirmed by test suite.**~~ **FIXED (2026-03-17):** JWT auth (`Depends(get_current_user)`) added to `task_router`, `leadgen_router`, `genesis_router`, `analytics_router`. All five security-tested endpoints now return 401 without credentials. `services/auth_service.py` created with JWT creation/verification and password hashing (`python-jose`, `passlib/bcrypt`). Auth routes at `POST /auth/login`, `POST /auth/register`.
- ~~**CORS wildcard with credentials confirmed.**~~ **FIXED (2026-03-17):** `allow_origins` reads from `ALLOWED_ORIGINS` env var (default: localhost origins). Wildcard removed.
- ~~**No rate limiting middleware confirmed.**~~ **FIXED (2026-03-17):** `SlowAPIMiddleware` added via `app.add_middleware(SlowAPIMiddleware)`. Limiter instance attached to `app.state.limiter`. `slowapi==0.1.9` added to requirements.

### §4 Error Handling (additions)
- **`services/calculation_services.py::calculate_twr()` ZeroDivisionError.** **FIXED (2026-03-17):** `task_difficulty=0` previously caused an unhandled `ZeroDivisionError` that propagated as HTTP 500. Fixed by: (1) adding a `ValueError` guard at the top of `calculate_twr()` when `task_difficulty == 0`; (2) adding a Pydantic `@validator` on `TaskInput.task_difficulty` that rejects values `<= 0` with a 422 response before the function is reached; (3) wrapping the `calculate_twr()` call in `routes/main_router.py` with `try/except ValueError` and `except ZeroDivisionError` both raising `HTTPException(422)`. Route now returns 422 with a clear error message instead of 500. Revealed by: `test_calculation_services.py::TestTWR::test_twr_zero_difficulty_raises`, `test_routes_analytics.py::TestCalculateTWREndpoint::test_twr_zero_difficulty_causes_500`.

### §3 Testing (additions — resolved)
- Comprehensive diagnostic test suite added: `AINDY/tests/` with 143 tests across 8 files covering services, memory bridge, Rust/C++ kernel, all route groups, models, and security. Test infrastructure: `pytest==9.0.2`, `pytest-mock==3.15.1`, `pytest-asyncio==1.3.0` added to `requirements.txt`. Final result: **135 passing, 8 failing** (all failures are intentional diagnostic tests for known bugs).

## 10. Memory Bridge Architectural Debt

The following items were identified during a structured architectural review of the Memory Bridge system (2026-03-17). They describe structural and design-level deficiencies distinct from the runtime bugs already recorded in §2, §8, and §9. Cross-references to those sections are noted where relevant. Canonical definition and evolution plan: `docs/architecture/MEMORY_BRIDGE.md`.

### §10.1 Data Model — MemoryNode.children is never persisted

- **`MemoryNode.children` (recursive nested nodes) is silently dropped on every persist call.** The `children: Vec<MemoryNode>` field is defined in the Rust struct and serializable, but no code in `MemoryNodeDAO.save_memory_node()` or `bridge/bridge.py` walks the children array and inserts corresponding rows into `memory_links`. Every child node created in-memory is lost on process exit. This makes recursive trace continuity — a stated design objective — a no-op.
  - Location: `AINDY/bridge/memory_bridge_rs/src/lib.rs` (MemoryNode struct), `AINDY/services/memory_persistence.py` (MemoryNodeDAO.save_memory_node)
  - Mechanism: Callers construct nested MemoryNode trees; the persist path only writes the root node's fields; `children` is ignored.
  - Impact: All associative chains are ephemeral. Any cross-session continuity built on children is silently incomplete.
  - ? **FIXED (2026-03-23 Sprint N+1):** `MemoryNodeDAO.save()` now reads `extra["children"]` after persisting the root node and creates `MemoryLink` rows (link_type="child") for each valid child UUID that exists in the DB. Children passed via `extra["children"]` are no longer silently dropped.

### §10.2 Data Model — MemoryTrace Python class creates a divergent shadow state

- **`MemoryTrace` (defined in `bridge/bridge.py`) maintains an in-memory representation of memory nodes that is not synchronized with the database.** It has no read-from-DB path, no cache invalidation, and no recovery logic on restart. Any write that goes through `MemoryTrace` and any write that goes through `MemoryNodeDAO` produce independent, inconsistent views of the same logical data.
  - Location: `AINDY/bridge/bridge.py` (MemoryTrace class)
  - Mechanism: `MemoryTrace.add_node()` appends to `self.nodes` in-memory. `MemoryNodeDAO.save_memory_node()` writes to PostgreSQL. There is no path between them.
  - Impact: Queries against the DB do not reflect in-memory state; in-memory state does not survive restart. Two consumers reading the same "memory" will see different results depending on which layer they use.
  - Status: ? **RESOLVED (2026-03-22):** `MemoryTrace` is now explicitly deprecated and emits a runtime warning on use. Database-backed traces (`MemoryTraceDAO` + `memory_traces`) are the only supported trace state.

### §10.3 Graph Layer — memory_links has no traversal query

- **`memory_links` is populated (or intended to be) but no query traverses it.** No method in `MemoryNodeDAO` fetches linked neighbors, expands from a seed node, or scores paths. The table has correct schema, correct indexes, and a uniqueness constraint — but zero read-path usage. The graph is write-only from the application's perspective.
  - Location: `AINDY/services/memory_persistence.py` (MemoryNodeDAO), `AINDY/routes/bridge_router.py` (no traversal endpoint)
  - Mechanism: `POST /bridge/link` inserts rows. No endpoint or DAO method queries `memory_links` for neighbors, reachability, or subgraph expansion.
  - Impact: The relational structure between memory nodes is unqueryable. Graph-based recall — the architectural basis for associative memory — does not function.
  - Status: ? **RESOLVED (2026-03-18 Memory Bridge v3):** Multi-hop DFS traversal added in `db/dao/memory_node_dao.py::traverse()` with cycle prevention. Exposed at `GET /memory/nodes/{id}/traverse`. Single-hop `get_linked_nodes()` remains for neighbor lookup.

### §10.4 Graph Layer — memory_links.strength is a VARCHAR, not a numeric value

- **`memory_links.strength` is defined as `VARCHAR(20)` with default `"medium"`.** This means relationship weight is a non-comparable string enum (`"low"`, `"medium"`, `"high"`). It cannot be used in ORDER BY relevance, cannot be averaged, and cannot participate in any scoring formula. Any future graph traversal that needs weighted edges will require a schema migration to convert this to a numeric type.
  - Location: `AINDY/alembic/versions/bff24d352475_create_memory_nodes_links.py`, `AINDY/services/memory_persistence.py` (MemoryLinkModel)
  - Mechanism: Schema defines `strength VARCHAR(20) DEFAULT 'medium'`. No numeric weight column exists.
  - Impact: Graph traversal scoring is blocked. Relationship strength carries no computational meaning in the current schema.
  - Status: ? **RESOLVED (2026-03-21):** `weight FLOAT` added to `memory_links` via migration `e2c3d4f5a6b7`; traversal now prefers numeric `weight` with legacy `strength` fallback.

### §10.5 Retrieval — semantic retrieval is architecturally impossible in current state

- **No embeddings are stored in `memory_nodes`.** The C++ `cosine_similarity` kernel is implemented and callable, but `MemoryNodeModel` has no `embedding` column and no embedding generation occurs on node creation. `GET /bridge/nodes` retrieves by tag match or full-text only. There is no `/bridge/nodes/search/semantic` endpoint, no pgvector integration, and no embedding provider call in the write path. This is cross-referenced in §8 but recorded here for completeness as a retrieval architecture gap.
  - Location: `AINDY/services/memory_persistence.py` (MemoryNodeModel — no embedding field), `AINDY/bridge/memory_bridge_rs/src/lib.rs` (cosine_similarity callable but unused in retrieval)
  - Mechanism: Write path: content stored as TEXT only. Read path: tag OR/AND query or tsvector FTS. No vector path exists.
  - Impact: Semantic recall — retrieving memories by meaning rather than exact tags — does not function. The primary differentiation of this memory system over a text log is absent.
  - Status: ? **RESOLVED (2026-03-18 Memory Bridge Phase 2):** `embedding VECTOR(1536)` column added to `MemoryNodeModel` and DB (migration `mb2embed0001`). `services/embedding_service.py` generates embeddings via OpenAI `text-embedding-ada-002` on every `MemoryNodeDAO.save()` call. `find_similar()` retrieves via pgvector `<=>` cosine distance. Semantic search available at `POST /memory/nodes/search`. HNSW index added via migration `f3a4b5c6d7e8`.

### §10.6 Retrieval — no temporal decay or recency weighting

- **`created_at` is indexed on `memory_nodes` but is never incorporated into retrieval scoring.** All nodes matching a tag query or full-text query are returned with equal relevance regardless of age. A node created 2 years ago ranks identically to one created 30 seconds ago. There is no decay function, no recency weight, and no salience model.
  - Location: `AINDY/services/memory_persistence.py` (MemoryNodeDAO.find_by_tags — ORDER BY clause absent or arbitrary)
  - Mechanism: `find_by_tags()` returns matching nodes without a relevance score. No timestamp-based ranking is applied.
  - Impact: As node count grows, older or irrelevant memories contaminate recall. Retrieval quality degrades with scale.
- Status: ? **RESOLVED (2026-03-18 Memory Bridge v4):** `MemoryNodeDAO.recall()` implements resonance v2 scoring: `score = (semantic * 0.40) + (graph * 0.15) + (recency * 0.15) + (success_rate * 0.20) + (usage_frequency * 0.10)` where `recency = exp(-age_days / 30.0)`, then multiplied by adaptive `weight` and capped at 1.0. All recall results are ranked by resonance score. `POST /memory/recall` is the primary retrieval API.

### §10.7 Retrieval — tag query returns unranked flat lists with no relevance signal

- **Tag-based retrieval returns a flat list with no ordering by relevance, specificity, or recency.** OR mode returns all nodes matching any tag; AND mode returns all nodes matching all tags. No result carries a score. Callers cannot distinguish a node that matched 5 of 5 query tags from one that matched 1 of 5.
  - Location: `AINDY/services/memory_persistence.py` (MemoryNodeDAO.find_by_tags), `AINDY/routes/bridge_router.py` (GET /bridge/nodes response)
  - Mechanism: SQL query returns rows; no rank, score, or tag-overlap count is computed or returned.
  - Impact: High-cardinality tag queries return noisy results with no signal for the caller. Useful for exact lookups; breaks for fuzzy or exploratory recall.
  - Status: ? **RESOLVED (2026-03-18 Memory Bridge Phase 2):** `recall()` computes `tag_score = overlap / query_tag_count` and incorporates it into the resonance formula. Each returned node carries `tag_score`, `semantic_score`, `recency_score`, and `resonance_score` fields. `get_by_tags()` direct call still returns flat lists for backward compat; callers needing ranked results should use `recall()` or `POST /memory/recall`.

### §10.8 Persistence — no versioning or history table, state reconstruction is impossible

- **`memory_nodes` has an `updated_at` column but no history table, no append-only log, and no event sourcing.** When a node's content is updated, the prior value is permanently overwritten. The stated design objective of reconstructing past states across sessions cannot be fulfilled without a record of mutations.
  - Location: `AINDY/services/memory_persistence.py` (MemoryNodeModel — no history table), `AINDY/alembic/versions/` (no history migration)
  - Mechanism: UPDATE on `memory_nodes` replaces content in-place. No trigger, no shadow table, no log of prior values.
  - Impact: Temporal reconstruction — replaying what the system knew at time T — is not possible. Audit trail for node evolution does not exist.
  - Status: ? **RESOLVED (2026-03-18 Memory Bridge v3):** `memory_node_history` table added with append-only snapshots. `MemoryNodeDAO.update()` records previous values on explicit updates and `GET /memory/nodes/{id}/history` exposes history.

### §10.9 Infrastructure — Rust/C++ FFI chain is 3 layers deep for 2 math functions

- **The build and runtime path is C++ ? Rust FFI ? PyO3 ? Python.** This is three foreign function boundaries for `cosine_similarity` and `weighted_dot_product`. Each layer adds: platform-specific compilation requirements (MSVC vs GCC divergence already present in `build.rs`), build chain dependencies (`cc`, `cxx`, `pyo3`, `maturin`), and a distinct failure mode. The performance fallback in `calculation_services.py` (pure Python) handles all current load without issue.
  - Location: `AINDY/bridge/memory_bridge_rs/build.rs`, `AINDY/bridge/memory_bridge_rs/src/cpp_bridge.rs`, `AINDY/bridge/memory_bridge_rs/src/lib.rs`, `AINDY/services/calculation_services.py`
  - Mechanism: C++ compiled to `.lib` via `cc` crate; Rust calls it via `extern "C"` unsafe block; PyO3 exposes Rust to Python; Python calls `from memory_bridge_rs import semantic_similarity`.
  - Impact: Build failures on new environments (already observed with Windows AppControl blocking release builds). High onboarding friction. Disproportionate complexity for two BLAS-level operations.
  - Status: Open. Recommendation: retain the kernel only when pgvector semantic search is operational and profiling confirms Python numpy is a bottleneck. Until then, the pure Python fallback is sufficient and the FFI chain is a net liability.

### §10.10 Security — HMAC permission tokens on memory writes are redundant with JWT

- ? **RESOLVED (2026-03-21):** Bridge write routes now rely on JWT; HMAC permission is deprecated and ignored. `trace_permission.py` moved to legacy.

---

## 11. ARM Phase 2 Debt (Deferred from Phase 1 — 2026-03-17)

The following items were explicitly deferred from ARM Phase 1 (commit `f1cd3b5`).
ARM Phase 1 shipped the core engine (analysis, generation, security, DB, router, tests).

### §11.1 Memory Bridge feedback loop
- ? **RESOLVED (2026-03-18 Memory Bridge Phase 3):** `run_analysis()` writes an `"outcome"` node after `db.commit()` (tags: `["arm", "analysis", ext]`). `generate_code()` writes an `"outcome"` node after `db.commit()` (tags: `["arm", "codegen", language]`). `run_analysis()` also recalls prior memory context before prompt build via `recall_memories(query=filename, tags=["arm", "analysis"])`. Both hooks are fire-and-forget (exceptions silenced, main call unaffected).

### §11.2 Self-tuning config via Infinity Algorithm feedback
- ? **FIXED (2026-03-17 ARM Phase 2):** `ARMConfigSuggestionEngine` in
  `services/arm_metrics_service.py` analyzes the 5 Thinking KPI metrics and
  produces prioritized, risk-labelled config suggestions via `GET /arm/config/suggest`.
  Suggestions are advisory only — user applies via `PUT /arm/config`. Low-risk
  suggestions are surfaced in `auto_apply_safe` list for quick application.

### §11.3 Infinity metric crosswalk (Decision Efficiency, Execution Speed)
- ? **FIXED (2026-03-17 ARM Phase 2):** All 5 Infinity Algorithm Thinking KPI
  metrics exposed via `GET /arm/metrics`: Execution Speed, Decision Efficiency,
  AI Productivity Boost, Lost Potential, Learning Efficiency. Calculated by
  `ARMMetricsService` from `analysis_results` + `code_generations` history.

### §11.5 ARM Phase 3 — Memory Bridge feedback loop
- ? **RESOLVED (2026-03-18 Memory Bridge Phase 3).** See §11.1.

### §11.6 ARM Phase 3 — Auto-approve low-risk config changes
- **ARM Phase 2 returns `auto_apply_safe` list** of low-risk suggestions but
  requires user to call `PUT /arm/config` manually. Phase 3 should optionally
  auto-apply low-risk suggestions after each session without user confirmation.
  - Location: `AINDY/services/arm_metrics_service.py`, `AINDY/routes/arm_router.py`
  - Status: ? **PARTIALLY RESOLVED (2026-03-22 Flow Engine Phase B):** ARM workflow execution state now persists to DB via `FlowRun` (flow_runs table). Config state is checkpointed after each node — multi-instance config propagation via flow state. Auto-approve of low-risk suggestions in ARM Phase 3 remains open.

### §11.4 deepseek_arm_service.py is now a dead code path
- ? **RESOLVED (2026-03-22):** `services/deepseek_arm_service.py` moved to `legacy/deepseek_arm_service.py` (not referenced by `arm_router.py`).
  The ARM router was rewritten in Phase 1 to use `DeepSeekCodeAnalyzer` directly.
  The service file remains in place for backward compat but its functions
  (`run_analysis`, `generate_code`, `get_reasoning_logs`, `get_config`,
  `update_config`) are dead code.
  - Location: `AINDY/services/deepseek_arm_service.py`
  - Fix: either delete the file or repurpose it as a thin orchestration layer
    that wraps `DeepSeekCodeAnalyzer` (for callers outside the router).
  - Status: Open. Low priority — no runtime impact.

## 12. Memory Bridge Phase 3 — Open Items (Deferred from Phase 2)

### §12.1 HNSW index for pgvector performance
- **No HNSW or IVFFlat index on `memory_nodes.embedding`.** Currently pgvector uses sequential scan for similarity queries. Acceptable at current node count; will degrade past ~50k rows.
  - Fix: `CREATE INDEX ON memory_nodes USING hnsw (embedding vector_cosine_ops);`
  - Status: **RESOLVED (2026-03-21):** HNSW index added via migration `f3a4b5c6d7e8`.

### §12.2 VALID_NODE_TYPES backward compatibility
- **Existing nodes may have `node_type="generic"` or other legacy values** that the new `validate_node_type` event listener would reject on UPDATE. The listener only fires on `before_insert` / `before_update`; existing rows are safe unless touched.
  - Fix: run a one-time migration to map `"generic"` ? `NULL` or `"insight"` before enabling strict enforcement on updates.
  - Status: Open. Low risk until UPDATE operations are performed on legacy nodes.

### §12.3 Embedding generation is synchronous and blocks the write path
- **`MemoryNodeDAO.save()` calls OpenAI synchronously** before the DB insert. A slow or failed OpenAI API call delays the HTTP response. Failure falls back to zero vector (safe), but latency is not bounded.
  - Fix: generate embeddings async via a task queue (Celery / ARQ) and backfill after insert; return node immediately without embedding then update when ready.
  - Status: Open. Deferred to Phase 3. Current behavior: 3-attempt retry then zero vector.

### §12.4 Phase 3 Workflow hooks — recall() integration
- ? **FULLY RESOLVED (2026-03-18 Sprint 7):** All 5 workflow memory hooks complete. `recall()` is now wired across the full system:
  - ARM analysis: retrieval hook before prompt build (top-3 prior results injected as "Prior analysis memory" section).
  - ARM codegen / Task completion / Genesis lock / Masterplan activate: write hooks persist structured outcome and decision nodes.
  - `bridge.recall_memories()` added as a programmatic bridge function for internal service use (no HTTP round-trip).
  - `bridge.create_memory_node()` upgraded to use `MemoryNodeDAO.save()` (with embedding) from `db.dao.memory_node_dao`.
  - ? **Sprint 7 (2026-03-18):** `genesis_ai.call_genesis_llm()` — recalls past strategic decisions/insights before Reflective Partner response (tags: `genesis`, `masterplan`, `decision`); writes `"insight"` node after each conversation turn. Router updated to pass `user_id` and `db`.
  - ? **Sprint 7 (2026-03-18):** `leadgen_service.run_ai_search()` — recalls past leadgen searches before querying (tags: `leadgen`, `search`, `outcome`); writes `"outcome"` node after results. `create_lead_results()` and router updated to pass `user_id`.
  - All memory hooks are fire-and-forget: exceptions silenced, main call unaffected. `user_id=None` / `db=None` gracefully bypasses all memory operations.
  - Memory hook coverage: **5/5 workflows complete** (ARM analysis, ARM codegen, Task completion, Genesis conversation, LeadGen search).

## 13. Prioritization Table

| Area | Risk Level (Low/Medium/High) | Impact | Recommended Phase |
|------|------------------------------|--------|-------------------|
| Schema / Migration | High | Runtime failures — `create_memory_node()` ImportError on every call | Phase 1 |
| Genesis Router (undefined names) | High | 3 of 5 genesis endpoints raise NameError at runtime | Phase 1 |
| Error Handling | High | Inconsistent client behavior and poor fault isolation | Phase 1 |
| C++ Kernel (wrong-table + import bug) | High | Memory nodes created via services are silently lost + ImportError | Phase 1 |
| **MB §10.1 — children not persisted** | **High** | Every recursive memory trace is silently lost on process exit | **Phase 1** |
| **MB §10.3 — graph traversal absent** | ? Resolved | Multi-hop traversal + traverse endpoint added (Memory Bridge v3) | Phase 1 ? |
| Security (auth missing) | ? Resolved | JWT auth on task/leadgen/genesis/analytics routers (2026-03-17) | Phase 2 ? |
| Concurrency | Medium | Duplicated background work and unbounded loops | Phase 2 |
| Security (CORS + rate limiting) | ? Resolved | CORS locked to explicit origins; SlowAPIMiddleware added (2026-03-17) | Phase 2 ? |
| Testing | Low | Test suite now added; coverage gaps remain | Phase 2 |
| C++ Kernel (embeddings/release build) | Medium | Semantic search inoperable; performance gains unrealized | Phase 2 |
| **MB §10.2 — MemoryTrace shadow state** | **Closed** | Deprecated with runtime warning; DB traces are authoritative | **Done** |
| **MB §10.5 — no embeddings / semantic retrieval impossible** | **Medium** | Primary differentiation of memory system over a log does not function | **Phase 2** |
| **MB §10.4 — strength is VARCHAR** | **Medium** | Graph edge weights are non-numeric; scored traversal blocked until schema migration | **Phase 2** |
| **MB §10.6 — no temporal decay** | **Medium** | Retrieval quality degrades with node count; stale memories rank equal to recent | **Phase 2** |
| **MB §10.7 — unranked tag retrieval** | **Low** | No relevance signal in results; noisy output at scale | **Phase 2** |
| **MB §10.10 — redundant HMAC + JWT auth** | ? Resolved | JWT-only bridge writes; HMAC deprecated | **Phase 3** |
| Observability | Medium | Limited visibility into failures | Phase 3 |
| Structural | Low | Known coupling and in-memory state | Phase 3 |
| **MB §10.8 — no versioning / history table** | ? Resolved | Append-only history table + update logging (Memory Bridge v3) | Phase 3 ? |

## 14. Memory Bridge Phase 4 — Open Items

- ? **Outcome feedback loop.** Implemented in Memory Bridge v4 (feedback counters + adaptive weight + feedback endpoints + auto-feedback hooks).
- ? **Resonance v2.** Implemented in Memory Bridge v4 (semantic + graph + recency + success_rate + usage_frequency).
- ? **Automatic memory capture.** Implemented in Memory Bridge v5 Phase 1 via centralized capture engine (no manual calls).
- ? **Nodus runtime integration.** Implemented in Memory Bridge v5 Phase 1 via `NodusMemoryBridge` + v5 endpoints.
- **Pattern detection.** Detect recurring memory motifs across time windows (e.g., repeated decision?outcome?insight sequences).
- ? **v5 integration:** identity layer implemented (preferences, behavior, evolution) with `/identity/*` endpoints and prompt injection.
- ? **Resolved (2026-03-19):** Nodus stdlib `memory.nd` updated with Memory Bridge helpers (`recall`, `remember`, `suggest`, `record_outcome`) and extended functions.
- ? **RESOLVED (2026-03-19):** v5 Phase 3 — multi-agent shared memory (agent registry, shared/private memory, federated recall).
- **OPEN (2026-03-19):** Identity ML inference — replace rules-only observation with probabilistic or model-driven inference.
- **OPEN (2026-03-19):** SYLVA agent implementation (reserved namespace, inactive system agent).
- **OPEN (2026-03-19):** Embedding-based deduplication in capture engine (Phase 2 note in `MemoryCaptureEngine._is_duplicate`).
- **OPEN (2026-03-19):** Agent trust levels and access policy tiers (future).
| **MB §10.9 — FFI chain depth** | **Low** | 3-layer foreign function boundary for 2 math functions; high build friction | **Phase 3** |

### Line References (Highest-Risk Items)
- Historical note only: background daemon-thread references in `main.py` are obsolete; scheduler leadership now lives in `task_services.start_background_tasks()` and `scheduler_service.start()`.
- Genesis session lock enforcement: `AINDY/services/masterplan_factory.py:15`
- Memory Bridge HMAC validation: removed (JWT-only)
- Canonical metrics unique constraint migration: `AINDY/alembic/versions/97ef6237e153_structure_integrity_check.py:24`
- ? **RESOLVED (2026-03-21):** Health check endpoint mismatch fixed (`/seo/*` pings aligned).
- Duplicate `POST /create_masterplan` definition: `AINDY/routes/main_router.py:236`
- Note: Line numbers are approximate and may shift as files change; re-verify during audits.

---

## 15. Full System Audit — 2026-03-22 — Newly Found Issues

### §15.1 Stale orphan-documentation tests (3 failing)
- ? **RESOLVED (2026-03-22 Quick Wins):** 3 stale documentation tests deleted. `save_memory_node()` was correctly removed; tests that asserted its existence were deleted.
  - Location: `AINDY/tests/test_memory_bridge.py`, `AINDY/tests/test_models.py`

### §15.2 Alembic CLI test broken by entry-point mismatch
- ? **RESOLVED (2026-03-22 Quick Wins):** `test_migrations.py` rewritten. Root cause: local `AINDY/alembic/` directory has `__init__.py` which shadows the installed alembic package when using `python -m alembic`. Fix: use `shutil.which("alembic")` to find the console-script entry point and call it directly. Test skips gracefully if DB is unavailable (test environment) rather than failing.
  - Location: `AINDY/tests/test_migrations.py`

### §15.3 Identity route tests failing — shape mismatch + monkeypatch scope
- ? **RESOLVED (2026-03-22 Quick Wins):** Two fixes applied: (1) `get_evolution_summary()` new-user early-return normalized to include all keys (`total_changes`, `dimensions_evolved`, `most_changed_dimension`, `recent_changes`, `evolution_arc`) with zero/empty values — both code paths now return the same shape. (2) `test_identity_profile_shape` updated to assert real response keys (`communication`, `tools`, `decision_making`, `learning`) instead of non-existent `profile` key.
  - Location: `AINDY/services/identity_service.py`, `AINDY/tests/test_routes_identity.py`

### §15.4 Hardcoded Windows absolute path in production route
- ? **RESOLVED (2026-03-22 Quick Wins):** Replaced hardcoded `r"C:\dev\Coding Language\src"` with `os.environ.get("NODUS_SOURCE_PATH", ...)`. `NODUS_SOURCE_PATH` documented in `.env.example`. The old path remains as a local dev fallback.
  - Location: `AINDY/routes/memory_router.py`, `AINDY/.env.example`

### §15.5 Dual DAO implementations for memory_nodes table
- ? **FIXED (2026-03-23 Sprint N+1):** `load_memory_node()` and `find_by_tags()` added to canonical DAO (`db/dao/memory_node_dao.py`) as aliases. `bridge_router.py` import updated to canonical path. `services/memory_persistence.py` legacy DAO still exists for backward compatibility but is no longer the primary import for any router.
  - Location: `AINDY/services/memory_persistence.py`, `AINDY/db/dao/memory_node_dao.py`, `AINDY/routes/bridge_router.py:13`

### §15.6 Runtime execution loop has 0% test coverage
- **`runtime/memory_loop.py` and `runtime/execution_registry.py` are production code paths with zero test coverage.** The memory loop was the original runtime for the memory execution system and is still relevant as compatibility/runtime residue. This is not a dev tool — untested execution code is a reliability risk.
  - Location: `AINDY/runtime/memory_loop.py`, `AINDY/runtime/execution_registry.py`
  - Fix: Add unit tests for the execution loop state machine and registry. Minimum: test state transitions, error handling, and session lifecycle.
  - Status: ? **RESOLVED (2026-03-22 Flow Engine Phase B):** `services/flow_engine.py` (PersistentFlowRunner) is the new canonical execution backbone, fully covered by `tests/test_flow_engine_phase_b.py` (62 tests). `runtime/memory_loop.py` and `runtime/execution_registry.py` now re-export from `flow_engine` for backward compatibility. Existing `ExecutionLoop` class and `REGISTRY` singleton preserved intact.

### §15.7 Coverage threshold floor is stale
- ? **RESOLVED (2026-03-22 Quick Wins):** `--cov-fail-under` raised from 64 to 69 in `pytest.ini`. Actual coverage: 69.62%.
  - Location: `AINDY/pytest.ini`

### §15.8 `SECRET_KEY` has insecure hardcoded default
- ? **FIXED (2026-03-23 Sprint N+1):** `config.py` validator warns when placeholder is active; `main.py` lifespan raises `RuntimeError` in `is_prod` environments before the server binds. Dev/test environments log a warning but continue.
  - Location: `AINDY/config.py`, `AINDY/main.py`

### §15.9 `PERMISSION_SECRET` is required config for a removed feature
- ? **RESOLVED (2026-03-22 Quick Wins):** `PERMISSION_SECRET` given default empty string in `config.py`. Still referenced by `conftest.py` and `test_security.py` so cannot be removed, but deployments no longer need to set it.
  - Location: `AINDY/config.py`

### §15.10 `get_evolution_summary()` has incompatible return shapes for new vs existing users
- ? **RESOLVED (current workspace):** `IdentityService.get_evolution_summary()` now returns a normalized new-user shape including `total_changes`, `dimensions_evolved`, `most_changed_dimension`, `recent_changes`, and `evolution_arc` alongside the existing informational message.
  - Location: `AINDY/services/identity_service.py`

### §15.11 MongoDB credentials not enforced by config
- ? **RESOLVED (current workspace):** `config.py` now requires `MONGO_URL` for runtime, `db/mongo_setup.py` eagerly validates connectivity with a ping, and `main.py` initializes Mongo during startup so failures happen before request handling.
  - Location: `AINDY/config.py`, `AINDY/db/mongo_setup.py`, `AINDY/main.py`

### §15.12 cpython-314 pycache present alongside cpython-311
- **`modules/deepseek/__pycache__/` contains both cpython-311 and cpython-314 compiled bytecode.** This indicates the project has been executed under Python 3.14 (pre-release as of 2026-03). Mixed pycache creates confusion about which Python version is authoritative and may cause subtle import resolution issues.
  - Location: `AINDY/modules/deepseek/__pycache__/`
  - Fix: Run `find . -name '__pycache__' -type d -exec rm -rf {} +` to clear all pycache; ensure CI and dev environments standardize on Python 3.11.
  - Status: Open. Low priority.

### §15.13 `routes/seo_routes.py` defines `analyze_seo()` twice
- ? **RESOLVED (prior sprint — confirmed 2026-03-22 audit):** Only one `analyze_seo()` definition remains in `routes/seo_routes.py`. The legacy duplicate was moved to `legacy/seo_routes_v1.py` which is not imported by any active router.
  - Location: `AINDY/routes/seo_routes.py`, `AINDY/legacy/seo_routes_v1.py`

### §15.14 Memory Bridge, Identity Layer, Agent Registry had no frontend UI
- ? **RESOLVED (2026-03-22 Make It Visible sprint):** `MemoryBrowser.jsx`, `IdentityDashboard.jsx`, and `AgentRegistry.jsx` created. All 3 routes added to `Sidebar.jsx` and `App.jsx`. 16 API functions added to `api.js`. 27 backend endpoint smoke tests added in `tests/test_memory_browser_ui.py`.

### §15.15 Execution Loop Console — no frontend UI
- ?? **PARTIAL (current workspace):** `ExecutionConsole.jsx` exists and is routed from `client/src/App.jsx`, but it is still a TWR/calculation console rather than a true frontend for the memory execution loop and `/memory/execute*` surfaces.
  - Location: `AINDY/client/src/components/ExecutionConsole.jsx`, `AINDY/runtime/memory_loop.py`, `AINDY/routes/memory_router.py`

### §15.16 RippleTrace viewer — no frontend UI
- ? **RESOLVED (current workspace):** `RippleTraceViewer.jsx` now exists and is routed from `client/src/App.jsx`. The viewer renders a signal timeline and graph-based ripple surface against the active RippleTrace APIs.
  - Location: `AINDY/client/src/components/RippleTraceViewer.jsx`, `AINDY/client/src/App.jsx`

### §15.17 Observability dashboard — no frontend UI
- **Request metrics (`/observability/requests*`) and memory metrics (`/memory/metrics*`) have no frontend dashboard.** System health data is only accessible via raw API or logs.
  - Status: ? **RESOLVED (current workspace):** `ObservabilityDashboard.jsx` now renders request/error metrics, flow status, loop activity, agent execution timeline, system health metrics, and recent `SystemEvent` feed from `GET /observability/dashboard`.

### §15.18 Flow Engine Phase B — Single File Engine integration
- **Flow Engine Phase A replaces daemon threads with APScheduler. Phase B integrates the Nodus Single File Engine** — tasks defined in `.nodus` files should be parseable and executable by the scheduler via `run_task_now()`.
  - Status: ? **RESOLVED (2026-03-22 Flow Engine Phase B):** `services/flow_engine.py` is a clean rewrite of the Single File Engine (`Single File Engine.py`) prototype architecture. `PersistentFlowRunner`, `NODE_REGISTRY`, `FLOW_REGISTRY`, `route_event`, `select_strategy`, `record_outcome`, and `execute_intent` are all implemented and tested. DB-backed execution with WAIT/RESUME, per-node audit trail (flow_history), and adaptive strategy learning (strategies table). ARM analysis, task completion, and LeadGen search flows registered at startup.

### §15.19 Flow Engine Phase C — Genesis ? executable flow
- **Genesis conversation and synthesis are not yet wired to the Flow Engine.** Genesis is a multi-turn, stateful workflow that would benefit from WAIT/RESUME (wait for user message, resume on response). Currently it is a direct LLM call in `genesis_ai.py` with no execution state in DB.
  - Location: `AINDY/services/genesis_ai.py`, `AINDY/routes/genesis_router.py`
  - Status: ? **RESOLVED (2026-03-23 Flow Engine Phase C).** Three genesis nodes registered (`genesis_validate_session`, `genesis_record_exchange`, `genesis_store_synthesis`) + `genesis_conversation` flow with conditional WAIT/RESUME edges. `genesis_router.py POST /genesis/message` co-runs a FlowRun alongside each message (fire-and-forget, non-fatal). FlowRun persists WAIT state between user messages; resumes via `route_event("genesis_user_message", ...)`. Genesis conversation now visible in `/flows/runs`.

### §15.20 Flow Engine Phase D — FlowHistory ? Memory Bridge
- **`flow_history` records every node execution with input/output patches but does not write to Memory Bridge.** High-signal flow completions (ARM analysis, LeadGen, task completion) should generate memory nodes from FlowHistory so execution patterns become retrievable context.
  - Location: `AINDY/services/flow_engine.py` (PersistentFlowRunner.resume), `AINDY/services/memory_capture_engine.py`
  - Status: ? **RESOLVED (2026-03-23 Flow Engine Phase D).** `PersistentFlowRunner._capture_flow_completion()` called automatically on flow SUCCESS. Queries FlowHistory for completed run, builds execution pattern summary (node names, timing, success rate), writes to Memory Bridge via `MemoryCaptureEngine`. Workflow-type ? event-type mapping: arm_analysis?arm_analysis_complete, task_completion?task_completed, leadgen_search?leadgen_search, genesis_conversation?genesis_synthesized. `"flow_completion": 0.5` added to `EVENT_SIGNIFICANCE` for unknown types. Non-fatal.

### §15.21 Known remaining schema drift (intentional skips)
Detected by `alembic revision --autogenerate` on 2026-03-22 post migration `a4c9e2f1b8d3`. All items below are intentionally left alone.

**DB indexes with no ORM declaration (DB has them, ORM doesn't — keep):**
- `ix_automation_logs_source`, `ix_automation_logs_status`, `ix_automation_logs_user_id` — created by migration `37020d1c3951`, not declared as `Index()` on ORM model. Functionally correct, low-priority to add to ORM.
- `ix_memory_nodes_embedding_hnsw` — HNSW pgvector cosine similarity index. **Must not be dropped.** Managed manually via migration `f3a4b5c6d7e8`. Autogenerate will always flag this as "removed" because pgvector HNSW is not introspectable by standard Alembic.
- `ix_request_metrics_path_created_at` — composite index on `(path, created_at)`. Exists in DB, not declared in ORM. Keep.

**DB constraints/FKs not in ORM (keep):**
- `request_metrics_user_id_fkey` — FK from `request_metrics.user_id` ? `users.id`. ORM model doesn't declare it (`user_id` is a plain UUID column with no ForeignKey). FK is valid; removing it would break referential integrity. Keep.
- `background_task_leases_name_key` — implicit unique constraint on `name`. ORM uses `ix_background_task_leases_name` (unique index). Alembic sees this as a constraint rename. Deferred.

**ORM declarations missing from DB (low-priority, non-critical):**
- `ix_request_metrics_id` — ORM declares `index=True` on PK `id`. Primary key is always indexed by PostgreSQL; the named index is redundant. Deferred.

---

## 16. Sprint N+4–N+7 Audit — 2026-03-25

### §16.1 Agentics Phase 1–3 + Observability + Event Log — RESOLVED
- ? **RESOLVED (Sprint N+4, 2026-03-24):** Agent runtime Phase 1 (goal?plan?execute) and Phase 2 (dry-run preview + approval gate) implemented. `services/agent_runtime.py`, `services/agent_tools.py`, `db/models/agent_run.py`, `routes/agent_router.py`.
- ? **RESOLVED (Sprint N+6, 2026-03-25):** Agentics Phase 3 (deterministic execution). `NodusAgentAdapter` + `AGENT_FLOW` wired to `PersistentFlowRunner`. Per-step retry policy. `flow_run_id` linkage. Nodus pip package confirmed NOT usable (separate scripting-language VM).
- ? **RESOLVED (Sprint N+7, 2026-03-25):** Agentics Phase 5 (observability). Stuck-run startup scan, `/recover` and `/replay` endpoints, `replayed_from_run_id` lineage, serializer unification.
- ? **RESOLVED (Sprint N+8, 2026-03-25):** Agent Event Log. `AgentEvent` table, `correlation_id` threading through `AgentRun`/`AgentStep`/`AgentEvent`, `emit_event()`, `GET /agent/runs/{id}/events` merged timeline, `AgentConsole.jsx` Timeline tab + pending-approval badge.

### §16.2 `new_plan` replay mode — RESOLVED
- ? **RESOLVED (Sprint N+8, 2026-03-25):** `replay_run(mode="new_plan")` re-calls GPT-4o with the original goal to generate a fresh plan. New run is created via `_create_run_from_plan()` with new `correlation_id` and `REPLAY_CREATED` event emitted with `{original_run_id, mode: "new_plan"}`. The prior approval does not carry forward — trust gate re-evaluated on new run.

### §16.3 Agent capability/policy system missing — Resolved
- ? **RESOLVED (Sprint N+10, 2026-03-26):** Scoped capability enforcement now exists. Tool registry entries carry capability metadata, `AgentTrustSettings.allowed_auto_grant_tools` defines static policy, `AgentRun.capability_token` stores per-run scoped grants, approve-time preflight blocks ungrantable plans, and step-time enforcement in `services/nodus_adapter.py` fails closed with `CAPABILITY_DENIED`.
  - Location: `AINDY/services/capability_service.py`, `AINDY/services/agent_runtime.py`, `AINDY/services/nodus_adapter.py`
  - Outcome: approved runs can no longer invoke arbitrary tools outside their scoped token; `genesis.message` remains manual-approval only.

### §16.4 `WatcherSignal.user_id` migration not chained cleanly — Low priority
- ? **RESOLVED (current workspace):** `watcher_signals.user_id` is now UUID-backed with `ForeignKey("users.id")`. The older String-based note is stale.
  - Location: `AINDY/db/models/watcher_signal.py`

### §16.5 Agent approval inbox has no dedicated UI — Resolved
- ? **RESOLVED (current workspace):** A dedicated approval surface now exists in `AINDY/client/src/components/AgentApprovalInbox.jsx`, routed at `/agent/approvals` from `AINDY/client/src/App.jsx`.
- ? **RESOLVED (current workspace):** Sidebar-level pending approval visibility now exists in `AINDY/client/src/components/Sidebar.jsx` via the approval count badge and `APPROVAL_EVENT` refresh hook.

### §16.6 [AGENTICS] Real Nodus execution is not the primary execution path — Open
- **Agentics currently runs on A.I.N.D.Y.'s internal flow engine, not on the installed Nodus DSL/VM runtime.** `services/nodus_adapter.py` is a wrapper over `PersistentFlowRunner` in `services/flow_engine.py`. The actual installed `nodus` runtime is only used by `services/nodus_execution_service.py` behind `POST /memory/nodus/execute`.
  - Current consequence: the system has working deterministic execution, but it is not yet aligned with the intended architecture where Nodus is the primary execution substrate.
  - Missing pieces:
    - no `.nd` workflow assets in the repo
    - no agent-plan-to-Nodus compilation path
    - no VM trace mapping into `FlowRun`, `AgentEvent`, or `SystemEvent`
  - Status: Open. High architectural importance.

### §16.7 [AGENTICS] Dual execution model causes architectural drift — Open
- **There are now two workflow/execution surfaces with different semantics:**
  - `services/flow_engine.py` for core runtime orchestration
  - `services/nodus_execution_service.py` for embedded Nodus source execution
- This split is manageable short-term, but it creates naming confusion, duplicated execution concepts, and drift away from the intended Nodus-centered execution architecture.
  - Primary files: `AINDY/services/flow_engine.py`, `AINDY/services/nodus_adapter.py`, `AINDY/services/nodus_execution_service.py`, `AINDY/routes/memory_router.py`
  - Status: Open. Structural debt.

### §16.8 [AGENTICS] Infinity loop is integrated but not autonomous — Open
- **The Infinity loop is now closed and memory-weighted, but the decision engine is still shallow and post-hoc.** `services/infinity_loop.py` now consumes ranked memory signals in addition to KPI and feedback context, and persists `LoopAdjustment` / `UserFeedback`, but it does not yet:
  - create bounded autonomous agent runs from its own decisions
  - learn from `UserFeedback` to change decision thresholds or KPI weights
  - implement expected-vs-actual scoring across agent outcomes
  - coordinate with capability/approval policy as a true autonomous controller
  - Status: Open. Medium effort, high strategic importance.

### §16.9 [AGENTICS] SystemEvent coverage is broader, but execution-envelope coverage is still incomplete
- ? **PARTIALLY RESOLVED (current workspace):** `SystemEvent` is now the canonical durable activity ledger for core execution plus outbound external interactions. External OpenAI/HTTP/watcher/health-probe calls fail closed on missing required event emission.
- ? **Further resolved (current workspace):** successful health/auth/async heavy-execution paths now also emit durable success events (`health.liveness.completed`, `health.readiness.completed`, `auth.register.completed`, `auth.login.completed`, `execution.started`, `execution.completed`) and were verified against a live compose deployment.
- ? **Further resolved (current workspace):** parent-child event stitching, causal `RippleEdge` creation, and `stored_as_memory` links now make execution traces reconstructable across `SystemEvent` and Memory Bridge.
- **Still open:** event coverage is stronger than full execution normalization. Agent runs, flow runs, async jobs, and embedded Nodus tasks do not yet share one normalized execution record model.
  - Status: Open. Structural follow-through still required.

### §16.10 [AGENTICS] Multi-agent coordination is still absent — Open
- **Agentics is still effectively single-agent.** Memory federation exists (`/memory/agents`, federated recall, shared/private memory), but there is no runtime delegation model, no parent/child run structure, and no inter-agent approval/capability boundary.
  - Primary files: `AINDY/routes/memory_router.py`, `AINDY/bridge/nodus_memory_bridge.py`, `AINDY/services/agent_runtime.py`, `AINDY/db/models/agent.py`
  - Status: Open. Major functional gap.

## 17. Current Workspace Audit — Newly Documented Debt

### §17.1 Search / SEO frontend-backend contract drift
- ? **RESOLVED (current workspace):** Compatibility routes now exist for `/analyze_seo/`, `/generate_meta/`, and `/suggest_improvements/`, and shared search orchestration lives in `services/search_service.py`.
  - Location: `AINDY/client/src/api.js`, `AINDY/routes/seo_routes.py`, `AINDY/services/search_service.py`

### §17.2 Logging standardization is incomplete
- **`print(...)` remains in database/bootstrap code paths.** Core routes/services mostly use `logger`, but `db/database.py` and `db/create_all.py` still emit raw prints, so logging is not fully standardized.
  - Location: `AINDY/db/database.py`, `AINDY/db/create_all.py`
  - Status: Open. Low priority, but still real debt.

### §17.3 Mongo configuration remains late-bound
- ? **RESOLVED (current workspace):** Mongo is now part of the validated runtime config. Missing or unreachable `MONGO_URL` fails startup instead of surfacing later during execution.
  - Location: `AINDY/config.py`, `AINDY/db/mongo_setup.py`, `AINDY/main.py`

### §17.4 TECH_DEBT historical statuses can drift from live system state
- **Historical audit entries now contain stale open items that are already resolved in the workspace** (for example MasterPlan anchor/ETA, RippleTrace viewer, Observability dashboard, and normalized identity evolution summary). This document therefore needs periodic alignment to remain trustworthy as an audit artifact.
  - Location: `AINDY/docs/roadmap/TECH_DEBT.md`
  - Status: Open. Low priority documentation debt.

### §17.5 New causal-memory and memory-weighted Infinity path lacks end-to-end scenario coverage
- **The new SystemEvent -> RippleTrace -> Memory Bridge -> Infinity signal path is implemented, but it does not yet have dedicated end-to-end tests that prove a high-impact failure changes the next Infinity decision on a subsequent run.**
  - Location: `AINDY/services/system_event_service.py`, `AINDY/services/memory_capture_engine.py`, `AINDY/services/rippletrace_service.py`, `AINDY/services/memory_scoring_service.py`, `AINDY/services/infinity_orchestrator.py`, `AINDY/services/infinity_loop.py`
  - Status: Open. Medium priority because this is now a strategic behavior path.

### §17.6 Automatic behavioral feedback path lacks scenario coverage
- **Retries, latency spikes, abandonment detection, and repeated-failure signals now emit feedback events and auto-capture into memory, but they do not yet have dedicated scenario tests proving signal emission and downstream decision impact.**
  - Location: `AINDY/services/system_event_service.py`, `AINDY/services/async_job_service.py`, `AINDY/services/memory_capture_engine.py`, `AINDY/services/memory_scoring_service.py`
  - Status: Open. Medium priority.

### §17.7 Native memory scorer is integrated, but production hardening is incomplete
- **The memory scoring hot path now uses the Rust/C++ bridge directly, but production hardening is still incomplete.** The runtime scorer has a safe Python fallback and focused parity tests, but release-mode packaging/benchmark validation and traversal-side native acceleration are still not done.
  - Location: `AINDY/runtime/memory/scorer.py`, `AINDY/runtime/memory/native_scorer.py`, `AINDY/bridge/memory_bridge_rs/src/lib.rs`, `AINDY/tests/integration/test_memory_native_scorer.py`
  - Status: Open. Medium priority.

