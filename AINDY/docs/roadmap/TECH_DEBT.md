# Technical Debt Inventory

This document inventories current technical debt based strictly on the existing implementation. It does not propose redesigns or new systems.

## 1. Structural Debt
- Background tasks are implemented as daemon threads in `AINDY/main.py` with no scheduler or supervision.
- Long-running loop variants exist in `AINDY/services/task_services.py` but are not managed by a job system.
- Gateway (`AINDY/server.js`) stores users in an in-memory array with no persistence.
- Gateway lacks state durability across restarts (`AINDY/server.js`).
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
- ~~**`bridge/bridge.py::create_memory_node()` writes to the wrong table.**~~ ✅ **FIXED (2026-03-18 Memory Bridge Phase 1):** Fully rewritten to write `MemoryNodeModel` rows via `MemoryNodeDAO` (table: `memory_nodes`). New signature: `(content, source, tags, user_id, db, node_type)`. All three callers updated. Regression tests added and bug-documenting tests flipped.
- Orphan `save_memory_node(self, memory_node)` defined at module level in `AINDY/services/memory_persistence.py:16`; takes `self` as first parameter but is not a method of any class. Would raise `TypeError` if called. The `MemoryNodeDAO.save_memory_node()` method below it handles persistence correctly; this function is dead code and should be removed.
- `AINDY/version.json` and `AINDY/system_manifest.json` report version `0.9.0-pre`; current release is `1.0.0` (Social Layer). These are not updated automatically and are stale.

## 3. Testing Debt
- Minimal unit coverage in `AINDY/services/`.
- Integration tests are limited to calculation endpoints (`test_calculations.py`, `test_routes.py`).
- No automated migration validation tests (`AINDY/alembic/` has no test harness).
- No coverage metrics tooling is configured (no coverage config files in repo root).
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

## 7. Observability Debt
- Logging granularity is limited; several routes rely on `print(...)` statements (`AINDY/routes/*`, `AINDY/services/*`).
- No centralized logging or tracing infrastructure (no config or tooling present).
- No metrics instrumentation beyond DB logging in `AINDY/routes/health_router.py`.

## 8. C++ Semantic Kernel Debt

The C++ semantic similarity kernel (`bridge/memory_bridge_rs/`) was added in `feature/cpp-semantic-engine`. The following items must be resolved before the kernel is production-ready.

- **Release build blocked by Windows AppControl.** The kernel was built in debug mode because AppControl policy blocks writes to `target/release/`. Debug benchmark (dim=1536, 10k iters): Python 2.753s vs C++ 3.844s — FFI overhead dominates in debug. Release build is expected to show 10–50x improvement. Action: run `maturin develop --release` in an environment without AppControl restrictions (deployment server or CI) and record results (`AINDY/bridge/benchmark_similarity.py`, `AINDY/bridge/memory_bridge_rs/Cargo.toml`).
- **No vector embeddings on `MemoryNode`.** The C++ `cosine_similarity` kernel is implemented and wired but has no data to operate on. `MemoryNode` stores text only; no embedding field, no embedding generation, no pgvector storage. Semantic memory search is inoperable until embeddings are added. Steps required: add `embedding` field to `MemoryNodeModel`, generate embeddings via OpenAI `text-embedding-ada-002` (dim=1536) on node creation, store in JSONB or pgvector, wire `cosine_similarity` to a `/bridge/nodes/search/semantic` endpoint (`AINDY/bridge/memory_bridge_rs/src/lib.rs`, `AINDY/services/memory_persistence.py`).
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

The following items were identified during a structured architectural review of the Memory Bridge system (2026-03-17). They describe structural and design-level deficiencies distinct from the runtime bugs already recorded in §2, §8, and §9. Cross-references to those sections are noted where relevant.

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
  - Status: ✅ **RESOLVED (2026-03-18 Memory Bridge Phase 1):** `MemoryNodeDAO.get_linked_nodes(node_id, direction)` added in `db/dao/memory_node_dao.py`; supports `in`, `out`, and `both` directions. Exposed at `GET /memory/nodes/{id}/links`.

### §10.4 Graph Layer — memory_links.strength is a VARCHAR, not a numeric value

- **`memory_links.strength` is defined as `VARCHAR(20)` with default `"medium"`.** This means relationship weight is a non-comparable string enum (`"low"`, `"medium"`, `"high"`). It cannot be used in ORDER BY relevance, cannot be averaged, and cannot participate in any scoring formula. Any future graph traversal that needs weighted edges will require a schema migration to convert this to a numeric type.
  - Location: `AINDY/alembic/versions/bff24d352475_create_memory_nodes_links.py`, `AINDY/services/memory_persistence.py` (MemoryLinkModel)
  - Mechanism: Schema defines `strength VARCHAR(20) DEFAULT 'medium'`. No numeric weight column exists.
  - Impact: Graph traversal scoring is blocked. Relationship strength carries no computational meaning in the current schema.
  - Status: Open. Fix: add `weight FLOAT NOT NULL DEFAULT 0.5` column to `memory_links`; deprecate `strength` string in a subsequent migration.

### §10.5 Retrieval — semantic retrieval is architecturally impossible in current state

- **No embeddings are stored in `memory_nodes`.** The C++ `cosine_similarity` kernel is implemented and callable, but `MemoryNodeModel` has no `embedding` column and no embedding generation occurs on node creation. `GET /bridge/nodes` retrieves by tag match or full-text only. There is no `/bridge/nodes/search/semantic` endpoint, no pgvector integration, and no embedding provider call in the write path. This is cross-referenced in §8 but recorded here for completeness as a retrieval architecture gap.
  - Location: `AINDY/services/memory_persistence.py` (MemoryNodeModel — no embedding field), `AINDY/bridge/memory_bridge_rs/src/lib.rs` (cosine_similarity callable but unused in retrieval)
  - Mechanism: Write path: content stored as TEXT only. Read path: tag OR/AND query or tsvector FTS. No vector path exists.
  - Impact: Semantic recall — retrieving memories by meaning rather than exact tags — does not function. The primary differentiation of this memory system over a text log is absent.
  - Status: Open (tracked in §8; requires pgvector extension, `embedding VECTOR(1536)` column, embedding generation on write, HNSW index, and a semantic search endpoint).

### §10.6 Retrieval — no temporal decay or recency weighting

- **`created_at` is indexed on `memory_nodes` but is never incorporated into retrieval scoring.** All nodes matching a tag query or full-text query are returned with equal relevance regardless of age. A node created 2 years ago ranks identically to one created 30 seconds ago. There is no decay function, no recency weight, and no salience model.
  - Location: `AINDY/services/memory_persistence.py` (MemoryNodeDAO.find_by_tags — ORDER BY clause absent or arbitrary)
  - Mechanism: `find_by_tags()` returns matching nodes without a relevance score. No timestamp-based ranking is applied.
  - Impact: As node count grows, older or irrelevant memories contaminate recall. Retrieval quality degrades with scale.
  - Status: Open. Minimum viable fix: add `ORDER BY created_at DESC` to `find_by_tags()`; defer decay weighting to v1.

### §10.7 Retrieval — tag query returns unranked flat lists with no relevance signal

- **Tag-based retrieval returns a flat list with no ordering by relevance, specificity, or recency.** OR mode returns all nodes matching any tag; AND mode returns all nodes matching all tags. No result carries a score. Callers cannot distinguish a node that matched 5 of 5 query tags from one that matched 1 of 5.
  - Location: `AINDY/services/memory_persistence.py` (MemoryNodeDAO.find_by_tags), `AINDY/routes/bridge_router.py` (GET /bridge/nodes response)
  - Mechanism: SQL query returns rows; no rank, score, or tag-overlap count is computed or returned.
  - Impact: High-cardinality tag queries return noisy results with no signal for the caller. Useful for exact lookups; breaks for fuzzy or exploratory recall.
  - Status: Open. Fix: return a `match_score` field (count of matched tags / total query tags) alongside each node result.

### §10.8 Persistence — no versioning or history table, state reconstruction is impossible

- **`memory_nodes` has an `updated_at` column but no history table, no append-only log, and no event sourcing.** When a node's content is updated, the prior value is permanently overwritten. The stated design objective of reconstructing past states across sessions cannot be fulfilled without a record of mutations.
  - Location: `AINDY/services/memory_persistence.py` (MemoryNodeModel — no history table), `AINDY/alembic/versions/` (no history migration)
  - Mechanism: UPDATE on `memory_nodes` replaces content in-place. No trigger, no shadow table, no log of prior values.
  - Impact: Temporal reconstruction — replaying what the system knew at time T — is not possible. Audit trail for node evolution does not exist.
  - Status: Open. Deferred to Phase 3. Fix: add `memory_node_history` table with `node_id`, `content`, `tags`, `changed_at`, populated by a BEFORE UPDATE trigger.

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
- **After each ARM analysis/generation, a `MemoryNode` should be persisted via
  `MemoryNodeDAO`** with ARM results as structured content and semantic tags.
  Currently: DB records written to `analysis_results` / `code_generations` only.
  Memory Bridge (`memory_nodes` table) is not updated.
  - Location: `AINDY/modules/deepseek/deepseek_code_analyzer.py` (run_analysis, generate_code)
  - Fix: after `db.commit()` in each method, call `MemoryNodeDAO(db).save_memory_node()`
    with `node_type="arm_analysis"` or `"arm_generation"`, content=summary/explanation,
    tags=["deepseek", file_type, analysis_type].
  - Status: Open. Deferred to ARM Phase 2.

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

### §11.5 ARM Phase 3 — Memory Bridge feedback loop (deferred pending bridge design)
- **After each ARM analysis/generation, a `MemoryNode` should be persisted via
  `MemoryNodeDAO`** with ARM results as structured content and semantic tags.
  Phase 2 writes to `analysis_results` / `code_generations` only.
  - Location: `AINDY/modules/deepseek/deepseek_code_analyzer.py`
  - Status: Open. Deferred to ARM Phase 3 pending Memory Bridge design.

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

## 12. Prioritization Table

| Area | Risk Level (Low/Medium/High) | Impact | Recommended Phase |
|------|------------------------------|--------|-------------------|
| Schema / Migration | High | Runtime failures — `create_memory_node()` ImportError on every call | Phase 1 |
| Genesis Router (undefined names) | High | 3 of 5 genesis endpoints raise NameError at runtime | Phase 1 |
| Error Handling | High | Inconsistent client behavior and poor fault isolation | Phase 1 |
| C++ Kernel (wrong-table + import bug) | High | Memory nodes created via services are silently lost + ImportError | Phase 1 |
| **MB §10.1 — children not persisted** | **High** | Every recursive memory trace is silently lost on process exit | **Phase 1** |
| **MB §10.3 — graph traversal absent** | **High** | memory_links table is write-only; associative recall does not function | **Phase 1** |
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
| **MB §10.8 — no versioning / history table** | **Low** | State reconstruction impossible; node mutation history lost permanently | **Phase 3** |
| **MB §10.9 — FFI chain depth** | **Low** | 3-layer foreign function boundary for 2 math functions; high build friction | **Phase 3** |

### Line References (Highest-Risk Items)
- Background daemon threads: `AINDY/main.py:70`
- Genesis session lock enforcement: `AINDY/services/masterplan_factory.py:15`
- Memory Bridge HMAC validation: `AINDY/routes/bridge_router.py:41`
- Canonical metrics unique constraint migration: `AINDY/alembic/versions/97ef6237e153_structure_integrity_check.py:24`
- Health check endpoint mismatch (`/tools/seo/*` pings): `AINDY/routes/health_router.py:61`
- Duplicate `POST /create_masterplan` definition: `AINDY/routes/main_router.py:236`
- Note: Line numbers are approximate and may shift as files change; re-verify during audits.
