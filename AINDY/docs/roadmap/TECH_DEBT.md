# Technical Debt Inventory

This document inventories current technical debt based strictly on the existing implementation. It does not propose redesigns or new systems.

## 1. Structural Debt
- Background tasks are implemented as daemon threads in `AINDY/main.py` with no scheduler or supervision.
- Long-running loop variants exist in `AINDY/services/task_services.py` but are not managed by a job system.
- Gateway (`AINDY/server.js`) stores users in an in-memory array with no persistence.
- Gateway lacks state durability across restarts (`AINDY/server.js`).
- Search System is fragmented across SEO, LeadGen, and Research modules with no unified pipeline; live retrieval is missing in LeadGen and Research. Canonical reference: `docs/roadmap/SEARCH_SYSTEM.md`.
- Freelancing System lacks automation and AI generation; metrics are incomplete and memory logging uses a legacy DAO path. Canonical reference: `docs/roadmap/FREELANCING_SYSTEM.md`.
- Social Layer lacks visibility scoring and persistent bridge event logging; memory logging for posts is non-persistent. Canonical reference: `docs/roadmap/SOCIAL_LAYER.md`.
- RippleTrace remains signal-capture only; pattern engine, graph layer, and insight engine are not implemented. Canonical reference: `docs/roadmap/RIPPLETRACE.md`.
- Masterplan SaaS lacks a masterplan anchor (target state), ETA projection, and dependency cascade modeling; current implementation is planning + activation only. Canonical reference: `docs/roadmap/MASTERPLAN_SAAS.md`.
- ✅ **FIXED (2026-03-18 Sprint 4):** `main.py` deprecated `@app.on_event("startup")` handlers replaced with a single `@asynccontextmanager lifespan` function. Both startup handlers (cache init + system identity seeder) merged into one lifespan. Deprecation warnings eliminated (11 → 7 warnings in test suite).
- ✅ **FIXED (2026-03-18 Sprint 4 Auth Hardening):** Pydantic v1 deprecations removed — `schemas/freelance.py` (3× `class Config: orm_mode = True` → `model_config = ConfigDict(from_attributes=True)`), `schemas/analytics_inputs.py` (`@validator` → `@field_validator` with `@classmethod`), `schemas/research_results_schema.py` (`class Config: from_attributes = True` → `model_config = ConfigDict(from_attributes=True)`). Deprecation warnings reduced from 7 → 1.
- ✅ **FIXED (2026-03-18 Sprint 6):** SQLAlchemy 2.0 migration complete. `db/database.py:9` `from sqlalchemy.ext.declarative import declarative_base` → `from sqlalchemy.orm import declarative_base`. The final deprecation warning is eliminated. Deprecation warnings: 0. No other files used the old import path (`Base` was defined once and all models import it from `db.database`).
- ✅ **FIXED (2026-03-18 Sprint 4):** `main.py` startup DB session leak resolved. The unused `db = SessionLocal()` at startup has been removed. The system identity seeder now uses a proper `try/finally` block with `db.close()`.
- ✅ **FIXED (2026-03-18 Sprint 4):** Duplicate `get_db()` definitions removed from `main_router.py` and `analytics_router.py`. Both now import `get_db` from `db.database`. Single canonical definition.
- ✅ **FIXED (2026-03-20 Security Sprint):** `health_router.py` now imports `seo_services` and `memory_persistence` from `services.*`, avoiding `ModuleNotFoundError` when `PYTHONPATH` does not include `AINDY/services/` directly.
- ✅ **FIXED (2026-03-18 Sprint 4):** `bridge_router.py` duplicate `create_engine`/`sessionmaker` imports removed.
- **OPEN (2026-03-18 Audit):** `services/master_index_service.py2.py` has an invalid Python filename (`.py2.py`). Python cannot import a file with this name. Either rename it or remove it.
- ✅ **FIXED (2026-03-18 Sprint 4):** `task_router.py POST /tasks/complete` now passes `user_id=current_user["sub"]` to `complete_task()`. Memory Bridge Phase 3 task completion hook now fires from the API.
- **OPEN (2026-03-18 Audit):** `social_router.py POST /social/post` calls `create_memory_node()` without a `db` session argument. `bridge.create_memory_node()` requires a DB session to persist via `MemoryNodeDAO`. Without it the function creates a transient `MemoryNode` and returns without writing to the database. The memory write for social posts silently does nothing (`AINDY/routes/social_router.py`).
- **OPEN (2026-03-22 Audit):** `services/research_results_service.py::log_to_memory_bridge()` calls `create_memory_node()` without a `db` session argument. The memory write is non-persistent and silently drops the node.
- **OPEN (2026-03-22 Audit):** `services/freelance_service.py::create_order()` uses legacy `services.memory_persistence.MemoryNodeDAO.save_memory_node()` (no embeddings, no user_id), bypassing the Memory Bridge v5 DAO and capture engine.
- **OPEN (2026-03-22 Audit):** `services/leadgen_service.py::create_lead_results()` calls `create_memory_node()` with `user_id=None`, creating unowned memory nodes in `memory_nodes`.
- **OPEN (2026-03-22 Audit):** `services/leadgen_service.py::score_lead()` calls `client.chat.completions.create(... input=...)` (chat API expects `messages`) and contains dead code after the first `return`.
- **OPEN (2026-03-22 Audit):** Duplicate `generate_meta_description()` is defined twice in `services/seo_services.py`.
- **OPEN (2026-03-22 Audit):** `client/src/components/RevenueScalingPanel.jsx` is wired to `calculateIncomeEfficiency()` and uses income-efficiency labels; no revenue-scaling endpoint is called.
- ✅ **FIXED (2026-03-20 Security Sprint):** Frontend auth regressions resolved — all listed components now use `client/src/api.js` functions backed by `authRequest()`.
- ✅ **FIXED (2026-03-20 Security Sprint):** Frontend/backend contract mismatches resolved — `AnalyticsPanel.jsx` uses `/analytics/masterplan/{id}/summary`, and `LeadGen.jsx` maps `{results}` with `overall_score` + `reasoning`.
- ✅ **FIXED (2026-03-20 Security Sprint):** `Dashboard.jsx` stray JSX removed.
- Implicit coupling exists between:
- `AINDY/routes/social_router.py` and `AINDY/bridge/bridge.py` (social post logging invokes memory bridge creation).
- `AINDY/routes/health_router.py` and `AINDY/routes/seo_routes.py` via hardcoded endpoint paths.
- Health checks are present (`/health/`, `/dashboard/health`) but no readiness gating is implemented (`AINDY/routes/health_router.py`, `AINDY/routes/health_dashboard_router.py`).
- `POST /bridge/user_event` accepts user join events and responds `{"status": "logged"}` but only calls `print()`; no persistence to any table and no RippleTrace event emitted (`AINDY/routes/bridge_router.py:159`).
- `AINDY/bridge/trace_permission.py` defines `trace_permission()` but is not imported or used anywhere; not exported from `bridge/__init__.py`. Either wire it into `bridge_router.py` as a permission log layer or delete it (`AINDY/bridge/trace_permission.py`).
- `AINDY/bridge/archive/` contains two files pending team confirmation of deletion: `memory_bridge_core_draft.rs` and `Memorybridgerecognitiontrace.rs`.

## 2. Schema / Migration Debt
- Migration drift risk exists due to multiple overlapping migrations and no automated migration validation in deployment (`AINDY/alembic/versions/`).
- Some application-level constraints are not enforced at DB level (e.g., session locking is application logic in `AINDY/services/masterplan_factory.py`).
- Many tables lack explicit foreign keys, making referential integrity dependent on application logic (`AINDY/db/models/*.py`).
- Cascade rules are sparse; only a subset of relationships define cascades (`AINDY/db/models/arm_models.py`, `AINDY/db/models/masterplan.py`).
- **OPEN (2026-03-21):** Legacy rows in `tasks`, `leadgen_results`, and `authors` may have `user_id = NULL` after ownership migration. Backfill or cleanup needed to avoid orphaned records.
- ✅ **RESOLVED (2026-03-21):** `tasks.user_id` added (nullable) with user-scoped routing in `task_router.py` and user_id enforcement in `task_services.py`. Existing legacy rows without `user_id` no longer appear in user-scoped queries.
- ✅ **RESOLVED (2026-03-21):** `leadgen_results.user_id` added (nullable) with user-scoped routing in `leadgen_router.py`. New writes require `user_id` and are filtered per user.
- **OPEN (2026-03-18 Audit):** `MasterPlan` has both `version` (String) and `version_label` (String) — redundant columns with overlapping semantics (`AINDY/db/models/masterplan.py`). Requires a clean-up migration.
- **OPEN (2026-03-18 Audit):** `GenesisSessionDB` has both `user_id` (Integer, legacy) and `user_id_str` (String, new) — dual ownership columns in the same row (`AINDY/db/models/masterplan.py`). Requires deprecating `user_id` Integer and migrating all FK references to `user_id_str`.
- **OPEN (2026-03-18 Audit):** `CanonicalMetricDB.user_id` is `Integer, nullable, no FK` — not referencing `users.id`. Any user_id stored here is unverifiable and non-relational (`AINDY/db/models/metrics_models.py:145`).
- ✅ **FIXED (2026-03-18 Sprint 4):** `bridge_router.py` `node_type="generic"` defaults changed to `None` in `NodeCreateRequest` schema and `_NodeLike` inner class. `NodeResponse.node_type` updated to `Optional[str]`. ORM event validator crash eliminated.
- ✅ **FIXED (2026-03-18 Sprint 4):** `services/memory_persistence.py::MemoryNodeDAO.save_memory_node()` fallback changed from `"generic"` to `None`. ORM event violation path removed.
- **OPEN (2026-03-18 Audit):** `AINDY/version.json` and `AINDY/system_manifest.json` still report version `0.9.0-pre`. Current release is post-v1.0.0. These are stale and not auto-updated.
- ~~**`bridge/bridge.py::create_memory_node()` writes to the wrong table.**~~ ✅ **FIXED (2026-03-18 Memory Bridge Phase 1):** Fully rewritten to write `MemoryNodeModel` rows via `MemoryNodeDAO` (table: `memory_nodes`). New signature: `(content, source, tags, user_id, db, node_type)`. All three callers updated. Regression tests added and bug-documenting tests flipped.
- Orphan `save_memory_node(self, memory_node)` defined at module level in `AINDY/services/memory_persistence.py:16`; takes `self` as first parameter but is not a method of any class. Would raise `TypeError` if called. The `MemoryNodeDAO.save_memory_node()` method below it handles persistence correctly; this function is dead code and should be removed.
- `AINDY/version.json` and `AINDY/system_manifest.json` report version `0.9.0-pre`; current release is `1.0.0` (Social Layer). These are not updated automatically and are stale.

## 3. Testing Debt
- Minimal unit coverage in `AINDY/services/`.
- Integration tests are limited to calculation endpoints (`test_calculations.py`, `test_routes.py`).
- No automated migration validation tests (`AINDY/alembic/` has no test harness).
- ✅ **FIXED (2026-03-18 CI/CD Sprint):** CI pipeline live. GitHub Actions `ci.yml` runs lint (ruff) + tests (pytest + coverage) on every push and PR to `main`. Coverage threshold: 64% (baseline: 69%). Coverage XML uploaded to Codecov. PR template, CODEOWNERS, SECRETS.md, and `.env.example` added.
- ✅ **FIXED (2026-03-18 CI/CD Sprint):** Coverage metrics tooling configured. `pytest-cov==7.0.0` + `.coveragerc` added. Baseline: 69%. CI threshold: 64% (`--cov-fail-under=64`). XML report generated and uploaded to Codecov on every push/PR.
- Duplicate test names in `test_routes.py` can mask failures (`test_routes.py`).
- `AINDY/bridge/smoke_memory.py` has broken imports: `from base import Base` and `from memory_persistence import MemoryNodeDAO` both fail with `ModuleNotFoundError`. Correct paths are `from db.database import Base` and `from services.memory_persistence import MemoryNodeDAO` (`AINDY/bridge/smoke_memory.py`).
- `AINDY/bridge/Bridgeimport.py` is a 12-line manual import test with no `if __name__ == "__main__"` guard; it runs immediately on import and has no pytest structure. Move to `tests/` as a proper pytest test or add the guard (`AINDY/bridge/Bridgeimport.py`).

## 4. Error Handling Debt
- Error classification is inconsistent across routes (`AINDY/routes/*`).
- Structured JSON error format is not enforced (`AINDY/routes/*`).
- ~~Missing retry logic for external model providers (`AINDY/services/genesis_ai.py`).~~ **FIXED (2026-03-17 Genesis Block 4):** `validate_draft_integrity()` implements 3-attempt retry loop with fail-safe fallback. ~~`deepseek_arm_service.py`~~ — **FIXED (2026-03-17 ARM Phase 1):** `DeepSeekCodeAnalyzer._call_openai()` implements retry with configurable `retry_limit` and `retry_delay_seconds`.
- Logging is mixed between `print(...)` and logging module; no structured logging (`AINDY/config.py`, multiple routes/services).

## 5. Concurrency Debt
- Background loops can block or run indefinitely without supervision (`AINDY/services/task_services.py`).
- No distributed-safe scheduler; multi-instance deployment risks duplicated background work (`AINDY/main.py` daemon threads).
- No explicit controls for thread lifecycle or shutdown coordination (`AINDY/main.py`).

## 6. Security Debt
- ✅ **FIXED (2026-03-17 Phase 2):** Rate limiting added — `SlowAPIMiddleware` registered in `main.py` with per-IP limiting via `slowapi`. AI endpoints (genesis, leadgen) can be rate-limited with `@limiter.limit()` decorator.
- ✅ **FIXED (2026-03-17 Phase 2):** JWT authentication added to user-facing route groups: `task_router`, `leadgen_router`, `genesis_router`, `analytics_router`. Dependency: `Depends(get_current_user)` from `services/auth_service.py`. Auth routes at `POST /auth/login`, `POST /auth/register` are public.
- ✅ **FIXED (2026-03-17 Phase 2):** CORS wildcard replaced — `allow_origins=["*"]` replaced with `ALLOWED_ORIGINS` read from `.env` environment variable. Default: localhost origins. No longer uses wildcard + credentials combination.
- ✅ **FIXED (2026-03-17 Phase 3):** Node gateway auth wired — `server.js` now loads `AINDY_API_KEY` from `.env` via `dotenv` and sends `X-API-Key` header on all FastAPI service calls. `POST /network_bridge/connect` and `POST /network_bridge/user_event` are now API-key protected; gateway sends the key.
- ✅ **FIXED (2026-03-17 Phase 3):** User ORM model created — `db/models/user.py` (`users` table: UUID PK, unique email/username indexes, `hashed_password`, `is_active`). Migration `37f972780d54` applied. `auth_router.py` replaced in-memory `_USERS` dict with `register_user()` / `authenticate_user()` from `auth_service.py` via `Depends(get_db)`.
- ✅ **FIXED (2026-03-17 Phase 3):** All remaining unprotected routes secured. JWT (`get_current_user`): `seo_routes`, `authorship_router`, `arm_router`, `rippletrace_router`, `freelance_router`, `research_results_router`, `dashboard_router`, `social_router`. API key (`verify_api_key`): `db_verify_router`, `network_bridge_router`. Zero unprotected non-public routes remain.
- ✅ **FIXED (2026-03-17 Phase 3):** Rate limiting decorators applied to all AI/cost endpoints — `@limiter.limit()` on `/leadgen/` (10/min), `/genesis/message` (20/min), `/genesis/synthesize` (5/min), `/arm/analyze` (10/min), `/arm/generate` (10/min). Shared `Limiter` extracted to `services/rate_limiter.py`.
- No documented secret rotation policy (`AINDY/routes/bridge_router.py` uses env secret without rotation).
- HMAC protection exists for Memory Bridge writes but no replay protection beyond TTL (`AINDY/routes/bridge_router.py`).
- `SECRET_KEY` default is insecure placeholder — must be set to a cryptographically random value in production `.env`.
- ✅ **FIXED (2026-03-18 Sprint 4):** `GET /dashboard/health` now requires JWT auth. `dependencies=[Depends(get_current_user)]` added to `health_dashboard_router.py` router level.
- ✅ **FIXED (2026-03-18 Sprint 4 Auth Hardening):** `GET /bridge/nodes`, `POST /bridge/nodes`, and `POST /bridge/link` now require JWT (`Depends(get_current_user)` added per-endpoint). `POST /bridge/user_event` now requires API key (`Depends(verify_api_key)`). All bridge endpoints are now protected.
- ✅ **RESOLVED (2026-03-21):** `POST /tasks/recurrence/check` now requires JWT (`Depends(get_current_user)`).
- ✅ **FIXED (2026-03-18 Sprint 4 Auth Hardening):** All calculation endpoints in `main_router.py` now require JWT. `dependencies=[Depends(get_current_user)]` added at router level. Covers `/calculate_twr`, `/calculate_effort`, all Infinity Algorithm endpoints, `/results`, `/masterplans`, and `/create_masterplan`. Rate-limit bypass vector closed.
- ✅ **PARTIALLY FIXED (2026-03-18 Sprint 4 Auth Hardening):** `GET /analytics/masterplan/{id}` and `/analytics/masterplan/{id}/summary` now verify MasterPlan ownership via `MasterPlan.user_id == current_user["sub"]` before returning results. Returns 404 for wrong owner.
- ✅ **FIXED (2026-03-18 Sprint 5):** Freelance cross-user exposure closed. Migration `d37ae6ebc319` adds `user_id` to `freelance_orders` and `client_feedback`. `create_order()` and `collect_feedback()` now set `user_id` from JWT. `get_all_orders()` and `get_all_feedback()` filter by `user_id`. `POST /deliver/{id}` verifies ownership before delegating.
- ✅ **FIXED (2026-03-18 Sprint 5):** Research cross-user exposure closed. Migration adds `user_id` to `research_results`. `create_research_result()` sets `user_id`. `get_all_research_results()` filters by `user_id`.
- ✅ **FIXED (2026-03-18 Sprint 5):** Rippletrace cross-user exposure closed. Migration adds `user_id` to `drop_points` and `pings`. All 6 service functions accept `user_id`. All router endpoints pass `current_user["sub"]`. System-internal `log_ripple_event()` calls pass `user_id=None` (system events are unowned).
- ✅ **RESOLVED (2026-03-21):** `leadgen_results.user_id` added and `GET /leadgen/` is user-scoped.
- ✅ **FIXED (2026-03-18 Sprint 4 Auth Hardening):** `GET /memory/nodes/{node_id}` now enforces ownership — returns 404 if `node.user_id != current_user["sub"]`. Cross-user node reads blocked.
- ✅ **FIXED (2026-03-18 Sprint 4):** `.env` orphan bare Google API key on line 7 removed. `.env` now parses cleanly with no floating values.
- **OPEN (2026-03-18 Audit):** `task_services.complete_task()` updates MongoDB with hardcoded `username: "me"` regardless of which user completed the task. Social velocity metrics are not user-scoped (`AINDY/services/task_services.py:121`).
- ✅ **FIXED (2026-03-20 Security Sprint):** Memory tag search, link traversal, and link creation are user-scoped. `GET /memory/nodes` and `GET /memory/nodes/{id}/links` filter by `user_id`, and `POST /memory/links` verifies ownership before linking.
- ✅ **FIXED (2026-03-20 Security Sprint):** `/bridge/nodes` now uses `MemoryCaptureEngine` and sets `user_id` (when provided) plus `source_agent` for federation tagging.
- ✅ **FIXED (2026-03-20 Security Sprint):** `POST /analytics/linkedin/manual` now verifies `MasterPlan.user_id == current_user["sub"]` and returns 404 when not owned.
- ✅ **FIXED (2026-03-20 Security Sprint):** `GET /masterplans` and `GET /results` now filter by `user_id`, and `POST /create_masterplan` sets `user_id` from JWT. `calculation_results.user_id` added with migration `c1f2a9d0b7e4`.
- ✅ **FIXED (2026-03-20 Security Sprint):** `POST /social/profile` upserts are scoped by `user_id` and block cross-user overwrites.
- ✅ **FIXED (2026-03-18 Sprint 4):** `client/src/api.js` — all protected endpoints now use `authRequest()`. ARM (analyze/generate/logs/config/metrics/suggest), Tasks (create/list/start/complete), Social (profile/feed/post), Research (query), and LeadGen now all send the JWT Bearer token. `runLeadGen` refactored from raw `fetch()` to `authRequest()`. `authRequest` definition moved before first use.
- **OPEN (2026-03-22 Audit):** `GET /calculate_twr` uses `MasterPlan.active_plan/origin_plan` and `CalculationResult.twr_history` without `user_id` scoping; cross-user data exposure (`AINDY/routes/main_router.py`).
- ✅ **RESOLVED (2026-03-21):** `dashboard_router.py` overview queries are scoped by `current_user["sub"]`; `authors.user_id` added for ownership filtering.
- ✅ **RESOLVED (2026-03-21):** `GET /bridge/nodes` now filters by `current_user["sub"]` via `MemoryNodeDAO.find_by_tags(..., user_id=...)`.
- ✅ **RESOLVED (2026-03-21):** `POST /bridge/nodes` now enforces `current_user["sub"]` and ignores caller-supplied `user_id`.
- **OPEN (2026-03-22 Audit):** `client/src/components/InfiniteNetwork.jsx` makes raw `axios` calls to `http://localhost:5000` without `authRequest()`/JWT; bypasses frontend auth path.

## 7. Observability Debt
- Logging granularity is limited; several routes rely on `print(...)` statements (`AINDY/routes/*`, `AINDY/services/*`).
- No centralized logging or tracing infrastructure (no config or tooling present).
- No metrics instrumentation beyond DB logging in `AINDY/routes/health_router.py`.
- Infinity Algorithm Support System remains open-loop (Watcher missing, feedback not enforced, task priority unused). Canonical reference: `docs/roadmap/INFINITY_ALGORITHM_SUPPORT_SYSTEM.md`.

## 8. C++ Semantic Kernel Debt

The C++ semantic similarity kernel (`bridge/memory_bridge_rs/`) was added in `feature/cpp-semantic-engine`. The following items must be resolved before the kernel is production-ready.

- **Release build blocked by Windows AppControl.** The kernel was built in debug mode because AppControl policy blocks writes to `target/release/`. Debug benchmark (dim=1536, 10k iters): Python 2.753s vs C++ 3.844s — FFI overhead dominates in debug. Release build is expected to show 10–50x improvement. Action: run `maturin develop --release` in an environment without AppControl restrictions (deployment server or CI) and record results (`AINDY/bridge/benchmark_similarity.py`, `AINDY/bridge/memory_bridge_rs/Cargo.toml`).
- ~~**No vector embeddings on `MemoryNode`.**~~ ✅ **RESOLVED (2026-03-18 Memory Bridge Phase 2):** `embedding VECTOR(1536)` column added to `MemoryNodeModel` (`services/memory_persistence.py`) and DB via migration `mb2embed0001`. `services/embedding_service.py` generates OpenAI `text-embedding-ada-002` embeddings on every `MemoryNodeDAO.save()` call. C++ kernel (`memory_bridge_rs.semantic_similarity`) wired for cosine similarity with Python fallback. `find_similar()` uses pgvector `<=>` operator. Endpoints: `POST /memory/nodes/search`, `POST /memory/recall`.
- **`PERMISSION_SECRET` defaults to `"dev-secret-must-change"`.** If `PERMISSION_SECRET` is not set in `.env`, HMAC signing uses this default. Any party who knows the default can forge valid permissions. This is a deployment configuration risk, not a code defect, but no rotation policy or validation on startup enforces that the secret has been changed (`AINDY/routes/bridge_router.py:21`).

## 9. Newly Revealed Bugs (Diagnostic Test Suite — 2026-03-17)

The following bugs were revealed by the comprehensive diagnostic test suite added in `feature/cpp-semantic-engine`. All items below were confirmed by failing tests in `AINDY/tests/`.

### §2 Schema / Migration (additions)
- ~~**`bridge/bridge.py::create_memory_node()` also has a broken import path.**~~ ~~**IMPORT PATH FIXED (2026-03-17):** Import corrected.~~ ✅ **FULLY FIXED (2026-03-18 Memory Bridge Phase 1):** `CalculationResult` no longer referenced at all. `create_memory_node()` fully rewritten to use `MemoryNodeDAO`. Both the import bug and the wrong-table bug are resolved. Revealed by: `test_memory_bridge.py::TestCreateMemoryNodeWrongTable` (now a regression guard).

### §1 Structural (additions)
- **`routes/genesis_router.py` has three undefined name references.** ~~(1) `POST /genesis/synthesize` calls `call_genesis_synthesis_llm()` — NameError. (2) `POST /genesis/lock` calls `create_masterplan_from_genesis()` — NameError. (3) `POST /genesis/{plan_id}/activate` references `MasterPlan` — NameError.~~ ~~**CRASHES FIXED (2026-03-17):** All three missing imports added. LLM synthesis remains a stub.~~ ✅ **FULLY RESOLVED (2026-03-17 Genesis Blocks 1-3):** `call_genesis_synthesis_llm()` replaced with real GPT-4o call. `determine_posture()` implemented with real Stable/Accelerated/Aggressive/Reduced logic. All routes user-scoped. Two new GET endpoints added. `masterplan_router.py` created. Migration `a1b2c3d4e5f6` applied. 22 new tests pass.
- **`services/leadgen_service.py::score_lead()` contains dead/unreachable code.** The function has two `try:` blocks, but the second is entirely unreachable because the first block always returns (or raises). The dead block calls `client.chat.completions.create(model="gpt-4o", ...)` — a different model than the live block — which is neither tested nor executed. Fix: remove the dead block (`AINDY/services/leadgen_service.py:104-127`). Revealed by: `test_routes_leadgen.py::TestLeadGenServiceBugs::test_score_lead_has_dead_code_after_return`.
- **`routes/seo_routes.py` defines `analyze_seo()` twice.** The function is defined at line 17 and again at line 39. Python silently uses the second definition, making the first (basic) implementation unreachable. The duplicate also appears in the router — both map to `POST /analyze_seo/`. The second definition (`POST /seo/analyze`) works but shares a name with the dead first one (`AINDY/routes/seo_routes.py:17,39`).
- **`routes/dashboard_router.py` and `routes/health_dashboard_router.py` both use prefix `/dashboard`.** This creates a route collision on `/dashboard/health`. FastAPI registers both but the last-registered takes precedence. The `dashboard_router.py` (overview) path is `/dashboard/overview` and is not directly conflicting, but the shared prefix means any future additions risk silent overrides (`AINDY/routes/__init__.py`).
- **`main.py` uses deprecated `@app.on_event("startup")` twice.** FastAPI 0.119.0 deprecates `on_event` in favor of lifespan context managers. Two startup handlers are registered (`startup` and `ensure_system_identity`), both using the deprecated API. This generates deprecation warnings on every test run (`AINDY/main.py:50,83`).

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
  - Status: Open.

### §10.2 Data Model — MemoryTrace Python class creates a divergent shadow state

- **`MemoryTrace` (defined in `bridge/bridge.py`) maintains an in-memory representation of memory nodes that is not synchronized with the database.** It has no read-from-DB path, no cache invalidation, and no recovery logic on restart. Any write that goes through `MemoryTrace` and any write that goes through `MemoryNodeDAO` produce independent, inconsistent views of the same logical data.
  - Location: `AINDY/bridge/bridge.py` (MemoryTrace class)
  - Mechanism: `MemoryTrace.add_node()` appends to `self.nodes` in-memory. `MemoryNodeDAO.save_memory_node()` writes to PostgreSQL. There is no path between them.
  - Impact: Queries against the DB do not reflect in-memory state; in-memory state does not survive restart. Two consumers reading the same "memory" will see different results depending on which layer they use.
  - Status: ✅ **PARTIALLY RESOLVED (2026-03-18 Memory Bridge Phase 1):** `MemoryTrace` now has a docstring explicitly marking it as transient and not a source of truth. PostgreSQL (via `MemoryNodeDAO`) is the authoritative read path. `MemoryTrace` still exists for in-process scratchpad use; full elimination remains open for a future phase.

### §10.3 Graph Layer — memory_links has no traversal query

- **`memory_links` is populated (or intended to be) but no query traverses it.** No method in `MemoryNodeDAO` fetches linked neighbors, expands from a seed node, or scores paths. The table has correct schema, correct indexes, and a uniqueness constraint — but zero read-path usage. The graph is write-only from the application's perspective.
  - Location: `AINDY/services/memory_persistence.py` (MemoryNodeDAO), `AINDY/routes/bridge_router.py` (no traversal endpoint)
  - Mechanism: `POST /bridge/link` inserts rows. No endpoint or DAO method queries `memory_links` for neighbors, reachability, or subgraph expansion.
  - Impact: The relational structure between memory nodes is unqueryable. Graph-based recall — the architectural basis for associative memory — does not function.
  - Status: ✅ **RESOLVED (2026-03-18 Memory Bridge v3):** Multi-hop DFS traversal added in `db/dao/memory_node_dao.py::traverse()` with cycle prevention. Exposed at `GET /memory/nodes/{id}/traverse`. Single-hop `get_linked_nodes()` remains for neighbor lookup.

### §10.4 Graph Layer — memory_links.strength is a VARCHAR, not a numeric value

- **`memory_links.strength` is defined as `VARCHAR(20)` with default `"medium"`.** This means relationship weight is a non-comparable string enum (`"low"`, `"medium"`, `"high"`). It cannot be used in ORDER BY relevance, cannot be averaged, and cannot participate in any scoring formula. Any future graph traversal that needs weighted edges will require a schema migration to convert this to a numeric type.
  - Location: `AINDY/alembic/versions/bff24d352475_create_memory_nodes_links.py`, `AINDY/services/memory_persistence.py` (MemoryLinkModel)
  - Mechanism: Schema defines `strength VARCHAR(20) DEFAULT 'medium'`. No numeric weight column exists.
  - Impact: Graph traversal scoring is blocked. Relationship strength carries no computational meaning in the current schema.
  - Status: ✅ **RESOLVED (2026-03-21):** `weight FLOAT` added to `memory_links` via migration `e2c3d4f5a6b7`; traversal now prefers numeric `weight` with legacy `strength` fallback.
  - Status: Open. Fix: add `weight FLOAT NOT NULL DEFAULT 0.5` column to `memory_links`; deprecate `strength` string in a subsequent migration.

### §10.5 Retrieval — semantic retrieval is architecturally impossible in current state

- **No embeddings are stored in `memory_nodes`.** The C++ `cosine_similarity` kernel is implemented and callable, but `MemoryNodeModel` has no `embedding` column and no embedding generation occurs on node creation. `GET /bridge/nodes` retrieves by tag match or full-text only. There is no `/bridge/nodes/search/semantic` endpoint, no pgvector integration, and no embedding provider call in the write path. This is cross-referenced in §8 but recorded here for completeness as a retrieval architecture gap.
  - Location: `AINDY/services/memory_persistence.py` (MemoryNodeModel — no embedding field), `AINDY/bridge/memory_bridge_rs/src/lib.rs` (cosine_similarity callable but unused in retrieval)
  - Mechanism: Write path: content stored as TEXT only. Read path: tag OR/AND query or tsvector FTS. No vector path exists.
  - Impact: Semantic recall — retrieving memories by meaning rather than exact tags — does not function. The primary differentiation of this memory system over a text log is absent.
  - Status: ✅ **RESOLVED (2026-03-18 Memory Bridge Phase 2):** `embedding VECTOR(1536)` column added to `MemoryNodeModel` and DB (migration `mb2embed0001`). `services/embedding_service.py` generates embeddings via OpenAI `text-embedding-ada-002` on every `MemoryNodeDAO.save()` call. `find_similar()` retrieves via pgvector `<=>` cosine distance. Semantic search available at `POST /memory/nodes/search`. HNSW index added via migration `f3a4b5c6d7e8`.

### §10.6 Retrieval — no temporal decay or recency weighting

- **`created_at` is indexed on `memory_nodes` but is never incorporated into retrieval scoring.** All nodes matching a tag query or full-text query are returned with equal relevance regardless of age. A node created 2 years ago ranks identically to one created 30 seconds ago. There is no decay function, no recency weight, and no salience model.
  - Location: `AINDY/services/memory_persistence.py` (MemoryNodeDAO.find_by_tags — ORDER BY clause absent or arbitrary)
  - Mechanism: `find_by_tags()` returns matching nodes without a relevance score. No timestamp-based ranking is applied.
  - Impact: As node count grows, older or irrelevant memories contaminate recall. Retrieval quality degrades with scale.
- Status: ✅ **RESOLVED (2026-03-18 Memory Bridge v4):** `MemoryNodeDAO.recall()` implements resonance v2 scoring: `score = (semantic * 0.40) + (graph * 0.15) + (recency * 0.15) + (success_rate * 0.20) + (usage_frequency * 0.10)` where `recency = exp(-age_days / 30.0)`, then multiplied by adaptive `weight` and capped at 1.0. All recall results are ranked by resonance score. `POST /memory/recall` is the primary retrieval API.

### §10.7 Retrieval — tag query returns unranked flat lists with no relevance signal

- **Tag-based retrieval returns a flat list with no ordering by relevance, specificity, or recency.** OR mode returns all nodes matching any tag; AND mode returns all nodes matching all tags. No result carries a score. Callers cannot distinguish a node that matched 5 of 5 query tags from one that matched 1 of 5.
  - Location: `AINDY/services/memory_persistence.py` (MemoryNodeDAO.find_by_tags), `AINDY/routes/bridge_router.py` (GET /bridge/nodes response)
  - Mechanism: SQL query returns rows; no rank, score, or tag-overlap count is computed or returned.
  - Impact: High-cardinality tag queries return noisy results with no signal for the caller. Useful for exact lookups; breaks for fuzzy or exploratory recall.
  - Status: ✅ **RESOLVED (2026-03-18 Memory Bridge Phase 2):** `recall()` computes `tag_score = overlap / query_tag_count` and incorporates it into the resonance formula. Each returned node carries `tag_score`, `semantic_score`, `recency_score`, and `resonance_score` fields. `get_by_tags()` direct call still returns flat lists for backward compat; callers needing ranked results should use `recall()` or `POST /memory/recall`.

### §10.8 Persistence — no versioning or history table, state reconstruction is impossible

- **`memory_nodes` has an `updated_at` column but no history table, no append-only log, and no event sourcing.** When a node's content is updated, the prior value is permanently overwritten. The stated design objective of reconstructing past states across sessions cannot be fulfilled without a record of mutations.
  - Location: `AINDY/services/memory_persistence.py` (MemoryNodeModel — no history table), `AINDY/alembic/versions/` (no history migration)
  - Mechanism: UPDATE on `memory_nodes` replaces content in-place. No trigger, no shadow table, no log of prior values.
  - Impact: Temporal reconstruction — replaying what the system knew at time T — is not possible. Audit trail for node evolution does not exist.
  - Status: ✅ **RESOLVED (2026-03-18 Memory Bridge v3):** `memory_node_history` table added with append-only snapshots. `MemoryNodeDAO.update()` records previous values on explicit updates and `GET /memory/nodes/{id}/history` exposes history.

### §10.9 Infrastructure — Rust/C++ FFI chain is 3 layers deep for 2 math functions

- **The build and runtime path is C++ → Rust FFI → PyO3 → Python.** This is three foreign function boundaries for `cosine_similarity` and `weighted_dot_product`. Each layer adds: platform-specific compilation requirements (MSVC vs GCC divergence already present in `build.rs`), build chain dependencies (`cc`, `cxx`, `pyo3`, `maturin`), and a distinct failure mode. The performance fallback in `calculation_services.py` (pure Python) handles all current load without issue.
  - Location: `AINDY/bridge/memory_bridge_rs/build.rs`, `AINDY/bridge/memory_bridge_rs/src/cpp_bridge.rs`, `AINDY/bridge/memory_bridge_rs/src/lib.rs`, `AINDY/services/calculation_services.py`
  - Mechanism: C++ compiled to `.lib` via `cc` crate; Rust calls it via `extern "C"` unsafe block; PyO3 exposes Rust to Python; Python calls `from memory_bridge_rs import semantic_similarity`.
  - Impact: Build failures on new environments (already observed with Windows AppControl blocking release builds). High onboarding friction. Disproportionate complexity for two BLAS-level operations.
  - Status: Open. Recommendation: retain the kernel only when pgvector semantic search is operational and profiling confirms Python numpy is a bottleneck. Until then, the pure Python fallback is sufficient and the FFI chain is a net liability.

### §10.10 Security — HMAC permission tokens on memory writes are redundant with JWT

- **`POST /bridge/nodes` and `POST /bridge/link` require a `permission` block with HMAC-SHA256 signature, nonce, TTL, and scopes.** JWT auth (`Depends(get_current_user)`) now exists on adjacent route groups (Phase 2, §6). Two independent token systems operate in the same stack for the same purpose: proving an authorized caller. The HMAC scheme adds implementation surface (signing logic in callers, TTL management, nonce generation) without adding security properties that JWT does not already provide.
  - Location: `AINDY/routes/bridge_router.py:21-55` (HMAC verification), `AINDY/bridge/trace_permission.py` (permission token construction)
  - Mechanism: Callers must generate a `permission` object with `nonce`, `ts`, `ttl`, `scopes`, and a valid HMAC-SHA256 signature over those fields using `PERMISSION_SECRET`. This is checked before any DB write. JWT is not checked on these routes.
  - Impact: API clients must implement two authentication schemes. Any caller that uses the Memory Bridge write API must also manage HMAC token generation. Maintenance surface is doubled.
  - Status: Open. Recommendation: migrate Memory Bridge write routes to `Depends(get_current_user)` (JWT). Retire the HMAC permission scheme or reduce it to a scope-tagging mechanism only, not a full authentication layer. Deferred to Phase 3.

---

## 11. ARM Phase 2 Debt (Deferred from Phase 1 — 2026-03-17)

The following items were explicitly deferred from ARM Phase 1 (commit `f1cd3b5`).
ARM Phase 1 shipped the core engine (analysis, generation, security, DB, router, tests).

### §11.1 Memory Bridge feedback loop
- ✅ **RESOLVED (2026-03-18 Memory Bridge Phase 3):** `run_analysis()` writes an `"outcome"` node after `db.commit()` (tags: `["arm", "analysis", ext]`). `generate_code()` writes an `"outcome"` node after `db.commit()` (tags: `["arm", "codegen", language]`). `run_analysis()` also recalls prior memory context before prompt build via `recall_memories(query=filename, tags=["arm", "analysis"])`. Both hooks are fire-and-forget (exceptions silenced, main call unaffected).

### §11.2 Self-tuning config via Infinity Algorithm feedback
- ✅ **FIXED (2026-03-17 ARM Phase 2):** `ARMConfigSuggestionEngine` in
  `services/arm_metrics_service.py` analyzes the 5 Thinking KPI metrics and
  produces prioritized, risk-labelled config suggestions via `GET /arm/config/suggest`.
  Suggestions are advisory only — user applies via `PUT /arm/config`. Low-risk
  suggestions are surfaced in `auto_apply_safe` list for quick application.

### §11.3 Infinity metric crosswalk (Decision Efficiency, Execution Speed)
- ✅ **FIXED (2026-03-17 ARM Phase 2):** All 5 Infinity Algorithm Thinking KPI
  metrics exposed via `GET /arm/metrics`: Execution Speed, Decision Efficiency,
  AI Productivity Boost, Lost Potential, Learning Efficiency. Calculated by
  `ARMMetricsService` from `analysis_results` + `code_generations` history.

### §11.5 ARM Phase 3 — Memory Bridge feedback loop
- ✅ **RESOLVED (2026-03-18 Memory Bridge Phase 3).** See §11.1.

### §11.6 ARM Phase 3 — Auto-approve low-risk config changes
- **ARM Phase 2 returns `auto_apply_safe` list** of low-risk suggestions but
  requires user to call `PUT /arm/config` manually. Phase 3 should optionally
  auto-apply low-risk suggestions after each session without user confirmation.
  - Location: `AINDY/services/arm_metrics_service.py`, `AINDY/routes/arm_router.py`
  - Status: Open. Deferred to ARM Phase 3.

### §11.4 deepseek_arm_service.py is now a dead code path
- **`services/deepseek_arm_service.py` is no longer called by `arm_router.py`.**
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
  - Fix: run a one-time migration to map `"generic"` → `NULL` or `"insight"` before enabling strict enforcement on updates.
  - Status: Open. Low risk until UPDATE operations are performed on legacy nodes.

### §12.3 Embedding generation is synchronous and blocks the write path
- **`MemoryNodeDAO.save()` calls OpenAI synchronously** before the DB insert. A slow or failed OpenAI API call delays the HTTP response. Failure falls back to zero vector (safe), but latency is not bounded.
  - Fix: generate embeddings async via a task queue (Celery / ARQ) and backfill after insert; return node immediately without embedding then update when ready.
  - Status: Open. Deferred to Phase 3. Current behavior: 3-attempt retry then zero vector.

### §12.4 Phase 3 Workflow hooks — recall() integration
- ✅ **FULLY RESOLVED (2026-03-18 Sprint 7):** All 5 workflow memory hooks complete. `recall()` is now wired across the full system:
  - ARM analysis: retrieval hook before prompt build (top-3 prior results injected as "Prior analysis memory" section).
  - ARM codegen / Task completion / Genesis lock / Masterplan activate: write hooks persist structured outcome and decision nodes.
  - `bridge.recall_memories()` added as a programmatic bridge function for internal service use (no HTTP round-trip).
  - `bridge.create_memory_node()` upgraded to use `MemoryNodeDAO.save()` (with embedding) from `db.dao.memory_node_dao`.
  - ✅ **Sprint 7 (2026-03-18):** `genesis_ai.call_genesis_llm()` — recalls past strategic decisions/insights before Reflective Partner response (tags: `genesis`, `masterplan`, `decision`); writes `"insight"` node after each conversation turn. Router updated to pass `user_id` and `db`.
  - ✅ **Sprint 7 (2026-03-18):** `leadgen_service.run_ai_search()` — recalls past leadgen searches before querying (tags: `leadgen`, `search`, `outcome`); writes `"outcome"` node after results. `create_lead_results()` and router updated to pass `user_id`.
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
| **MB §10.3 — graph traversal absent** | ✅ Resolved | Multi-hop traversal + traverse endpoint added (Memory Bridge v3) | Phase 1 ✅ |
| Security (auth missing) | ✅ Resolved | JWT auth on task/leadgen/genesis/analytics routers (2026-03-17) | Phase 2 ✅ |
| Concurrency | Medium | Duplicated background work and unbounded loops | Phase 2 |
| Security (CORS + rate limiting) | ✅ Resolved | CORS locked to explicit origins; SlowAPIMiddleware added (2026-03-17) | Phase 2 ✅ |
| Testing | Low | Test suite now added; coverage gaps remain | Phase 2 |
| C++ Kernel (embeddings/release build) | Medium | Semantic search inoperable; performance gains unrealized | Phase 2 |
| **MB §10.2 — MemoryTrace shadow state** | **Medium** | Dual state representation diverges silently; DB and in-memory views inconsistent | **Phase 2** |
| **MB §10.5 — no embeddings / semantic retrieval impossible** | **Medium** | Primary differentiation of memory system over a log does not function | **Phase 2** |
| **MB §10.4 — strength is VARCHAR** | **Medium** | Graph edge weights are non-numeric; scored traversal blocked until schema migration | **Phase 2** |
| **MB §10.6 — no temporal decay** | **Medium** | Retrieval quality degrades with node count; stale memories rank equal to recent | **Phase 2** |
| **MB §10.7 — unranked tag retrieval** | **Low** | No relevance signal in results; noisy output at scale | **Phase 2** |
| **MB §10.10 — redundant HMAC + JWT auth** | **Low** | Callers must implement two auth schemes; maintenance surface doubled | **Phase 3** |
| Observability | Medium | Limited visibility into failures | Phase 3 |
| Structural | Low | Known coupling and in-memory state | Phase 3 |
| **MB §10.8 — no versioning / history table** | ✅ Resolved | Append-only history table + update logging (Memory Bridge v3) | Phase 3 ✅ |

## 14. Memory Bridge Phase 4 — Open Items

- ✅ **Outcome feedback loop.** Implemented in Memory Bridge v4 (feedback counters + adaptive weight + feedback endpoints + auto-feedback hooks).
- ✅ **Resonance v2.** Implemented in Memory Bridge v4 (semantic + graph + recency + success_rate + usage_frequency).
- ✅ **Automatic memory capture.** Implemented in Memory Bridge v5 Phase 1 via centralized capture engine (no manual calls).
- ✅ **Nodus runtime integration.** Implemented in Memory Bridge v5 Phase 1 via `NodusMemoryBridge` + v5 endpoints.
- **Pattern detection.** Detect recurring memory motifs across time windows (e.g., repeated decision→outcome→insight sequences).
- ✅ **v5 integration:** identity layer implemented (preferences, behavior, evolution) with `/identity/*` endpoints and prompt injection.
- ✅ **Resolved (2026-03-19):** Nodus stdlib `memory.nd` updated with Memory Bridge helpers (`recall`, `remember`, `suggest`, `record_outcome`) and extended functions.
- ✅ **RESOLVED (2026-03-19):** v5 Phase 3 — multi-agent shared memory (agent registry, shared/private memory, federated recall).
- **OPEN (2026-03-19):** Identity ML inference — replace rules-only observation with probabilistic or model-driven inference.
- **OPEN (2026-03-19):** SYLVA agent implementation (reserved namespace, inactive system agent).
- **OPEN (2026-03-19):** Embedding-based deduplication in capture engine (Phase 2 note in `MemoryCaptureEngine._is_duplicate`).
- **OPEN (2026-03-19):** Agent trust levels and access policy tiers (future).
| **MB §10.9 — FFI chain depth** | **Low** | 3-layer foreign function boundary for 2 math functions; high build friction | **Phase 3** |

### Line References (Highest-Risk Items)
- Background daemon threads: `AINDY/main.py:70`
- Genesis session lock enforcement: `AINDY/services/masterplan_factory.py:15`
- Memory Bridge HMAC validation: `AINDY/routes/bridge_router.py:41`
- Canonical metrics unique constraint migration: `AINDY/alembic/versions/97ef6237e153_structure_integrity_check.py:24`
- Health check endpoint mismatch (`/tools/seo/*` pings): `AINDY/routes/health_router.py:61`
- Duplicate `POST /create_masterplan` definition: `AINDY/routes/main_router.py:236`
- Note: Line numbers are approximate and may shift as files change; re-verify during audits.


