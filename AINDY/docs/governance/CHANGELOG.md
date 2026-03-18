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
