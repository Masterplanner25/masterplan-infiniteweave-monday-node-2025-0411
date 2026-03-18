## [Unreleased] — feature/cpp-semantic-engine

### Added (2026-03-18 - Memory Bridge v3: Structured Continuity)
- `alembic/versions/dc59c589ab1e_memory_bridge_v3_history_table.py` - Migration: `memory_node_history` table (append-only change log) + index on (`node_id`, `changed_at`).
- `alembic/versions/edc8c8d84cbb_repair_memory_nodes_tsv_trigger_drift.py` - Repair migration: removes stale `content_tsv` trigger/function/index drift from `memory_nodes` on upgraded databases.
- `db/models/memory_node_history.py` - ORM model for history snapshots (previous values only).
- `db/dao/memory_node_dao.py::update()` — explicit node updates now record prior state in history; optional embedding regeneration on content change.
- `db/dao/memory_node_dao.py::get_history()` — returns history entries (reverse chronological).
- `db/dao/memory_node_dao.py::traverse()` — DFS multi-hop traversal with cycle prevention + narrative summary.
- `db/dao/memory_node_dao.py::expand()` — related node expansion (linked + semantic neighbors).
- `db/dao/memory_node_dao.py::recall(expand_results=True)` — optional expanded context return.
- `routes/memory_router.py` — v3 endpoints:
  - `PUT /memory/nodes/{node_id}`
  - `GET /memory/nodes/{node_id}/history`
  - `GET /memory/nodes/{node_id}/traverse`
  - `POST /memory/nodes/expand`
  - `POST /memory/recall/v3`
- `tests/test_memory_bridge_v3.py` — v3 unit + route coverage (history, traversal, expansion, recall v3).
- `tests/validate_memory_v3.py` — live validation script for v3 success condition.

### Added (2026-03-18 — Memory Bridge Phase 2: Make It Intelligent)
- `alembic/versions/mb2embed0001` — Migration: `embedding VECTOR(1536)` column on `memory_nodes`. `CREATE EXTENSION IF NOT EXISTS vector` included. Idempotent (checks column existence before adding).
- `services/embedding_service.py` — OpenAI `text-embedding-ada-002` embedding generation (1536 dims). Zero-vector fallback on failure (never crashes). 3-attempt retry with exponential backoff. `cosine_similarity()` uses C++ kernel (`memory_bridge_rs.semantic_similarity` via `bridge/memory_bridge_rs/target/debug`) with pure Python fallback. `cosine_similarity_python()` available as standalone fallback.
- `services/memory_persistence.py` — `VALID_NODE_TYPES = {"decision", "outcome", "insight", "relationship"}`. SQLAlchemy `before_insert`/`before_update` event listener enforces type at ORM layer. `embedding = Column(Vector(1536), nullable=True)` added to `MemoryNodeModel`.
- `db/dao/memory_node_dao.py::find_similar()` — Semantic similarity retrieval via pgvector `<=>` cosine distance operator. Filters by `user_id`, `node_type`, `min_similarity`. Returns nodes with `similarity` and `distance` fields. NULL embeddings excluded.
- `db/dao/memory_node_dao.py::recall()` — Resonance-scored retrieval: `score = (semantic * 0.6) + (tag_match * 0.2) + (recency * 0.2)`. Recency decay: `exp(-age_days / 30.0)`. Deduplicates across semantic + tag paths. Primary retrieval method for Phase 3 workflow hooks.
- `db/dao/memory_node_dao.py::recall_by_type()` — Type-filtered resonance recall. Validates against `VALID_NODE_TYPES`. Calls `recall()` internally.
- `db/dao/memory_node_dao.py::save()` — Now accepts `generate_embedding: bool = True`. Generates and stores embedding via `embedding_service` before DB insert.
- `routes/memory_router.py::POST /memory/nodes/search` — Semantic similarity search. Accepts `query`, `limit`, `node_type`, `min_similarity`. Generates query embedding, calls `find_similar()`.
- `routes/memory_router.py::POST /memory/recall` — Primary retrieval API. Accepts `query`, `tags`, `limit`, `node_type`. Returns resonance-ranked results with scoring metadata (`semantic_weight`, `tag_weight`, `recency_weight`). Returns 400 if neither `query` nor `tags` provided.
- `routes/memory_router.py` — `CreateNodeRequest.node_type` upgraded from `str` to `Literal["decision", "outcome", "insight", "relationship"]`. Pydantic validates at API boundary.
- `tests/test_memory_bridge_phase2.py` — 24 tests covering: embedding service importability, 1536-dim output, zero-vector on empty input, cosine similarity (identical/orthogonal/zero vectors), C++ kernel confirmed working, embedding failure fallback, ORM column presence, DB column presence, resonance formula weights, recency decay, tag score calculation, type enforcement (VALID_NODE_TYPES, Literal schema), all 4 new route behaviors (auth required, 400 on missing params, recall with query, search with auth).

### Changed (2026-03-18 — Memory Bridge Phase 2)
- `tests/test_models.py::test_memory_node_has_no_embedding_column` renamed to `test_memory_node_has_embedding_column`; assertion inverted. Previously a diagnostic test tracking a known gap; now a regression guard confirming the column exists.

### Added (2026-03-17 — ARM Phase 1)
- `modules/deepseek/security_deepseek.py` — `SecurityValidator` fully implemented.
  Replaces stub. Raises `HTTPException` (FastAPI-native). Validation layers: path
  traversal blocking (BLOCKED_PATH_SEGMENTS), extension allowlist, regex-based
  sensitive content detection (OpenAI sk- keys, AWS AKIA keys, PEM private key
  blocks, generic `api_key=...` assignments, `.env` references), configurable size
  limit. Previously: basic keyword scan with `PermissionError`.
- `modules/deepseek/config_manager_deepseek.py` — `ConfigManager` fully implemented.
  16-key `DEFAULT_CONFIG` (model, temperatures, token limits, retry settings,
  Infinity Algorithm defaults). Runtime updates via `update(dict)` with key
  allowlist (unknown keys silently dropped). `_persist()` writes to
  `deepseek_config.json`. `calculate_task_priority()` implements Infinity Algorithm
  `TP = (Complexity × Urgency) / Resource Cost` with zero-division guard.
  Previously: 3-key minimal implementation.
- `modules/deepseek/file_processor_deepseek.py` — `FileProcessor` fully implemented.
  Line-boundary chunking (`chunk_content()`), UUID v4 session IDs
  (`create_session_id()`), structured session log dicts with Infinity Algorithm
  Execution Speed metric (tokens/second). Previously: activity log writer only.
- `modules/deepseek/deepseek_code_analyzer.py` — `DeepSeekCodeAnalyzer` fully
  implemented with OpenAI GPT-4o integration. `_call_openai()` uses
  `response_format={"type": "json_object"}`, configurable retry with delay,
  returns (text, input_tokens, output_tokens). `run_analysis()` full pipeline:
  security validation → chunking → prompt construction → GPT-4o → DB persist
  (`AnalysisResult`) → enriched result. `generate_code()` same pipeline for code
  generation (`CodeGeneration` DB record). Both persist failure records on error.
  Previously: keyword-counting stub returning summary string + template code.
- `db/models/arm_models.py` — `AnalysisResult` and `CodeGeneration` SQLAlchemy
  models added (UUID PKs, PostgreSQL dialect). `AnalysisResult`: session_id,
  user_id, file_path, file_type, analysis_type, prompt_used, model_used,
  input_tokens, output_tokens, execution_seconds, result_summary, result_full,
  task_priority, status, error_message, created_at. `CodeGeneration`: links to
  `AnalysisResult` via FK, generation_type, original_code, generated_code,
  language, quality_notes. Existing `ARMRun`, `ARMLog`, `ARMConfig` models retained.
- `routes/arm_router.py` — fully rewritten. Uses `DeepSeekCodeAnalyzer` directly
  (bypasses `deepseek_arm_service.py`). Singleton analyzer with config-reset on
  PUT /arm/config. New request schemas: `AnalyzeRequest` (file_path, complexity,
  urgency, context), `GenerateRequest` (prompt, original_code, language,
  generation_type, analysis_id), `ConfigUpdateRequest` (updates dict).
  GET /arm/logs returns `{analyses, generations, summary}` with Infinity metrics.
- `tests/test_arm.py` — 46 ARM-specific tests: `TestSecurityValidator` (16),
  `TestConfigManager` (10), `TestFileProcessor` (8), `TestARMRoutes` (12).
  OpenAI calls mocked; no real API calls. All 46 pass.
- Frontend ARM components updated to match new API contracts:
  `ARMAnalyze.jsx` — structured display with score badges, severity-tagged findings,
  Infinity metrics row. `ARMGenerate.jsx` — prompt-based interface with language
  selector, optional existing code, explanation + quality notes.
  `ARMLogs.jsx` — aligned to `{analyses, generations, summary}` response shape with
  metrics pills. `ARMConfig.jsx` + `api.js` — signatures updated to match new
  endpoint contracts.
- Total test suite: **208 passing, 0 failing** (up from 162).

### Added (2026-03-17 — Genesis Blocks 1-3)
- **Alembic migration** `a1b2c3d4e5f6_genesis_block1_missing_columns` — additive columns:
  - `genesis_sessions`: `synthesis_ready` (Boolean, default false), `draft_json` (JSON),
    `locked_at` (DateTime), `user_id_str` (String UUID)
  - `master_plans`: `user_id` (String UUID), `status` (String, default "draft")
- `db/models/masterplan.py` — `MasterPlan` gains `user_id` + `status`; `GenesisSessionDB`
  gains `synthesis_ready`, `draft_json`, `locked_at`, `user_id_str`.
- `services/masterplan_factory.py` — accepts `user_id` param; version count scoped per-user;
  sets `masterplan.status = "locked"` and `session.locked_at` on lock.
- `services/posture.py` — real posture detection replacing stub. Returns one of
  `Stable | Accelerated | Aggressive | Reduced` based on `time_horizon_years` and
  `ambition_score` from synthesis draft. Adds `posture_description()` helper.
- `services/genesis_ai.py` — `call_genesis_synthesis_llm()` replaced stub with real
  GPT-4o call using `response_format={"type": "json_object"}` and `SYNTHESIS_SYSTEM_PROMPT`.
  Produces structured draft: vision, horizon, mechanism, ambition_score, phases, domains,
  success_criteria, risk_factors. Fail-safe fallback on parse error.
- `routes/genesis_router.py` — full rewrite with user isolation:
  - All session queries scoped to `user_id_str` (from JWT `sub`)
  - `POST /genesis/session` — binds `user_id_str`
  - `POST /genesis/message` — persists `synthesis_ready` to DB as one-way flag
  - `GET /genesis/session/{id}` — new endpoint (Block 2)
  - `GET /genesis/draft/{id}` — new endpoint (Block 2)
  - `POST /genesis/synthesize` — gated on `synthesis_ready`, persists `draft_json`
  - `POST /genesis/lock` — passes `user_id` to factory
  - `POST /genesis/{plan_id}/activate` — scoped to current user, sets `status = "active"`
- `routes/masterplan_router.py` — new router (prefix `/masterplans`), JWT auth:
  - `POST /masterplans/{id}/lock`, `GET /masterplans/`, `GET /masterplans/{id}`,
    `POST /masterplans/{id}/activate`
- `routes/__init__.py` — `masterplan_router` registered.
- Frontend: `client/src/components/Genesis.jsx` — auth-wired rewrite using `api.js`
  functions (no raw fetch). Synthesis-ready banner, draft preview with LOCK PLAN button,
  locked confirmation panel. Phase 2/3 UI fully implemented.
- Frontend: `client/src/components/GenesisDraftPreview.jsx` — new Phase 3 editable preview
  component. Shows vision, horizon, mechanism, ambition score, phases, domains,
  success criteria, risk factors.
- Frontend: `client/src/components/MasterPlanDashboard.jsx` — rewritten to use
  authenticated `listMasterPlans()` / `activateMasterPlan()` from `api.js`. Status badges:
  ACTIVE (green) / LOCKED (yellow) / DRAFT (grey) / ARCHIVED (muted). Activate button on
  locked plans.
- `client/src/api.js` — `authRequest` helper (reads Bearer token from localStorage);
  10 new functions: `startGenesisSession`, `sendGenesisMessage`, `getGenesisSession`,
  `synthesizeGenesisDraft`, `getGenesisDraft`, `lockMasterPlan`, `listMasterPlans`,
  `getMasterPlan`, `activateMasterPlan`.
- Tests: 22 new tests in `tests/test_routes_genesis.py`:
  - `TestGenesisBlock1` (10 tests): model column presence, factory signature, masterplan_router registration/auth
  - `TestGenesisBlock2` (5 tests): new route registration, auth guards, one-way flag guard
  - `TestGenesisBlock3` (7 tests): real LLM assertion, synthesis gate, posture logic, posture_description helper
- Total test suite: **246 passing, 0 failing** (up from 224).

### Added (2026-03-17 — ARM Phase 2)
- `services/arm_metrics_service.py` — `ARMMetricsService` calculates all five
  Infinity Algorithm Thinking KPI metrics from `analysis_results` and
  `code_generations` DB history: Execution Speed (tokens/sec), Decision Efficiency
  (% success), AI Productivity Boost (output/input token ratio), Lost Potential
  (% wasted tokens on failed sessions), Learning Efficiency (speed trend first-half
  vs second-half). Handles empty history without crashing.
- `services/arm_metrics_service.py` — `ARMConfigSuggestionEngine` analyzes metrics
  against 5 configurable thresholds and produces prioritized, risk-labelled config
  suggestions. Categorises as auto_apply_safe (low-risk) or requires_approval
  (medium/high). Returns `combined_suggested_config` for one-shot apply.
  Suggestions are advisory only — never auto-applies.
- `routes/arm_router.py` — two new endpoints:
  - `GET /arm/metrics?window=30` — full Thinking KPI report
  - `GET /arm/config/suggest?window=30` — config suggestions with metrics snapshot
- Frontend: `client/src/components/ARMMetrics.jsx` — 5-card KPI dashboard with
  window selector (7/30/90 days), colour-coded efficiency/waste indicators,
  trend arrows for learning efficiency.
- Frontend: `client/src/components/ARMConfigSuggest.jsx` — suggestion panel grouped
  by priority (critical/warning/info), per-suggestion Apply button calls
  PUT /arm/config, "Apply All Low-Risk" button for batch apply.
- `client/src/api.js` — `getARMMetrics(window)` and `getARMConfigSuggestions(window)`
  added.
- Tests: 16 new tests in `tests/test_arm.py`: `TestARMMetrics` (4 route-level),
  `TestARMMetricsService` (7 unit), `TestARMConfigSuggestions` (4 unit). No DB
  required for service unit tests.
- Total test suite: **224 passing, 0 failing** (up from 208).

### Deferred to Phase 3 (ARM)
- Memory Bridge feedback loop: after each analysis/generation, persist a `MemoryNode`
  via `MemoryNodeDAO` with ARM results as structured content and tags.
  (Deferred: bridge design in progress.)
- Auto-approve low-risk config changes without user confirmation.
  Phase 2 returns auto_apply_safe list; Phase 3 will apply them automatically.

### Deferred to Phase 2 (ARM) — NOW COMPLETE
- ~~Self-tuning config: `ConfigManager.update()` to be called by an Infinity Algorithm
  feedback loop that adjusts temperature/model based on execution speed trends.~~
  **DONE (ARM Phase 2):** `ARMConfigSuggestionEngine` + GET /arm/config/suggest.
- ~~Infinity metric crosswalk: Decision Efficiency and Execution Speed metric
  integration into ARM response payloads.~~
  **DONE (ARM Phase 2):** All 5 metrics exposed via GET /arm/metrics.

### Added (C++ semantic engine — earlier in this branch)
- C++ semantic similarity engine (`memory_cpp/semantic.h` +
  `semantic.cpp`) providing high-performance vector math
- `cosine_similarity(a, b, len)` — foundation for semantic
  memory node search; ready for when embeddings are added
  to MemoryNode
- `weighted_dot_product(values, weights, len)` — directly
  powers `calculate_engagement_score()` in the Infinity Algorithm
- Rust extern "C" FFI bridge (`src/cpp_bridge.rs`) safely wrapping
  C++ operations for Python consumption
- `semantic_similarity()` and `weighted_dot_product()` exposed
  to Python via PyO3 in `memory_bridge_rs`
- Python fallback implementations in `calculation_services.py`
  (app works without compiled extension)
- `bridge/benchmark_similarity.py` for performance verification

### Changed
- `calculate_engagement_score()` in `calculation_services.py`
  now calls C++ `weighted_dot_product` kernel (with fallback)
- `Cargo.toml` updated: `cc` build-dependency added
- `build.rs` added for C++ compilation configuration

### Fixed
- `memorycore.py` (misnamed Rust source) archived to
  `bridge/archive/memory_bridge_core_draft.rs`
- `Memorybridgerecognitiontrace.rs` (orphan file) archived
  to `bridge/archive/`

### Technical Notes
- Build toolchain: MSVC VS 2022 Community (x64) via registry
- Build mode: debug (release blocked by Windows AppControl
  policy in `target/` directories)
- Benchmark (debug, dim=1536, 10k iters): Python 2.753s vs
  C++ 3.844s — debug FFI overhead dominates; release build
  expected to show 10–50x improvement
- Branch: `feature/cpp-semantic-engine`
- Commits: `6a14d64` (cleanup) + `2054914` (implementation)

---

# 🧠 A.I.N.D.Y. v1.0 — The "Anti-LinkedIn" Social Layer Build

**Date:** November 23, 2025
**Branch:** main (merged from feature/social-layer)
**Status:** ✅ Release | Full Stack Active

### 🔧 Summary
This update transforms A.I.N.D.Y. from a backend engine into a **Full-Stack Social Operating System**.
We have activated the **Social Layer** (MongoDB), the **Velocity Engine** (Task-to-Profile sync), and the **Memory Scribe** (Auto-Documentation).

### 🚀 New Modules & Integrations
* **`social_router.py`**: New API endpoints for Profiles, Feeds, and Trust Tiers.
* **`mongo_setup.py`**: Added MongoDB connection to handle flexible social data alongside SQL metrics.
* **`social_models.py`**: Pydantic schemas for `SocialProfile`, `SocialPost`, and `TrustTier`.
* **`task_services.py`**: Upgraded to trigger **Real-Time Profile Updates** upon task completion.

### 💻 Frontend Evolution (React Client)
* **`ProfileView.jsx`**: Live "Identity Node" displaying real-time TWR and Velocity scores.
* **`Feed.jsx`**: The "Trust Feed" allowing filtered viewing by Inner Circle / Public tiers.
* **`PostComposer.jsx`**: Input mechanism with Trust Tier selection.
* **`TaskDashboard.jsx`**: Execution interface to create/complete tasks and drive velocity metrics.

### 🧬 Systemic Synthesis
* **The Loop is Closed:** Work (Tasks) $\to$ Velocity (Metrics) $\to$ Identity (Profile) $\to$ Memory (Bridge).
* **Memory Scribe Activated:** Every social post is now auto-logged to the symbolic `bridge.py` for long-term AI recall.
* **Legacy Repair:** Fixed Rust/Python import conflicts and updated OpenAI API syntax to v1.0+.

### ⚙️ Developer Notes
* **Requires MongoDB:** Ensure `mongod` is running locally or `MONGO_URL` is set in `.env`.
* **Launch:** Run `uvicorn main:app --reload` (Backend) and `npm run dev` (Frontend).


# 🧠 A.I.N.D.Y. v0.9 — Research Engine Integration Build  
**Date:** October 21, 2025  
**Branch:** `main` (merged from `feature/research-engine`)  
**Status:** ✅ Pre-Release | System Integration Complete  

---

## 🔧 Summary  
This update marks the official merge of the **Research Engine** and **Memory Bridge v0.1** into the main A.I.N.D.Y. architecture.  
It transforms A.I.N.D.Y. from a modular backend into a unified **AI-Native orchestration layer** — bridging metrics, symbolic memory, and service logic.

---

## 🚀 New Modules & Integrations
- **`research_results_service.py`** — AI-native research module with symbolic logging to the Memory Bridge  
- **`bridge.py`** — upgraded to **Memory Bridge v0.1** (Solon Protocol logic, continuity anchoring)  
- **`freelance_service.py`**, **`leadgen_service.py`**, **`deepseek_arm_service.py`** — added as new autonomous functional agents  
- **`main.py`** — unified all routers, added caching, threading, and middleware  
- **`models.py`** — expanded SQLAlchemy schema to include performance metrics, business formulas, and research result tracking  

---

## 🧩 Structural Changes
- Reorganized **database layer** → `db/models/` with centralized Base imports  
- Removed deprecated Alembic files and legacy `services/*` and `models/*` structures  
- Introduced **modules/** directory for scalable extensions  
- Added **tests/** folder for integration and performance testing  
- Refined FastAPI startup events with threaded background tasks (`check_reminders`, `handle_recurrence`)  

---

## 🧬 Symbolic & Systemic Additions
- Embedded **Solon Continuity Layer** for symbolic recall  
- Introduced **MemoryTrace()** runtime linkage for insight propagation  
- Added tags and trace logic for recursive knowledge graph formation  
- Marked start of **Bridge-to-Rust integration** for performance persistence  

---

## ⚙️ Developer Notes
Run local verification:
```bash
uvicorn main:app --reload


Visit http://127.0.0.1:8000

Expected response:

{"message": "A.I.N.D.Y. API is running!"}

Version Roadmap
Milestone	Focus	Status
v0.8	Core DB + Router Sync	✅ Completed
v0.9	Research Engine + Memory Bridge	✅ Merged
v1.0	Rust Bridge + Frontend React Integration	🧠 In Progress
v1.1	AI-Search Optimized API Docs + Knowledge Graph Indexing  🔜 Upcoming

A.I.N.D.Y. Ecosystem Notes

Core Logic: Infinity Algorithm • Symbolic Continuity • Agentic Yield Architecture
Lead Architect: Shawn Knight — Masterplan Infinite Weave
Tagline: “Quicker, Better, Faster, Smarter.”

