# Testing Strategy

This document distinguishes current testing reality from required policy going forward. It defines testing discipline and does not invent tests or tooling that are not present.

## 1. Current Testing Landscape

### Current State
- Root test files:
- `test_calculations.py` (FastAPI TestClient calls for calculation endpoints)
- `test_routes.py` (FastAPI TestClient calls for calculation endpoints)
- `test_import.py` (simple import check)
- `AINDY/tests/`:
- `AINDY/tests/example.py` (minimal placeholder)
- Scope:
- Tests focus primarily on calculation endpoints in `AINDY/routes/main_router.py`.
- Coverage is minimal and does not include most services, background loops, or other routes.
- Coverage tooling is not configured in the repository (no coverage config files observed).
- Endpoints exercised by current tests (exact paths):
- `POST /ai_productivity_boost`
- `test_calculations.py::test_post_ai_productivity_boost`
- `test_routes.py::test_post_ai_productivity_boost`
- `POST /income_efficiency`
- `test_calculations.py::test_post_income_efficiency`
- `test_routes.py::test_post_income_efficiency`
- `POST /execution_speed`
- `test_calculations.py::test_post_execution_speed`
- `test_routes.py::test_post_execution_speed`
- `POST /engagement_rate`
- `test_calculations.py::test_post_engagement_rate`
- `test_routes.py::test_post_engagement_rate`
- `POST /lost_potential`
- `test_calculations.py::test_post_lost_potential`
- `test_routes.py::test_post_lost_potential`
- `POST /decision_efficiency`
- `test_calculations.py::test_post_decision_efficiency`
- `test_routes.py::test_post_decision_efficiency`
- `POST /batch_calculations`
- `test_calculations.py::test_post_batch_calculations`
- `test_routes.py::test_post_batch_calculations`
- `GET /results`
- `test_calculations.py::test_get_results`
- `test_routes.py::test_get_results`
- Known gaps (current state):
- No tests for Memory Bridge, Genesis, RippleTrace, Network Bridge, Social Layer, or DB verification routes.
- No explicit tests for background task loops (`AINDY/services/task_services.py`).
- No migration validation tests.
- No error handling contract tests.

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
- Minimal route coverage limited to calculation endpoints.
- No coverage metrics are configured in the repository.
- No CI enforcement is defined in the repository.
- Missing tests for services, background loops, migrations, and error-handling contracts.
- Duplicate test names exist (`test_get_results` appears multiple times in `test_routes.py`), which can lead to test collection conflicts or overwritten results depending on the test runner.
- Duplicate test function names across files (potential conflicts): 
- `test_get_results` (`test_calculations.py`, `test_routes.py`)
- `test_post_ai_productivity_boost` (`test_calculations.py`, `test_routes.py`)
- `test_post_batch_calculations` (`test_calculations.py`, `test_routes.py`)
- `test_post_decision_efficiency` (`test_calculations.py`, `test_routes.py`)
- `test_post_engagement_rate` (`test_calculations.py`, `test_routes.py`)
- `test_post_execution_speed` (`test_calculations.py`, `test_routes.py`)
- `test_post_income_efficiency` (`test_calculations.py`, `test_routes.py`)
- `test_post_lost_potential` (`test_calculations.py`, `test_routes.py`)
- Duplicate test function names within the same file (higher risk of overwriting in collection):
- `test_get_results` appears 3 times in `test_routes.py`
