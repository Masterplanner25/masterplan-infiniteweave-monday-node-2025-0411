# Testing Strategy

This document distinguishes current testing reality from required policy going forward. It defines testing discipline and does not invent tests or tooling that are not present.

## 1. Current Testing Landscape

### Current State (as of 2026-03-17)

**Diagnostic suite** (`AINDY/tests/`) — 162 tests across 10 files. Final result: **162 passing, 0 failing**.

| File | Tests | Coverage |
|------|-------|----------|
| `tests/conftest.py` | — | Shared fixtures: TestClient, mock_db, mock_openai, auth_headers, api_key_headers |
| `tests/test_calculation_services.py` | 26 | All Infinity Algorithm formulas, C++ kernel flag, Python/C++ parity |
| `tests/test_memory_bridge.py` | 40 | Python bridge layer, MemoryNodeDAO, Rust/C++ kernel (cosine similarity, weighted dot product, dim=1536) |
| `tests/test_models.py` | 15 | SQLAlchemy model structure, orphan function documentation |
| `tests/test_routes_health.py` | 6 | Health endpoint structure and response time |
| `tests/test_routes_tasks.py` | 14 | Task route auth enforcement (401 without token), acceptance with valid JWT, schema validation |
| `tests/test_routes_bridge.py` | 8 | HMAC validation, TTL enforcement, read path |
| `tests/test_routes_analytics.py` | 13 | Analytics route auth enforcement, zero-view guard, zero-difficulty 422 |
| `tests/test_routes_leadgen.py` | 10 | Route auth enforcement, dead code documentation |
| `tests/test_routes_genesis.py` | 13 | Route auth enforcement, import regression guards |
| `tests/test_security.py` | 25 | JWT auth (401 + acceptance), CORS, rate limiting, hardcoded key scan, permission secret; Phase 3: seo/authorship/arm/rippletrace/freelance/research/dashboard/social/db_verify/network_bridge rejection + acceptance |

Test infrastructure: `pytest==9.0.2`, `pytest-mock==3.15.1`, `pytest-asyncio==1.3.0`, `python-jose==3.5.0`, `passlib==1.7.4`, `bcrypt==4.0.1`, `slowapi==0.1.9` in `requirements.txt`. Discovery configured in `pytest.ini`.

**Root test files** (legacy, minimal scope):
- `test_calculations.py` — FastAPI TestClient calls for calculation endpoints
- `test_routes.py` — FastAPI TestClient calls for calculation endpoints (duplicate test names — see §8)
- `test_import.py` — simple import check

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

## 8. Known Gaps
- No coverage metrics tooling configured in the repository (no coverage config files).
- No CI enforcement defined in the repository.
- No migration validation tests (`AINDY/alembic/` has no test harness).
- No tests for background task loops (`AINDY/services/task_services.py`).
- No error handling contract tests validating JSON error structure per `docs/governance/ERROR_HANDLING_POLICY.md`.
- Duplicate test function names in legacy root test files (potential collection conflicts):
  - `test_get_results` (`test_calculations.py`, `test_routes.py`) — also appears 3 times within `test_routes.py`
  - `test_post_ai_productivity_boost`, `test_post_batch_calculations`, `test_post_decision_efficiency`, `test_post_engagement_rate`, `test_post_execution_speed`, `test_post_income_efficiency`, `test_post_lost_potential` (`test_calculations.py`, `test_routes.py`)
- ✅ **Resolved (2026-03-17 Phase 2):** Security gap tests (authentication, CORS, rate limiting) are all passing. No intentional failures remain in the test suite. See `docs/roadmap/TECH_DEBT.md` §6.
