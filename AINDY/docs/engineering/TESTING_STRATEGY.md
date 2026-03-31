# Testing Strategy

This document distinguishes current testing reality from required policy going forward. It defines testing discipline and does not invent tests or tooling that are not present.

## 1. Current Testing Landscape

### Current State (as of 2026-03-27)

The historical breakdown below is preserved, but the current validated baseline has moved substantially since the early CI rollout.

**Current test architecture**
- Pytest runs in `TEST_MODE=true` by default.
- The primary test runtime is a real SQLite-backed SQLAlchemy session, not `MockSession`.
- Shared fixtures live under `tests/fixtures/` and provide:
  - `db_session`
  - `client`
  - `test_user`
  - `auth_headers`
- Async heavy execution is off by default in tests and is enabled only per-test when the `202` queueing contract is under test.
- Test env defaults are injected in `tests/conftest.py`, including:
  - `SECRET_KEY`
  - `AINDY_API_KEY`
  - `PERMISSION_SECRET`
  - `AINDY_ENABLE_LEGACY_SURFACE=true`
- Root-level legacy `tests/test_*.py` files have been removed; active tests live under:
  - `tests/unit/`
  - `tests/integration/`
  - `tests/api/`
  - `tests/system/`

**Current system-level invariant coverage**
- `tests/system/test_invariants.py` validates:
  - execution emits durable events
  - cross-user isolation holds across core routes
  - capability denial changes the real execution path
  - memory create/read consistency holds
  - request metrics and dashboard summaries reflect executed actions
- Agent runtime invariants are additionally covered in:
  - `tests/system/test_agent_events.py`
  - `tests/system/test_deterministic_agent.py`
  - `tests/system/test_capability_system.py`
- Runtime hardening invariants are covered in:
  - `tests/system/test_hardening.py`
  - async jobs never disappear without an `AutomationLog` terminal state
  - failed async jobs roll back partial DB writes before persisting failure state
  - scheduler lease exclusivity holds across competing workers
  - canonical execution event chains stay complete
  - invalid agent run IDs fail cleanly as `400` instead of surfacing as `500`
- These suites use real persisted `AgentRun`, `AgentStep`, `AgentEvent`, `SystemEvent`, and `AutomationLog` rows with only boundary mocks for external planners/executors.

**Current validated baseline** — local `pytest -q --tb=short` after Sprint N+11:
- **1,290 passed**
- **4 skipped**
- **0 failed**
- full suite green under `pytest -q --no-cov`

**Current runtime guarantees validated by the green suite**
- UUID identity normalization holds across route/service/system paths.
- TEST_MODE auth stays deterministic without collapsing all users onto one identity.
- Legacy compatibility endpoints are tested through their real API-key protection, not as public routes.
- Memory recall strategies are request-isolated; no shared mutable strategy state leaks between tests or executions.
- Successful and failed execution paths both persist `SystemEvent` rows under the DB-backed fixture stack.
- Queued async execution emits both queue-time and worker-time lifecycle events:
  - `execution.started` at submission
  - `async_job.started` / `async_job.completed` / `async_job.failed` for queued worker execution
  - `execution.completed` / `execution.failed` as canonical ledger events

| File | Tests | Coverage |
|------|-------|----------|
| `tests/conftest.py` | — | Shared fixtures: TestClient, mock_db, mock_openai, auth_headers, api_key_headers |
| `tests/test_calculation_services.py` | 26 | All Infinity Algorithm formulas, C++ kernel flag, Python/C++ parity |
| `tests/test_memory_bridge.py` | 40 | Python bridge layer, MemoryNodeDAO, Rust/C++ kernel (cosine similarity, weighted dot product, dim=1536) |
| `tests/test_models.py` | 15 | SQLAlchemy model structure, orphan function documentation |
| `tests/test_routes_health.py` | 6 | Health endpoint structure and response time |
| `tests/test_routes_observability.py` | 2 | Observability endpoint auth + response shape |
| `tests/test_routes_dashboard.py` | 2 | Dashboard overview auth + response shape |
| `tests/test_routes_identity.py` | 4 | Identity route auth + response shapes |
| `tests/test_routes_memory_metrics.py` | 3 | Memory metrics auth + response shapes |
| `tests/test_routes_tasks.py` | 14 | Task route auth enforcement (401 without token), acceptance with valid JWT, schema validation |
| `tests/test_routes_bridge.py` | 8 | Bridge routes (JWT-only writes, read path) |
| `tests/test_routes_analytics.py` | 13 | Analytics route auth enforcement, zero-view guard, zero-difficulty 422 |
| `tests/test_routes_leadgen.py` | 10 | Route auth enforcement, dead code documentation |
| `tests/test_routes_genesis.py` | 35 | Route auth enforcement, import regression guards. Genesis Blocks 1-3 (22 new): TestGenesisBlock1 (10) — model column presence, factory signature, masterplan_router registration/auth; TestGenesisBlock2 (5) — new route registration, auth guards, one-way flag guard; TestGenesisBlock3 (7) — real LLM assertion, synthesis gate (422), posture logic, posture_description. |
| `tests/test_genesis_flow.py` | 55 | Genesis Blocks 4-6: TestValidateDraftIntegrity (13) — AUDIT_SYSTEM_PROMPT schema, retry logic, fail-safe, happy/failed path with mocked OpenAI; TestGenesisAuditRoute (6) — route registration, auth, handler reachability; TestMasterplanFactoryHardening (10) — synthesis_ready gate, draft_from_session, rollback-on-failure, posture from draft; TestMasterplanRouterLock (8) — new static /lock endpoint, ValueError→422, posture_description in response; TestMasterplanListResponseShape (4) — {"plans": [...]} shape; TestDuplicateRouteRemoval (4) — single handler in main_router, no duplicate paths; TestSynthesisPromptSchema (2) — synthesis_notes field; TestPostureDescriptionHelper (4) — all posture labels; TestGenesisFlowRouteRegistration (2) — all genesis + masterplan routes present. |
| `tests/test_security.py` | 25 | JWT auth (401 + acceptance), CORS, rate limiting, hardcoded key scan, permission secret; Phase 3: seo/authorship/arm/rippletrace/freelance/research/dashboard/social/db_verify/network_bridge rejection + acceptance |
| `tests/test_arm.py` | 62 | ARM Phase 1 (46): SecurityValidator, ConfigManager, FileProcessor, ARM routes with mocked OpenAI. ARM Phase 2 (16): TestARMMetrics route-level (4), TestARMMetricsService unit (7), TestARMConfigSuggestions unit (4), TestARMRoutes new endpoints (1). No DB required for service unit tests. |
| `tests/test_memory_bridge_phase1.py` | 36 | Memory Bridge Phase 1 (2026-03-18): TestWritePathFix (8) — create_memory_node() regression, transient fallback, MemoryTrace docstring, create_memory_link export; TestMemoryNodeDAOUnit (11) — save/get_by_id/get_by_tags/get_linked_nodes/create_link, source+user_id in _node_to_dict; TestMemoryRouterEndpoints (12) — router registration, 5 auth guards, create/get/search/link with mocked DAO; TestCreateMemoryLinkUnit (5) — DAO delegation, default link_type, source+user_id model columns. |
| `tests/test_memory_bridge_phase2.py` | 24 | Memory Bridge Phase 2 (2026-03-18): TestEmbeddingService (7) — OpenAI call, retry, zero-vector fallback, C++ kernel path, cosine_similarity_python correctness; TestMemoryNodeEmbeddingColumn (2) — column presence in model + DB; TestResonanceScoring (4) — formula correctness (semantic/tag/recency weights); TestMemoryTypeEnforcement (4) — Literal validation at API boundary, ORM event listener; TestMemoryRoutePhase2 (7) — POST /memory/nodes/search, POST /memory/recall (auth, 400 on no query/tags, scoring metadata). |
| `tests/test_memory_bridge_phase3.py` | 22 | Memory Bridge Phase 3 (2026-03-18): TestRecallMemoriesBridge (4) — no-db returns [], DAO delegation, failure returns [], node_type filter; TestCreateMemoryNodeBridge (3) — no-db transient, new DAO used, default node_type=None; TestARMAnalysisMemoryHook (4) — write fires on success, recall fires before prompt, skipped when no user_id, failure does not raise; TestARMCodegenMemoryHook (3) — write fires, failure silenced, skipped when no user_id; TestTaskCompletionMemoryHook (4) — write fires, skipped when no user_id, failure silenced, user_id kwarg accepted; TestGenesisMemoryHooks (4) — lock writes decision node, lock memory failure safe, activate writes decision node, activate memory failure safe. |

Test infrastructure: `pytest==9.0.2`, `pytest-mock==3.15.1`, `pytest-asyncio==1.3.0`, `pytest-cov==7.0.0`, `python-jose==3.5.0`, `passlib==1.7.4`, `bcrypt==4.0.1`, `slowapi==0.1.9` in `requirements.txt`. Discovery and coverage configured in `pytest.ini` and `AINDY/.coveragerc`.

**New test files (Sprint 6+7 / CI Sprint):**

| File | Tests | Coverage |
|------|-------|----------|
| `tests/test_sprint6_sprint7.py` | 24 | SQLAlchemy 2.0 import path (4), Genesis memory hook signature/behavior (9), LeadGen memory hook signature/behavior (11) |

**CI enforcement (current):** All tests run automatically on every push and PR to `main` via `.github/workflows/ci.yml`. Coverage threshold is 69%. Ruff lint is enforced in a separate job. `tests/validate_memory_loop.py` remains excluded from CI because it requires live OpenAI + a real DB.

**Execution-contract lint (current):** `.github/workflows/lint.yml` now runs `python tools/execution_contract_linter.py --strict`. The same check is available locally through `.pre-commit-config.yaml`. This is architecture enforcement rather than behavioral test coverage; it statically rejects route-entry, direct-memory, and direct-event patterns that bypass the execution pipeline.

**Root test files**
- Legacy root-level test files have been migrated out of `tests/` and replaced by the structured layout above.

**Phase 2 security tests** — all 7 previously-failing `_WILL_FAIL` security tests now pass. Each test verifies both the rejection path (no auth → 401) and the acceptance path (valid JWT → expected status). No intentional failures remain in the test suite.

**Phase 3 security tests** — 12 additional tests in `TestPhase3RouteProtection` class verify every router protected in Phase 3: `seo_routes`, `authorship_router`, `arm_router`, `rippletrace_router`, `freelance_router`, `research_results_router`, `dashboard_router`, `social_router` (JWT rejection), `db_verify_router`, `network_bridge_router` (API key rejection and acceptance).

## 2. Required Coverage Areas (Policy)

### A. Invariant Coverage
- Tests must validate all invariants defined in `docs/governance/INVARIANTS.md`.
- Any change affecting invariants requires updated tests.

### B. Service-Level Unit Tests
- All business logic in `AINDY/services/` must have unit tests.
- Pure logic must be isolated from DB where possible.
- DB interactions must be tested using transactional test sessions.

### C. Route-Level Integration Tests
- Critical routes must be tested via FastAPI `TestClient`.
- Validate success responses.
- Validate error classification (4xx vs 5xx).
- Validate response schema shape.
- API contracts must match `docs/interfaces/API_CONTRACTS.md`.

### D. Background Task Behavior
- Background loop functions must be tested in isolation.
- Infinite loops must be testable via controlled iteration or injection.
- Thread behavior must not require real daemon threads in tests.

### E. Invariant Tests
- Cross-domain guarantees belong in `tests/system/test_invariants.py` or another `tests/system/` file.
- These tests should use real persisted state and assert durable side effects, not just response codes.

## 3. Mocking Policy for External Model Providers

### A. OpenAI (`AINDY/services/genesis_ai.py`)
- Tests must not call real OpenAI APIs.
- Use dependency injection or patching to mock responses.
- Validate:
- Valid JSON path.
- Malformed JSON path.
- Model error path.

### B. DeepSeek Integration (`AINDY/services/deepseek_arm_service.py`)
- No real external calls during unit tests.
- Mock module behavior.
- Validate fallback/error behavior.

## 4. Database Testing Discipline

### Required Policy
- Use an isolated test database.
- Transactions must roll back after each test.
- No tests may run against production DB.
- Migrations must be validated via:
- `alembic upgrade head`
- `alembic downgrade` (if supported)
- Schema changes require migration validation before merge.

## 5. Migration Validation Requirements
- Any change to `AINDY/db/models/` requires:
- New Alembic revision.
- A test confirming new table/column existence.
- Existing migrations must never be edited after application.
- Migration diffs must be reviewed before merge.

## 6. Error Handling Validation
- Tests must confirm:
- Proper 4xx vs 5xx classification.
- No HTML error pages for API routes.
- JSON error structure matches `docs/governance/ERROR_HANDLING_POLICY.md`.

## 7. Minimum Merge Requirements (Policy Gate)
A change cannot be merged if:
- It modifies business logic without tests.
- It modifies schema without migration.
- It alters invariants without validation tests.
- It changes API contract without route-level test updates.
- The `Last updated` date in `docs/GOVERNANCE_INDEX.md` is not refreshed after doc changes.
- **CI checks fail** — every PR must pass the `lint` and `test` jobs in `.github/workflows/ci.yml` before merge. Coverage must remain at or above 69%.

## 8. Known Gaps
- Some structured tests still retain targeted mocks for external boundaries, especially older memory-bridge and model-provider coverage. That is acceptable only where the boundary is truly external or nondeterministic.
- The historical counts below are preserved for traceability, but they do not describe the current suite layout anymore.
- ✅ **Resolved (2026-03-18 CI/CD Sprint):** Coverage metrics tooling configured — `pytest-cov`, `.coveragerc`, and `--cov-fail-under=64` in `pytest.ini`. Baseline: 69%.
- ✅ **Resolved (2026-03-18 CI/CD Sprint):** CI enforcement live — GitHub Actions `ci.yml` enforces lint + test + coverage on every push/PR.
- No migration validation tests (`AINDY/alembic/` has no test harness).
- No tests for background task loops (`AINDY/services/task_services.py`).
- No error handling contract tests validating JSON error structure per `docs/governance/ERROR_HANDLING_POLICY.md`.
- ✅ **Resolved (2026-03-22):** Duplicate `test_get_results` names in `test_routes.py` renamed to unique identifiers. Other root tests still mirror names across files but are unique within each file.
- ✅ **Resolved (2026-03-22):** Migration drift guard added via `tests/test_migrations.py` (asserts `alembic current` equals `alembic heads`).
- ✅ **Resolved (2026-03-17 Phase 2):** Security gap tests (authentication, CORS, rate limiting) are all passing. No intentional failures remain in the test suite. See `docs/roadmap/TECH_DEBT.md` §6.
- ✅ **Resolved (2026-03-17 ARM Phase 2):** `test_arm.py` expanded with 16 new tests for Thinking KPI System: `TestARMMetrics` (route-level auth + structure), `TestARMMetricsService` (pure unit — no DB, uses `__new__` + `MagicMock`), `TestARMConfigSuggestions` (pure unit — no DB). Pattern established: service unit tests bypass DB entirely using `ARMMetricsService.__new__()` to isolate calculation logic.
- ✅ **Resolved (2026-03-17 Genesis Blocks 4-6):** `test_genesis_flow.py` added with 55 tests covering: `validate_draft_integrity()` with mocked OpenAI (including retry and fail-safe paths), `POST /genesis/audit` route registration + auth, factory hardening (`synthesis_ready` gate, `db.rollback()` path), `POST /masterplans/lock` endpoint, `GET /masterplans/` response shape, duplicate route removal, synthesis prompt schema, posture description helper. Total: 301 passing.
- ✅ **Resolved (2026-03-18 Memory Bridge Phase 1):** `test_memory_bridge_phase1.py` added with 36 tests. Bug-documenting tests in `test_memory_bridge.py` and `test_routes_leadgen.py` flipped to regression guards. Total: 338 passing.
- ✅ **Resolved (2026-03-18 Memory Bridge Phase 2):** `test_memory_bridge_phase2.py` added with 24 tests covering embedding service, resonance scoring, type enforcement (Pydantic Literal + ORM event), and Phase 2 API endpoints (`/memory/nodes/search`, `/memory/recall`). All OpenAI calls mocked. `test_models.py::test_memory_node_has_no_embedding_column` renamed and inverted to confirm column presence. Total: 362 passing.
- ✅ **Resolved (2026-03-18 Memory Bridge v4):** `test_memory_bridge_v4.py` added for feedback loop, resonance v2, suggestion engine, and endpoints. `validate_memory_v4.py` provides a live DB validation script. Total: 505 passing, 2 skipped.
- ✅ **Resolved (2026-03-18 Memory Bridge Phase 3):** `test_memory_bridge_phase3.py` added with 22 tests verifying workflow hooks across 5 integration surfaces: `bridge.recall_memories()`, updated `bridge.create_memory_node()`, ARM analysis/codegen hooks, task completion hook, Genesis lock/activate hooks. All hooks verified as fire-and-forget. Patch target: `db.dao.memory_node_dao.MemoryNodeDAO` (lazy import). Genesis tests use FastAPI `dependency_overrides`. Total: 384 passing.
