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
