# Changelog

All notable changes to this project will be documented in this file.

The format is based on the "Keep a Changelog" style and follows semantic-style versioning where possible.

---

# [Unreleased]

Changes that have been implemented but are not yet part of a tagged release.

## Added

* Initial system documentation structure
* Architecture specifications
* Interface contracts
* Governance policies

## Changed

* Ongoing improvements to runtime behavior and system architecture

---

# [feature/cpp-semantic-engine — Genesis Blocks 4-6] — 2026-03-17

## Added

* **Block 4 — Strategic Integrity Audit**
  * `AUDIT_SYSTEM_PROMPT` in `services/genesis_ai.py` — GPT-4o audit schema with finding
    types (`mechanism_gap | contradiction | timeline_risk | asset_gap | confidence_concern`),
    severity levels (`critical | warning | advisory`), and structured output fields.
  * `validate_draft_integrity(draft: dict) -> dict` — GPT-4o integrity audit with 3-attempt
    retry logic, `response_format=json_object`, and fail-safe fallback on exception.
  * `POST /genesis/audit` — JWT-protected endpoint; loads `session.draft_json`, calls
    `validate_draft_integrity()`, returns audit result. 422 if no draft yet.
  * `auditGenesisDraft(sessionId)` added to `client/src/api.js`.
  * `GenesisDraftPreview.jsx` — full audit panel: AUDIT DRAFT button, severity-colored
    finding cards, `audit_passed` / `overall_confidence` / `audit_summary` display.

## Changed

* **Block 5 — Lock Pipeline Hardening**
  * `create_masterplan_from_genesis()` — `synthesis_ready` gate raises `ValueError` if
    session not ready; loads draft from `session.draft_json` (falls back to caller draft);
    wraps all DB ops in `try/except` with `db.rollback()` on failure.
  * `POST /masterplans/lock` — new static endpoint in `masterplan_router.py`; drives
    genesis→lock pipeline; maps `ValueError` → 422; includes `posture_description` in response.
  * `GET /masterplans/` — response shape changed from plain list to `{"plans": [...]}`.
  * `MasterPlanDashboard.jsx` — updated to consume `data.plans || []`.
  * `SYNTHESIS_SYSTEM_PROMPT` — `synthesis_notes` field and corresponding rule added.

## Fixed

* **Block 6 — Duplicate Route Removal**
  * Removed duplicate `POST /create_masterplan` from `routes/main_router.py` (the variant
    using `MasterPlanCreate` schema). Retained the `MasterPlanInput` variant with legacy comment.

## Tests

* Added `tests/test_genesis_flow.py` — 55 tests covering all Block 4-6 behaviors.
* **Total test count: 301 (was 246).**

---

# [feature/cpp-semantic-engine — ARM Phase 1] — 2026-03-17

## Added

* **ARM Phase 1 — Autonomous Reasoning Module (GPT-4o engine)**
  * `SecurityValidator` — full HTTPException-based input validation: path traversal
    blocking, extension allowlist, regex sensitive content detection (API keys,
    private keys, AWS keys, .env refs), configurable size limit.
  * `ConfigManager` — 16-key DEFAULT_CONFIG, runtime update with key allowlist,
    `deepseek_config.json` persistence, Infinity Algorithm Task Priority formula
    `TP = (C × U) / R` with zero-division guard.
  * `FileProcessor` — line-boundary chunking, UUID session IDs, session log dicts
    with Execution Speed metric (tokens/second).
  * `DeepSeekCodeAnalyzer` — GPT-4o powered analysis (`run_analysis`) and code
    generation (`generate_code`) with retry logic, `json_object` response format,
    full success/failure DB logging.
  * `AnalysisResult` + `CodeGeneration` SQLAlchemy models (UUID PKs, PostgreSQL).
  * ARM router fully rewritten — singleton analyzer, config-reset on PUT,
    structured response shapes with Infinity metrics.
  * 46 ARM tests (208 total, 0 failing).
  * Frontend ARM components updated: structured analysis display, prompt-based
    generation, aligned log/config shapes.

---

# [feature/cpp-semantic-engine — Phase 3 security] — 2026-03-17

## Added

* `db/models/user.py` — `User` SQLAlchemy model (`users` table): UUID PK, `email` (unique index), `username` (unique index, nullable), `hashed_password`, `is_active`, `created_at`
* `alembic/versions/37f972780d54_create_users_table.py` — migration creating `users` table; applied via `alembic upgrade head`
* `services/register_user()` and `services/authenticate_user()` — DB-backed user operations added to `auth_service.py`; replace in-memory `_USERS` dict
* `services/rate_limiter.py` — shared `Limiter` instance extracted from `main.py` to allow route modules to import it without circular imports
* Rate limiting decorators applied to all AI/expensive endpoints:
  - `POST /leadgen/` — 10 requests/minute (Perplexity cost)
  - `POST /genesis/message` — 20 requests/minute (OpenAI cost)
  - `POST /genesis/synthesize` — 5 requests/minute (OpenAI cost)
  - `POST /arm/analyze` — 10 requests/minute (DeepSeek cost)
  - `POST /arm/generate` — 10 requests/minute (DeepSeek cost)
* 12 new security tests in `test_security.py` (`TestPhase3RouteProtection` class) — one rejection test and one acceptance test per newly protected router

## Fixed

* **In-memory user store** — `auth_router.py` now uses `Depends(get_db)` + `register_user()` / `authenticate_user()` from `auth_service.py`. Users persist to PostgreSQL across restarts and across worker processes. `_USERS` dict removed.
* **All remaining unprotected routers secured:**
  - JWT (`Depends(get_current_user)`): `seo_routes`, `authorship_router`, `arm_router`, `rippletrace_router`, `freelance_router`, `research_results_router`, `dashboard_router`, `social_router`
  - API key (`Depends(verify_api_key)`): `db_verify_router` (exposes DB schema), `network_bridge_router` (service-to-service target)
  - Zero unprotected non-public routes remain.
* **Node.js gateway** — `server.js` now loads `AINDY_API_KEY` from `.env` via `dotenv` and sends `X-API-Key` header on all FastAPI service calls (`/network_bridge/connect`). Previously forwarded requests without credentials, which would 401 after Phase 3 route protection.

## Test Results

* **162 passing, 0 failing** (up from 150 passing, 0 failing after Phase 2)
* `test_security.py`: 13 → 25 tests (12 Phase 3 additions)

## Known Gaps (Phase 4+)

* `SECRET_KEY` default is insecure placeholder — must be set to a cryptographically random value in production `.env`
* Memory Bridge write routes (`/bridge/nodes`, `/bridge/link`) use HMAC permission tokens alongside JWT — dual-auth scheme adds caller complexity (tracked in `TECH_DEBT.md` §10.10)
* `db/models/user.py` has no role or permission fields — authorization is binary (authenticated vs. not); no scoped permissions

---

# [feature/cpp-semantic-engine — Phase 2 security] — 2026-03-17

## Added

* `services/auth_service.py` — JWT token creation/verification, API key validation, password hashing (`python-jose`, `passlib/bcrypt==4.0.1`)
* `schemas/auth_schemas.py` — `LoginRequest`, `RegisterRequest`, `TokenResponse` Pydantic models
* `routes/auth_router.py` — `POST /auth/login`, `POST /auth/register` (public endpoints, in-memory user store MVP)
* `slowapi==0.1.9` — rate limiting package; `SlowAPIMiddleware` registered on FastAPI app
* `config.py` — `SECRET_KEY` and `AINDY_API_KEY` settings fields
* `tests/conftest.py` — `auth_headers` and `api_key_headers` fixtures; `SECRET_KEY`, `AINDY_API_KEY`, `ALLOWED_ORIGINS` env defaults

## Fixed

* **CORS wildcard** — `allow_origins=["*"]` replaced with `ALLOWED_ORIGINS` env var (default: localhost origins). `allow_credentials=True` + wildcard is a CORS spec violation; now uses explicit origin list (`AINDY/main.py`).
* **No authentication on API routes** — `Depends(get_current_user)` (JWT Bearer) added to all routes in `task_router`, `leadgen_router`, `genesis_router`, `analytics_router`. Unauthenticated requests now return 401. Health, bridge, and auth routes remain public.
* **No rate limiting** — `SlowAPIMiddleware` added via `app.add_middleware()`; limiter attached to `app.state.limiter`. Rate limits can be applied per-route with `@limiter.limit()`.

## Test Results

* **7 intentional `_WILL_FAIL` security tests → 0 failures** (all 7 now pass)
* Total: **150 passing, 0 failing** (up from 136 passing, 7 failing)
* `test_security.py` tests renamed (removed `_WILL_FAIL` suffix); positive assertion paths added
* Affected diagnostic test files updated: `test_routes_tasks.py`, `test_routes_genesis.py`, `test_routes_leadgen.py`, `test_routes_analytics.py`

## Known Gaps (Phase 3)

* No User ORM model — auth router uses in-memory store; replace with `db.models.user.UserDB`
* Node gateway (`server.js`) still lacks auth headers when forwarding to FastAPI
* `SECRET_KEY` default is insecure placeholder — must be set in production `.env`

---

# [feature/cpp-semantic-engine — crash fixes] — 2026-03-17

## Fixed

* **`bridge/bridge.py` ImportError** — `from db.models.models import CalculationResult` corrected to `from db.models.calculation import CalculationResult`. `db/models/models.py` does not exist; every call to `create_memory_node()` (social posts, leadgen) was crashing with `ImportError` before reaching any DB logic. Wrong-table architectural issue (`calculation_results` vs `memory_nodes`) remains tracked in `docs/roadmap/TECH_DEBT.md` §2.
* **`routes/genesis_router.py` NameError crashes** — Three missing imports added: `call_genesis_synthesis_llm` (from `services.genesis_ai`), `create_masterplan_from_genesis` (from `services.masterplan_factory`), `MasterPlan` (from `db.models`). A cascading `ModuleNotFoundError` was also resolved by creating `services/posture.py` stub (`determine_posture()`). `POST /genesis/synthesize` and `POST /genesis/lock` no longer crash with `NameError` before reaching business logic.
* **`calculate_twr()` ZeroDivisionError → HTTP 500** — Three-layer fix: (1) Pydantic `@validator("task_difficulty")` on `TaskInput` rejects `<= 0` at schema level with automatic 422; (2) `ValueError` guard added inside `calculate_twr()` as second line of defense; (3) `try/except ValueError/ZeroDivisionError` in `routes/main_router.py` maps both to HTTP 422 with a clear message. Route previously returned HTTP 500 on zero-difficulty input.

## Added

* `services/posture.py` — minimal stub for `determine_posture()`, required by `masterplan_factory.py` import chain.

## Documentation

* `docs/roadmap/TECH_DEBT.md` — §9 status updated for all three crash bugs; import path fix noted as resolved; genesis NameError crashes noted as resolved; TWR ValueError guard noted as resolved.

---

# [feature/cpp-semantic-engine — test suite] — 2026-03-17

## Added

* Comprehensive diagnostic test suite (`AINDY/tests/`) — 143 tests across 8 files:
  * `tests/conftest.py` — shared fixtures (TestClient, mock_db, mock_openai)
  * `tests/test_calculation_services.py` — 26 tests: all Infinity Algorithm formulas, C++ kernel flag, Python/C++ parity
  * `tests/test_memory_bridge.py` — 40 tests: Python bridge layer, MemoryNodeDAO, Rust/C++ kernel (cosine similarity, weighted dot product, dim=1536)
  * `tests/test_models.py` — 15 tests: SQLAlchemy model structure, orphan function documentation
  * `tests/test_routes_health.py` — 6 tests: health endpoint structure and response time
  * `tests/test_routes_tasks.py` — 11 tests: task route registration, schema validation
  * `tests/test_routes_bridge.py` — 8 tests: HMAC validation, TTL enforcement, read path
  * `tests/test_routes_analytics.py` — 10 tests: analytics route registration, zero-view guard, zero-difficulty 500
  * `tests/test_routes_leadgen.py` — 8 tests: route registration, dead code documentation
  * `tests/test_routes_genesis.py` — 9 tests: route registration, NameError bug documentation
  * `tests/test_security.py` — 10 tests: auth gaps (intentional failures), CORS, rate limiting
* Test infrastructure: `pytest==9.0.2`, `pytest-mock==3.15.1`, `pytest-asyncio==1.3.0` added to `requirements.txt`
* `pytest.ini` — test discovery configuration

## Notes

* Final result after test suite + crash fixes: **136 passing, 7 failing**
* All 7 remaining failures are intentional `_WILL_FAIL` security gap tests (no auth, wildcard CORS, no rate limiting) — tracked in `docs/roadmap/TECH_DEBT.md` §6 for Phase 2.

---

# [feature/cpp-semantic-engine] — 2026-03-17

## Added

* C++ semantic similarity engine (`bridge/memory_bridge_rs/memory_cpp/semantic.h` + `semantic.cpp`) providing high-performance vector math
* `cosine_similarity(a, b, len)` — C++ kernel for semantic memory node search (active; embeddings pending)
* `weighted_dot_product(values, weights, len)` — C++ kernel powering `calculate_engagement_score()` in the Infinity Algorithm
* Rust `extern "C"` FFI bridge (`src/cpp_bridge.rs`) safely wrapping C++ operations without proc-macro dependencies
* `semantic_similarity()` and `weighted_dot_product()` exposed to Python via PyO3 (`src/lib.rs`)
* Python fallback implementations in `calculation_services.py` (app works without compiled extension)
* `bridge/benchmark_similarity.py` for performance verification

## Changed

* `calculate_engagement_score()` in `calculation_services.py` now routes through C++ `weighted_dot_product` kernel (with Python fallback)
* `Cargo.toml` updated: `cc` build-dependency added; `cxx` removed
* `build.rs` added for C++ compilation configuration (MSVC VS 2022 x64)
* `AINDY_README.md` architecture tree updated to reflect current `bridge/` structure; Memory Bridge and Infinity Algorithm sections added

## Documentation

* `docs/roadmap/TECH_DEBT.md` — added §8 C++ Semantic Kernel Debt; added specific items to §1 (Structural), §2 (Schema/Migration), §3 (Testing)
* `docs/architecture/SYSTEM_SPEC.md` — added stack diagram to §2; added three detailed data flow paths to §3; updated Known Gaps
* `docs/governance/CHANGELOG.md` — this entry

## Technical Notes

* Build toolchain: MSVC VS 2022 Community (x64) via registry
* Build mode: debug (release blocked by Windows AppControl policy on `target/` directories)
* Benchmark (debug, dim=1536, 10k iters): Python 2.753s vs C++ 3.844s — debug FFI overhead dominates; release expected 10–50x faster
* `cxx` crate dropped in favor of direct `extern "C"` FFI because cxx proc-macro DLLs were also blocked by AppControl
* Branch: `feature/cpp-semantic-engine`

---

# [0.1.0] – Initial Repository Baseline

## Added

* Core project repository structure
* Documentation architecture

```
docs/
  architecture/
  engineering/
  governance/
  interfaces/
  roadmap/
```

* System specification documents
* Runtime behavior documentation
* Data model mapping
* Algorithm and formula documentation
* Interface contracts
* Deployment and testing documentation
* System invariants and governance rules

## Documentation

Architecture specifications added:

* SYSTEM_SPEC.md
* DATA_MODEL_MAP.md
* RUNTIME_BEHAVIOR.md
* FORMULA_AND_ALGORITHM_OVERVIEW.md
* INFINITY_ALGORITHM_CANONICAL.md
* INFINITY_ALGORITHM_FORMALIZATION.md
* ABSTRACTED_ALGORITHM_SPEC.md

Engineering documentation:

* DEPLOYMENT_MODEL.md
* TESTING_STRATEGY.md
* MIGRATION_POLICY.md

Governance documentation:

* INVARIANTS.md
* ERROR_HANDLING_POLICY.md
* AGENT_WORKING_RULES.md

Interface specifications:

* API_CONTRACTS.md
* GATEWAY_CONTRACT.md
* MEMORY_BRIDGE_CONTRACT.md

Roadmap and planning documents:

* EVOLUTION_PLAN.md
* TECH_DEBT.md
* release_notes.md

---

# Versioning

Version numbers generally follow the pattern:

```
MAJOR.MINOR.PATCH
```

Example:

```
1.0.0
```

Where:

MAJOR – Breaking architecture changes
MINOR – New features or capabilities
PATCH – Bug fixes or small improvements

---

# Release Process

Typical release workflow:

1. Update the `CHANGELOG.md`
2. Commit release changes
3. Tag the version

Example:

```
git tag v0.1.0
git push origin v0.1.0
```

4. Publish release notes

---

# Notes

This project maintains documentation-driven architecture.

Changes that affect:

* system behavior
* API contracts
* runtime rules
* governance invariants

should also update the corresponding documentation in:

```
docs/
```
