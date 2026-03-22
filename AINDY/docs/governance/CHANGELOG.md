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
* Identity Layer (v5 Phase 2): `user_identity` table, `UserIdentity` ORM model, `IdentityService`
* Identity API endpoints: `GET/PUT /identity/`, `GET /identity/evolution`, `GET /identity/context`
* Identity Layer tests (`tests/test_identity_layer.py`) and migration `bb4935e07dec_identity_layer_v5_phase2`
* Memory Metrics system: `memory_metrics` table, `MemoryMetricsEngine`, `MemoryMetricsStore`, and `/memory/metrics*` endpoints
* Memory Trace layer: `memory_traces` + `memory_trace_nodes`, `MemoryTraceDAO`, and `/memory/traces*` endpoints
* Symbolic memory ingest: `services/memory_ingest_service.py` and `Tools/ingest_memory.py`
* Request metrics baseline: `request_metrics` table + structured request logging middleware

## Changed

* Execution loop routing: `/memory/execute` now dispatches registered workflows (leadgen, genesis_message) via `runtime/execution_registry.py`
* Added HNSW index on `memory_nodes.embedding` (migration `f3a4b5c6d7e8`) for faster semantic recall
* Memory links now store numeric `weight` (migration `e2c3d4f5a6b7`) and traversal prefers weight over legacy strength
* Ongoing improvements to runtime behavior and system architecture
* ARM analysis and Genesis prompts now inject identity context when available
* Masterplan lock flow now observes identity posture signals for inference
* Health checks and memory metrics now emit structured JSON log summaries
* MasterPlan version column removed; `version_label` is canonical
* Observability query endpoint added: `GET /observability/requests`
* Genesis sessions now bind `user_id` (UUID FK to users) and legacy `user_id`/`user_id_str` columns are removed

---

# [main — CI/CD Pipeline Sprint] — 2026-03-18

## Summary

Implements the full GitHub Actions CI/CD pipeline. Every push and PR to `main` now runs lint (ruff) and tests with coverage enforcement. Establishes baseline coverage at 69%, enforces 64% floor. Adds PR governance scaffolding (template, CODEOWNERS, SECRETS.md, `.env.example`). CI badge added to README.

## Added
* **`.github/workflows/ci.yml`** — Two-job CI pipeline:
  - `lint`: ruff check (excludes `legacy/`, `bridge/memory_bridge_rs/`, `alembic/`)
  - `test`: pytest + coverage on `ubuntu-latest` with pgvector service container (postgres:5433)
  - Coverage XML artifact uploaded; Codecov integration included
  - `alembic upgrade head` runs before tests; `validate_memory_loop.py` excluded from test run
* **`AINDY/.coveragerc`** — Coverage omit patterns (venv, tests, alembic, bridge/memory_bridge_rs)
* **`AINDY/ruff.toml`** — Lint config: `E/F/W` rules, noisy rules suppressed, `legacy/` and Rust dirs excluded
* **`.github/PULL_REQUEST_TEMPLATE.md`** — Checklist: tests, coverage, lint, migrations, docs
* **`.github/CODEOWNERS`** — `@Masterplanner25` owns all files; explicit entries for CI, services, db, bridge
* **`.github/SECRETS.md`** — Documents all required Actions secrets with format guidance
* **`AINDY/.env.example`** — Template `.env` with all required variable names
* **`requirements.txt`** — Added `pytest-cov==7.0.0`, `ruff==0.15.6`

## Changed
* **`AINDY/pytest.ini`** — Added `addopts` block: `--ignore=tests/validate_memory_loop.py`, `--cov=.`, `--cov-report=term-missing`, `--cov-report=xml:coverage.xml`, `--cov-fail-under=64`
* **`README.md`** — CI badge added at top of file

## Design Decisions
* **Coverage threshold at 64%** (baseline 69% − 5% buffer): prevents regression without blocking CI on current untested paths
* **`validate_memory_loop.py` excluded**: requires live OpenAI and real DB; cannot run in CI without secrets
* **ruff suppresses 13 rules**: all are existing-code patterns (F401, F403, F541, F841, W292, E401, E402, E501, E731, F811, F821, W291, W293); new violations in any of these categories will still be caught if ruff adds new sub-rules
* **`alembic/` excluded from ruff**: migration files contain intentional patterns that trip lint
* **Tests run against in-memory mocks**: conftest.py sets all env vars via `setdefault()` — no real API keys needed in CI; pgvector service container only needed for `alembic upgrade head`

## Coverage Baseline (2026-03-18)
| Metric | Value |
|--------|-------|
| Total coverage | **69%** |
| Threshold (`--cov-fail-under`) | **64%** |
| Tests passing | **453** |
| Tests excluded from CI | `validate_memory_loop.py` |

---

# [main — Sprint 6+7: SQLAlchemy 2.0 + Memory Hook Completion] — 2026-03-18

## Summary

Sprint 6 closes the final deprecation warning (SQLAlchemy `declarative_base` import path). Sprint 7 completes memory hook coverage across all 5 LLM-calling workflows: genesis conversation and leadgen search now recall past context before the AI call and write structured memory nodes after. 453 tests passing, 0 warnings.

## Sprint 6 — SQLAlchemy 2.0 Migration

### Changed
* **`db/database.py`** — `from sqlalchemy.ext.declarative import declarative_base` → `from sqlalchemy.orm import declarative_base`. One-line fix, all models import `Base` from this single location. Deprecation warnings: **1 → 0**.

## Sprint 7 — Memory Prompt Injection Hooks (TECH_DEBT §12.4)

### Changed
* **`services/genesis_ai.py` — `call_genesis_llm()`** updated:
  - Renamed param `user_message` → `message`; added `user_id: str = None, db = None`
  - Recalls past strategic decisions/insights before Reflective Partner LLM call (tags: `genesis`, `masterplan`, `decision`; limit 2; injected into system prompt)
  - Writes `"insight"` node (`source="genesis_conversation"`) after each successful turn
  - All memory operations fire-and-forget; exceptions silenced with `logging.warning()`

* **`routes/genesis_router.py` — `POST /genesis/message`** updated:
  - Passes `message=user_message, user_id=str(user_id), db=db` to `call_genesis_llm()`

* **`services/leadgen_service.py` — `run_ai_search()`** updated:
  - Added `user_id: str = None, db = None` params
  - Recalls past leadgen searches before querying (tags: `leadgen`, `search`, `outcome`; limit 2)
  - Writes `"outcome"` node (`source="leadgen_search"`) after results are gathered
  - All memory operations fire-and-forget

* **`services/leadgen_service.py` — `create_lead_results()`** updated:
  - Added `user_id: str = None`; passes to `run_ai_search()`

* **`routes/leadgen_router.py` — `POST /leadgen/`** updated:
  - Passes `user_id=str(current_user["sub"])` to `create_lead_results()`

### Memory Hook Coverage (complete)
| Workflow | Recall | Write | node_type |
|----------|--------|-------|-----------|
| ARM analysis | ✅ | ✅ | outcome |
| ARM codegen | — | ✅ | outcome |
| Task completion | — | ✅ | outcome |
| Genesis conversation | ✅ | ✅ | insight |
| LeadGen search | ✅ | ✅ | outcome |

### Tests
* **`tests/test_sprint6_sprint7.py`** — 24 new tests across 3 classes:
  - `TestSprint6SQLAlchemy` (4): no deprecation warning, Base importable, shared metadata, new import path in source
  - `TestSprint7GenesisMemoryHook` (9): signature, recall/write hooks, insight node type, failure isolation, no-user-id skip, router pass-through
  - `TestSprint7LeadGenMemoryHook` (11): signature, recall/write hooks, outcome node type, failure isolation, no-user-id skip, router pass-through

### Design Decisions
* Genesis: prior context injected into `system_content = GENESIS_SYSTEM_PROMPT + prior_context` — appended to system prompt, not as a separate message, to preserve the Reflective Partner persona.
* LeadGen: recall happens on `run_ai_search()` (the search layer), not `create_lead_results()` (the pipeline layer), so the hook fires before any scoring or DB writes.
* Both hooks use `user_id=None` / `db=None` guard — no memory operations for system-internal or unauthenticated calls.

---

# [main — Sprint 5 User Isolation] — 2026-03-18

## Summary

Closes all remaining cross-user data exposure gaps identified in the Sprint 4 audit. Adds `user_id` to 5 tables, scopes all writes and reads in freelance, research, and rippletrace modules. 429 tests passing.

## Migration

* `d37ae6ebc319` — `sprint5_user_id_freelance_research_rippletrace`
  * `freelance_orders.user_id` — String, nullable, indexed
  * `client_feedback.user_id` — String, nullable, indexed
  * `research_results.user_id` — String, nullable, indexed
  * `drop_points.user_id` — String, nullable, indexed
  * `pings.user_id` — String, nullable, indexed

## Changed

* Execution loop routing: `/memory/execute` now dispatches registered workflows (leadgen, genesis_message) via `runtime/execution_registry.py`
* Added HNSW index on `memory_nodes.embedding` (migration `f3a4b5c6d7e8`) for faster semantic recall
* Memory links now store numeric `weight` (migration `e2c3d4f5a6b7`) and traversal prefers weight over legacy strength
* **`db/models/freelance.py`** — `FreelanceOrder` and `ClientFeedback` ORM models updated with `user_id` column.
* **`db/models/research_results.py`** — `ResearchResult` ORM model updated with `user_id` column.
* **`db/models/drop.py`** — `DropPointDB` and `PingDB` ORM models updated with `user_id` column.
* **`services/freelance_service.py`** — `create_order()` and `collect_feedback()` accept `user_id=None` and set it on record. `get_all_orders()` and `get_all_feedback()` accept `user_id=None` and filter when set.
* **`services/research_results_service.py`** — `create_research_result()` accepts `user_id=None` and sets it. `get_all_research_results()` accepts `user_id=None` and filters when set.
* **`services/rippletrace_services.py`** — all 6 functions (`add_drop_point`, `add_ping`, `get_all_drop_points`, `get_all_pings`, `get_recent_ripples`, `get_ripples`) accept `user_id=None`. `log_ripple_event()` accepts `user_id=None` (system-internal calls pass None; system-generated drop points remain unowned).
* **`routes/freelance_router.py`** — all create/read routes extract `current_user["sub"]` and pass to service. `POST /deliver/{id}` verifies ownership before delegating.
* **`routes/research_results_router.py`** — all create/read routes pass `user_id=current_user["sub"]` to service.
* **`routes/rippletrace_router.py`** — all create/read routes pass `user_id=current_user["sub"]` to service.

## Tests

* **`tests/test_sprint5_isolation.py`** — 27 new tests across 4 classes: `TestFreelanceIsolation`, `TestResearchIsolation`, `TestRippletraceIsolation`, `TestUserIdColumnPresence`. Verifies auth requirements, user_id presence in model/router/service, and ORM column existence.

## Design Decisions

* `client_feedback.user_id` is denormalized (not derived from the order FK) for simpler query filtering without joins.
* `revenue_metrics` is system-wide aggregate — no user scope applied.
* `rippletrace.log_ripple_event()` called by bridge system hooks passes `user_id=None` — system-generated pings remain unowned and will not appear in any user's scoped views.
* Existing rows with `user_id = NULL` are treated as legacy unowned data — not visible to any user in scoped queries.

## Docs Updated (Sprint 5 governance protocol)

* **`docs/architecture/DATA_MODEL_MAP.md`** — added `user_id` column entries for all 5 tables; added Sprint 5 migration entry in Section 3; added migration reminder callout.
* **`docs/engineering/MIGRATION_POLICY.md`** — added explicit rule in Section 2: always run `alembic upgrade head` immediately after any SQLAlchemy model change.
* **`docs/engineering/DEPLOYMENT_MODEL.md`** — added development reminder in Section 4: run migrations before starting the server or tests.
* **`docs/interfaces/API_CONTRACTS.md`** — updated route inventory auth annotations for `main_router` (JWT, not public) and `bridge_router` (JWT + API key per route); updated authentication model to reflect Sprint 4 hardening and Sprint 5 user scoping behavior.

---

# [main — Sprint 4 Auth Hardening] — 2026-03-18

## Summary

Auth hardening sprint: closed all unprotected route vectors, added cross-user ownership enforcement on analytics and memory, fixed Pydantic v2 deprecations. 402 tests passing, warnings reduced from 7 → 1.

## Changed

* Execution loop routing: `/memory/execute` now dispatches registered workflows (leadgen, genesis_message) via `runtime/execution_registry.py`
* Added HNSW index on `memory_nodes.embedding` (migration `f3a4b5c6d7e8`) for faster semantic recall
* Memory links now store numeric `weight` (migration `e2c3d4f5a6b7`) and traversal prefers weight over legacy strength
* **`routes/bridge_router.py`** — `POST /bridge/nodes`, `GET /bridge/nodes`, `POST /bridge/link` now require JWT (`Depends(get_current_user)` per endpoint). `POST /bridge/user_event` now requires API key (`Depends(verify_api_key)`). All bridge endpoints protected.
* **`routes/main_router.py`** — `dependencies=[Depends(get_current_user)]` added at router level. All 17 calc endpoints, `/results`, `/masterplans`, `/create_masterplan` now require JWT. Rate-limit bypass vector closed.
* **`routes/analytics_router.py`** — `GET /analytics/masterplan/{id}` and `GET /analytics/masterplan/{id}/summary` now verify `MasterPlan.user_id == current_user["sub"]` before returning data. Returns 404 for wrong owner (not 403 — don't leak existence).
* **`routes/memory_router.py`** — `GET /memory/nodes/{node_id}` now checks `node.user_id == current_user["sub"]`; returns 404 if node belongs to another user.
* **`schemas/freelance.py`** — Migrated 3 schemas (`FreelanceOrderResponse`, `FeedbackResponse`, `RevenueMetricsResponse`) from `class Config: orm_mode = True` to `model_config = ConfigDict(from_attributes=True)`.
* **`schemas/analytics_inputs.py`** — `@validator("task_difficulty")` replaced with `@field_validator` + `@classmethod` (Pydantic v2).
* **`schemas/research_results_schema.py`** — `class Config: from_attributes = True` replaced with `model_config = ConfigDict(from_attributes=True)`.

## Tests

* **`tests/test_routes_bridge.py`** — Updated 6 test methods to include `auth_headers` / `api_key_headers`. Added 4 new hardening tests (JWT-required and API-key-required assertions).
* **`tests/test_routes_analytics.py`** — 3 calc-endpoint tests updated to include `auth_headers`.
* **`tests/test_security.py`** — Added `TestSprintFourAuthHardening` class (18 tests): calc endpoint auth, bridge auth, user_event API key, analytics ownership, memory ownership.

## Known Open Items

* Cross-user exposure remains on `freelance_orders`, `client_feedback`, `research_results`, `rippletrace` tables — no `user_id` column exists on these models; migration required before filter can be applied.
* `Task.user_id` remains commented-out; task CRUD is still not user-scoped.
* SQLAlchemy `declarative_base()` deprecation (1 remaining warning) — requires SQLAlchemy 2.0 migration.

---

# [main — Memory Bridge Phase 3] — 2026-03-18

## Summary

Phase 3 ("Make It Useful") wires the memory recall and write hooks into ARM analysis, ARM code generation, Task completion, and Genesis lock/activate workflows. Run 1 writes; Run 2 recalls.

## Added

* **`bridge/bridge.py::recall_memories()`** — programmatic bridge function for internal service use. Calls `MemoryNodeDAO.recall()` with resonance scoring. Returns `[]` on failure (fire-and-forget). Exported from `bridge/__init__.py`.
* **`tests/test_memory_bridge_phase3.py`** — 22 new tests across 5 classes: `TestRecallMemoriesBridge`, `TestCreateMemoryNodeBridge`, `TestARMAnalysisMemoryHook`, `TestARMCodegenMemoryHook`, `TestTaskCompletionMemoryHook`, `TestGenesisMemoryHooks`.
* **`tests/validate_memory_loop.py`** — live two-run loop validation script. Run 1 writes a node; Run 2 recalls it by resonance score. Requires Docker pgvector on port 5433.

## Changed

* Execution loop routing: `/memory/execute` now dispatches registered workflows (leadgen, genesis_message) via `runtime/execution_registry.py`
* Added HNSW index on `memory_nodes.embedding` (migration `f3a4b5c6d7e8`) for faster semantic recall
* Memory links now store numeric `weight` (migration `e2c3d4f5a6b7`) and traversal prefers weight over legacy strength
* **`bridge/bridge.py::create_memory_node()`** — upgraded to use `db.dao.memory_node_dao.MemoryNodeDAO.save()` (with embedding generation). Default `node_type` changed from `"generic"` to `None` to pass ORM `VALID_NODE_TYPES` validation.
* **`db/dao/memory_node_dao.MemoryNodeDAO.save()`** — default `node_type` changed from `"generic"` to `None` (was causing `ValueError` from ORM event listener on every call with default).
* **`modules/deepseek/deepseek_code_analyzer.py`** — three memory hooks added:
  - Retrieval hook in `run_analysis()`: calls `recall_memories(query=filename, tags=["arm", "analysis"])` before prompt build; injects prior context into `user_prompt` as "Prior analysis memory" section.
  - Write hook in `run_analysis()`: after `db.commit()`, writes `"outcome"` node tagged `["arm", "analysis", ext]`.
  - Write hook in `generate_code()`: after `db.commit()`, writes `"outcome"` node tagged `["arm", "codegen", language]`.
* **`services/task_services.py::complete_task()`** — added `user_id: str = None` optional param (backward compatible). After `db.commit()`, writes `"outcome"` node tagged `["task", "completion"]` when `user_id` is provided.
* **`routes/genesis_router.py::lock_masterplan()`** — after `create_masterplan_from_genesis()` succeeds, writes `"decision"` node tagged `["genesis", "masterplan", "decision"]` with vision summary excerpt.
* **`routes/genesis_router.py::activate_masterplan()`** — after `db.commit()`, writes `"decision"` node tagged `["genesis", "masterplan", "activation"]`.

## Node Type Assignments

| Workflow | node_type | tags |
|---|---|---|
| ARM analysis | `outcome` | `["arm", "analysis", ext]` |
| ARM codegen | `outcome` | `["arm", "codegen", language]` |
| Task completion | `outcome` | `["task", "completion"]` |
| Genesis lock | `decision` | `["genesis", "masterplan", "decision"]` |
| Masterplan activate | `decision` | `["genesis", "masterplan", "activation"]` |

## Test Result

384 passing, 0 failing (was 362 before Phase 3).

---

# [feature/cpp-semantic-engine — Memory Bridge Phase 2] — 2026-03-18

## Added

* **`services/embedding_service.py`** — OpenAI `text-embedding-ada-002` embedding generation (1536 dims). `generate_embedding()` with zero-vector fallback and 3-attempt retry. `cosine_similarity()` using C++ kernel (`memory_bridge_rs.semantic_similarity`) with pure Python fallback.
* **`memory_nodes.embedding`** — `VECTOR(1536)` column added via migration `mb2embed0001`. pgvector extension enabled. Nullable; zero-vector is written on OpenAI failure.
* **`MemoryNodeDAO.find_similar()`** — pgvector `<=>` cosine distance retrieval. Filters NULL embeddings, user_id, node_type, min_similarity. Returns `similarity` and `distance` per node.
* **`MemoryNodeDAO.recall()`** — resonance v2 scoring combining semantic + graph + recency + success_rate + usage_frequency, then multiplied by adaptive weight and capped at 1.0. Formula: `(semantic * 0.40) + (graph * 0.15) + (recency * 0.15) + (success_rate * 0.20) + (usage_frequency * 0.10)`.
* **`MemoryNodeDAO.recall_by_type()`** — type-filtered resonance recall. Validates against `VALID_NODE_TYPES`.
* **`POST /memory/nodes/search`** — semantic similarity search endpoint (JWT auth).
* **`POST /memory/recall`** — primary retrieval API (JWT auth). Returns scoring metadata.
* **`VALID_NODE_TYPES = {"decision", "outcome", "insight", "relationship"}`** — enforced via SQLAlchemy ORM event listener (`before_insert`/`before_update`) and Pydantic Literal on request schema.

## Changed

* Execution loop routing: `/memory/execute` now dispatches registered workflows (leadgen, genesis_message) via `runtime/execution_registry.py`
* Added HNSW index on `memory_nodes.embedding` (migration `f3a4b5c6d7e8`) for faster semantic recall
* Memory links now store numeric `weight` (migration `e2c3d4f5a6b7`) and traversal prefers weight over legacy strength
* **`MemoryNodeDAO.save()`** — now generates and stores embedding on every write. New param `generate_embedding: bool = True`.
* **`CreateNodeRequest.node_type`** — upgraded from `str` to `Literal[...]` (API-level type validation).
* **`docs/architecture/DATA_MODEL_MAP.md`** — `memory_nodes` schema updated (embedding column, source, user_id, VALID_NODE_TYPES, migration note).
* **`docs/architecture/SYSTEM_SPEC.md`** — Memory Bridge section updated; data flow diagrams updated.
* **`docs/governance/INVARIANTS.md`** — Invariants 27 (node type enforcement) and 28 (zero-vector fallback) added.
* **`docs/interfaces/MEMORY_BRIDGE_CONTRACT.md`** — §8 added documenting all 7 `/memory/*` endpoints.
* **`docs/roadmap/TECH_DEBT.md`** — §10.5, §10.6, §10.7, §8 embedding item closed. §12 (Phase 3 open items) added.

---

# [main — Docker pgvector Setup] — 2026-03-18

## Added

* **`docker-compose.yml`** (repo root) — `pgvector/pgvector:pg16` container on port `5433`
  with named volume `aindy_pgdata` for data persistence and `unless-stopped` restart policy.
* **`AINDY/docs/DOCKER_SETUP.md`** — full operational guide: quick start, connection details,
  common commands, data persistence, rollback to PG18 instructions.
* **`AINDY/.env.pg18`** — backup of original PG18 connection string (gitignored); allows
  one-file rollback to local PostgreSQL 18 if needed.
* **`pgvector==0.4.2`** added to `requirements.txt` (Python package; installed in venv).
* **`.env.pg18`** added to root `.gitignore`.

## Notes

* Docker Desktop is not yet installed on the development machine. Container is not running.
  `.env` and `alembic.ini` still point to `localhost:5432` (PG18). Port update (`5432→5433`),
  `CREATE EXTENSION IF NOT EXISTS vector`, and `alembic upgrade head` are deferred until
  Docker Desktop is installed. See `AINDY/docs/DOCKER_SETUP.md` for the complete runbook.
* pgvector Python package (`pgvector.sqlalchemy.Vector`) is fully functional; `Vector(1536)`
  type confirmed working. SQLAlchemy integration is ready for Phase 2 migration authoring.

---

# [feature/cpp-semantic-engine — Memory Bridge Phase 1] — 2026-03-18

## Added

* **Write path fix** — `create_memory_node()` in `bridge/bridge.py` rewritten to write
  to `MemoryNodeModel` via `MemoryNodeDAO` (table: `memory_nodes`). Previous behavior
  silently wrote to `CalculationResult` (table: `calculation_results`) and discarded
  content and tags. Bug confirmed and documented since `feature/cpp-semantic-engine`.
* **New signature** — `create_memory_node(content, source, tags, user_id, db, node_type)`.
  Callers updated: `leadgen_service.py`, `research_results_service.py`, `social_router.py`.
  When `db=None`, returns a transient `MemoryNode` (logs a warning; does not crash).
* **`create_memory_link(source_id, target_id, link_type, db)`** — new bridge function;
  persists a directed link via `MemoryNodeDAO.create_link()`. Raises `ValueError` if `db=None`.
  Exported from `bridge/__init__.py`.
* **`MemoryTrace` docstring** — clarifies transient-only status; not a source of truth.
* **`db/dao/memory_node_dao.py`** — canonical DAO for memory operations:
  `save()`, `get_by_id()`, `get_by_tags()`, `get_linked_nodes()`, `create_link()`, `_node_to_dict()`.
* **`routes/memory_router.py`** — 5 JWT-protected endpoints:
  `POST /memory/nodes` (201), `GET /memory/nodes/{id}` (404 if not found),
  `GET /memory/nodes/{id}/links` (with `direction` param), `GET /memory/nodes` (tag search),
  `POST /memory/links` (201, 422 on ValueError).
* **Alembic migration `492fc82e3e2b`** — adds `source VARCHAR(255)` and `user_id VARCHAR(255)`
  to `memory_nodes`. (`extra JSONB` column was already present.)
* **`source` and `user_id` columns** added to `MemoryNodeModel` ORM and exposed in all DAO return dicts.
* `tests/test_memory_bridge_phase1.py` — 36 tests across 4 classes:
  `TestWritePathFix` (8), `TestMemoryNodeDAOUnit` (11), `TestMemoryRouterEndpoints` (12),
  `TestCreateMemoryLinkUnit` (5). 0 failing.

## Fixed

* ~~`create_memory_node()` writes to wrong table (`CalculationResult` / `calculation_results`).~~
  **FIXED:** Now writes to `MemoryNodeModel` / `memory_nodes` via `MemoryNodeDAO`.
* ~~Broken import path in `bridge.py`: `from db.models.models import CalculationResult`.~~
  **FIXED:** `CalculationResult` no longer referenced.

## Tests

* Flipped `TestCreateMemoryNodeWrongTable.test_create_memory_node_uses_wrong_table` →
  `test_create_memory_node_uses_correct_table` + `test_create_memory_node_without_db_returns_memory_node`
  (1→2 tests; was a bug-documenting test, now a regression guard).
* Flipped `test_routes_leadgen.py::test_create_memory_node_called_with_wrong_table` →
  `test_create_memory_node_no_longer_uses_wrong_table` (asserts `"CalculationResult" not in source`).
* **Total test count: 338 (was 301).**

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

* Execution loop routing: `/memory/execute` now dispatches registered workflows (leadgen, genesis_message) via `runtime/execution_registry.py`
* Added HNSW index on `memory_nodes.embedding` (migration `f3a4b5c6d7e8`) for faster semantic recall
* Memory links now store numeric `weight` (migration `e2c3d4f5a6b7`) and traversal prefers weight over legacy strength
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
* ✅ **Resolved (2026-03-21):** Bridge write routes are JWT-only; HMAC permission retired.
* `db/models/user.py` has no role or permission fields — authorization is binary (authenticated vs. not); no scoped permissions

---

# [feature/cpp-semantic-engine — Phase 2 security] — 2026-03-17

## Added

* `services/auth_service.py` — JWT token creation/verification, API key validation, password hashing (`python-jose`, `passlib/bcrypt==4.0.1`)
* `schemas/auth_schemas.py` — `LoginRequest`, `RegisterRequest`, `TokenResponse` Pydantic models
* ✅ **Resolved (2026-03-17):** Auth routes use DB-backed user model (no in-memory user store).
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

* ✅ **Resolved (2026-03-17):** User ORM model added; auth router uses `db.models.user.User`.
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

* Execution loop routing: `/memory/execute` now dispatches registered workflows (leadgen, genesis_message) via `runtime/execution_registry.py`
* Added HNSW index on `memory_nodes.embedding` (migration `f3a4b5c6d7e8`) for faster semantic recall
* Memory links now store numeric `weight` (migration `e2c3d4f5a6b7`) and traversal prefers weight over legacy strength
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
