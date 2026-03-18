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

## 9. Prioritization Table

| Area | Risk Level (Low/Medium/High) | Impact | Recommended Phase |
|------|------------------------------|--------|-------------------|
| Schema / Migration | High | Risk of runtime failures due to drift or missing constraints | Phase 1 |
| Error Handling | High | Inconsistent client behavior and poor fault isolation | Phase 1 |
| C++ Kernel (wrong-table bug) | High | Memory nodes created via services are silently lost | Phase 1 |
| Concurrency | Medium | Duplicated background work and unbounded loops | Phase 2 |
| Security | Medium | Increased exposure due to lack of auth and rate limiting | Phase 2 |
| Testing | Medium | Undetected regressions and poor change safety | Phase 2 |
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
