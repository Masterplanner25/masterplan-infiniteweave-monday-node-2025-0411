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
- **`bridge/bridge.py::create_memory_node()` writes to the wrong table.** It persists via `CalculationResult` to `calculation_results`, storing only `title` as `metric_name` and `0.0` as `result_value`. Content and tags are silently discarded. The correct path uses `MemoryNodeDAO` writing to `memory_nodes`. Split state results: memory nodes created via `leadgen_service.py` produce phantom `CalculationResult` rows. Fix: rewrite `create_memory_node()` to use `MemoryNodeDAO` (`AINDY/bridge/bridge.py:60`).
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
- Missing retry logic for external model providers (`AINDY/services/genesis_ai.py`, `AINDY/services/deepseek_arm_service.py`).
- Logging is mixed between `print(...)` and logging module; no structured logging (`AINDY/config.py`, multiple routes/services).

## 5. Concurrency Debt
- Background loops can block or run indefinitely without supervision (`AINDY/services/task_services.py`).
- No distributed-safe scheduler; multi-instance deployment risks duplicated background work (`AINDY/main.py` daemon threads).
- No explicit controls for thread lifecycle or shutdown coordination (`AINDY/main.py`).

## 6. Security Debt
- No rate limiting on API routes (`AINDY/routes/*`).
- No authentication or authorization on gateway or backend routes (`AINDY/server.js`, `AINDY/routes/*`).
- No documented secret rotation policy (`AINDY/routes/bridge_router.py` uses env secret without rotation).
- HMAC protection exists for Memory Bridge writes but no replay protection beyond TTL (`AINDY/routes/bridge_router.py`).

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
- **`bridge/bridge.py::create_memory_node()` also has a broken import path.** ~~In addition to writing to the wrong table, `create_memory_node()` imports via `from db.models.models import CalculationResult` — but `db/models/models.py` does not exist. This causes an `ImportError` at runtime whenever the function is called.~~ **IMPORT PATH FIXED (2026-03-17):** Import corrected from `db.models.models` to `db.models.calculation`. The `ImportError` crash is resolved. The wrong-table architectural issue remains open: `create_memory_node()` still writes to `CalculationResult` (table: `calculation_results`) instead of `MemoryNodeDAO` (table: `memory_nodes`). Content and tags are still discarded. Full fix requires rewriting to use `MemoryNodeDAO` (`AINDY/bridge/bridge.py:66`). Revealed by: `test_memory_bridge.py::TestCreateMemoryNodeWrongTable::test_create_memory_node_uses_wrong_table`.

### §1 Structural (additions)
- **`routes/genesis_router.py` has three undefined name references.** ~~(1) `POST /genesis/synthesize` calls `call_genesis_synthesis_llm()` — NameError. (2) `POST /genesis/lock` calls `create_masterplan_from_genesis()` — NameError. (3) `POST /genesis/{plan_id}/activate` references `MasterPlan` — NameError.~~ **CRASHES FIXED (2026-03-17):** All three missing imports added. `call_genesis_synthesis_llm` imported from `services.genesis_ai`; `create_masterplan_from_genesis` imported from `services.masterplan_factory`; `MasterPlan` imported from `db.models`. A stub `services/posture.py::determine_posture()` was also created to resolve a `ModuleNotFoundError` in `masterplan_factory.py` (full posture logic pending). Routes no longer raise NameError before reaching any business logic. LLM synthesis implementation for `call_genesis_synthesis_llm` remains a stub — tracked in TECH_DEBT.md. Revealed by: `test_routes_genesis.py::TestGenesisSynthesizeEndpoint::test_post_genesis_synthesize_has_name_error_bug`, `test_routes_genesis.py::TestGenesisLockEndpoint::test_post_genesis_lock_has_undefined_name_bug`.
- **`services/leadgen_service.py::score_lead()` contains dead/unreachable code.** The function has two `try:` blocks, but the second is entirely unreachable because the first block always returns (or raises). The dead block calls `client.chat.completions.create(model="gpt-4o", ...)` — a different model than the live block — which is neither tested nor executed. Fix: remove the dead block (`AINDY/services/leadgen_service.py:104-127`). Revealed by: `test_routes_leadgen.py::TestLeadGenServiceBugs::test_score_lead_has_dead_code_after_return`.
- **`routes/seo_routes.py` defines `analyze_seo()` twice.** The function is defined at line 17 and again at line 39. Python silently uses the second definition, making the first (basic) implementation unreachable. The duplicate also appears in the router — both map to `POST /analyze_seo/`. The second definition (`POST /seo/analyze`) works but shares a name with the dead first one (`AINDY/routes/seo_routes.py:17,39`).
- **`routes/dashboard_router.py` and `routes/health_dashboard_router.py` both use prefix `/dashboard`.** This creates a route collision on `/dashboard/health`. FastAPI registers both but the last-registered takes precedence. The `dashboard_router.py` (overview) path is `/dashboard/overview` and is not directly conflicting, but the shared prefix means any future additions risk silent overrides (`AINDY/routes/__init__.py`).
- **`main.py` uses deprecated `@app.on_event("startup")` twice.** FastAPI 0.119.0 deprecates `on_event` in favor of lifespan context managers. Two startup handlers are registered (`startup` and `ensure_system_identity`), both using the deprecated API. This generates deprecation warnings on every test run (`AINDY/main.py:50,83`).

### §6 Security (additions)
- **No authentication or authorization on any API route confirmed by test suite.** Tests confirm: `GET /tasks/list` returns 200, `POST /tasks/create` returns 200 (creates records), `POST /genesis/session` returns 200, `POST /leadgen/` reaches the handler and makes API calls — all without any credentials. This confirms the existing §6 entry with test evidence (`AINDY/routes/*`). Revealed by: `test_security.py::TestAuthenticationMissing::*`.
- **CORS wildcard with credentials confirmed.** `allow_origins=["*"]` with `allow_credentials=True` is confirmed active in `main.py`. Browsers reject this configuration per the CORS spec; it is a security misconfiguration. Revealed by: `test_security.py::TestCORSConfiguration::test_cors_is_not_wildcard_WILL_FAIL`.
- **No rate limiting middleware confirmed.** Only `BaseHTTPMiddleware` and `CORSMiddleware` are active. No `SlowAPI`, `fastapi-limiter`, or equivalent present. Revealed by: `test_security.py::TestRateLimit::test_rate_limiting_exists_WILL_FAIL`.

### §4 Error Handling (additions)
- **`services/calculation_services.py::calculate_twr()` ZeroDivisionError.** **FIXED (2026-03-17):** `task_difficulty=0` previously caused an unhandled `ZeroDivisionError` that propagated as HTTP 500. Fixed by: (1) adding a `ValueError` guard at the top of `calculate_twr()` when `task_difficulty == 0`; (2) adding a Pydantic `@validator` on `TaskInput.task_difficulty` that rejects values `<= 0` with a 422 response before the function is reached; (3) wrapping the `calculate_twr()` call in `routes/main_router.py` with `try/except ValueError` and `except ZeroDivisionError` both raising `HTTPException(422)`. Route now returns 422 with a clear error message instead of 500. Revealed by: `test_calculation_services.py::TestTWR::test_twr_zero_difficulty_raises`, `test_routes_analytics.py::TestCalculateTWREndpoint::test_twr_zero_difficulty_causes_500`.

### §3 Testing (additions — resolved)
- Comprehensive diagnostic test suite added: `AINDY/tests/` with 143 tests across 8 files covering services, memory bridge, Rust/C++ kernel, all route groups, models, and security. Test infrastructure: `pytest==9.0.2`, `pytest-mock==3.15.1`, `pytest-asyncio==1.3.0` added to `requirements.txt`. Final result: **135 passing, 8 failing** (all failures are intentional diagnostic tests for known bugs).

## 10. Prioritization Table

| Area | Risk Level (Low/Medium/High) | Impact | Recommended Phase |
|------|------------------------------|--------|-------------------|
| Schema / Migration | High | Runtime failures — `create_memory_node()` ImportError on every call | Phase 1 |
| Genesis Router (undefined names) | High | 3 of 5 genesis endpoints raise NameError at runtime | Phase 1 |
| Error Handling | High | Inconsistent client behavior and poor fault isolation | Phase 1 |
| C++ Kernel (wrong-table + import bug) | High | Memory nodes created via services are silently lost + ImportError | Phase 1 |
| Security (auth missing) | High | All routes publicly writable — confirmed by test suite | Phase 1 |
| Concurrency | Medium | Duplicated background work and unbounded loops | Phase 2 |
| Security (CORS + rate limiting) | Medium | CORS misconfiguration; no rate limiting | Phase 2 |
| Testing | Low | Test suite now added; coverage gaps remain | Phase 2 |
| C++ Kernel (embeddings/release build) | Medium | Semantic search inoperable; performance gains unrealized | Phase 2 |
| Observability | Medium | Limited visibility into failures | Phase 3 |
| Structural | Low | Known coupling and in-memory state | Phase 3 |

### Line References (Highest-Risk Items)
- Background daemon threads: `AINDY/main.py:70`
- Genesis session lock enforcement: `AINDY/services/masterplan_factory.py:15`
- Memory Bridge HMAC validation: `AINDY/routes/bridge_router.py:41`
- Canonical metrics unique constraint migration: `AINDY/alembic/versions/97ef6237e153_structure_integrity_check.py:24`
- Health check endpoint mismatch (`/tools/seo/*` pings): `AINDY/routes/health_router.py:61`
- Duplicate `POST /create_masterplan` definition: `AINDY/routes/main_router.py:236`
- Note: Line numbers are approximate and may shift as files change; re-verify during audits.
