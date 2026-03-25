## [Unreleased] — feat/infinity-algorithm-loop

### Added (2026-03-24 - Sprint N+3 "Infinity Algorithm Loop")

**Infinity Algorithm Event-Driven Loop — execution scoring engine**

Closes INFINITY_ALGORITHM.md §Phase v4 (unified loop) and
INFINITY_ALGORITHM_SUPPORT_SYSTEM.md §Phase v3 (watcher signals fed into scoring).

**Score storage (db/models/user_score.py + migration):**
- `user_scores` table: latest cached score per user (upserted on recalculation)
- `score_history` table: append-only time series of all score snapshots
- `KPI_WEIGHTS` dict: hard-invariant (asserts sum == 1.0 at import time)
- 5 KPI component scores (0-100) + master score (0-100)
- confidence: "high" / "medium" / "low" based on data density

**KPI calculators (services/infinity_service.py):**
- `calculate_execution_speed`: task velocity vs 14-day historical baseline (sigmoid scoring)
- `calculate_decision_efficiency`: task completion rate + ARM analysis quality trend
- `calculate_ai_productivity_boost`: ARM usage frequency + code quality improvement trend
- `calculate_focus_quality`: watcher session duration, distraction ratio, focus achievement rate (returns neutral 50.0 until user_id added to watcher_signals)
- `calculate_masterplan_progress`: task completion % + days ahead/behind target
- `calculate_infinity_score`: weighted KPI average (0.25+0.25+0.20+0.15+0.15=1.0); never raises; returns None on failure

**Event triggers (fire-and-forget, wrapped in try/except):**
- Task completion → score recalculation (task_services.py complete_task)
- Watcher session_ended → score recalculation (watcher_router.py _trigger_eta_update)
- ARM analysis complete → score recalculation (deepseek_code_analyzer.py run_analysis)
- APScheduler 7am daily job → recalculate all users (scheduler_service.py)

**Social feed ranking (social_router.py):**
- New: `_compute_infinity_ranked_score()` — recency(0.4) + author_score(0.4) + trust(0.2)
- get_feed() batch-loads author UserScore from PostgreSQL, incorporates into ranking
- Fallback: author_score defaults to 50.0 if no score exists

**Score API (routes/score_router.py):**
- GET /scores/me — latest score + 5 KPI breakdown + weights + metadata
- POST /scores/me/recalculate — force refresh
- GET /scores/me/history — time series (reverse chronological)

**Dashboard UI:**
- `InfinityScorePanel` component: SVG score ring (color-coded 0-40 red / 40-70 yellow / 70-100 green), 5 KPI cards with progress bars + weight labels, history sparkline
- `ScoreRing` SVG component with animated stroke-dasharray
- api.js: `getMyScore`, `recalculateScore`, `getScoreHistory`

**Tests (tests/test_infinity_algorithm.py):**
- 55 new tests: models, KPI helpers, calculators, master score formula, event triggers, social ranking, API endpoints, frontend presence

**TECH DEBT CLOSED:**
- INFINITY_ALGORITHM.md §Phase v4: unified execution loop
- INFINITY_ALGORITHM_SUPPORT_SYSTEM.md §Phase v3: watcher signals → scoring

---

## [Unreleased] — feat/watcher-agent

### Added (2026-03-24 - Sprint N+2 "The Watcher")

**A.I.N.D.Y. Watcher — OS-level attention monitoring agent**

Closes the observation gap in the Infinity Algorithm Support System (INFINITY_ALGORITHM_SUPPORT_SYSTEM.md §3.2).
Implements Phase v2 of the Support System evolution plan.

**watcher/ — standalone process:**
- `watcher/window_detector.py` — cross-platform active window detection; Windows (ctypes), macOS (AppKit+Quartz), Linux (xdotool), psutil fallback; never raises
- `watcher/classifier.py` — `ActivityType` enum (WORK/COMMUNICATION/DISTRACTION/IDLE/UNKNOWN); pattern-matching on 60+ process names and window title regexes; `ClassificationResult` dataclass with confidence + matched_rule
- `watcher/session_tracker.py` — `SessionState` machine (IDLE→CONFIRMING_WORK→WORKING→DISTRACTED→RECOVERING); emits `SessionEvent` objects: session_started, session_ended, distraction_detected, focus_achieved, context_switch, heartbeat; pure state machine, no external calls
- `watcher/signal_emitter.py` — thread-safe deque queue, background flush thread, batched HTTP POST, 3-attempt exponential backoff, DRY_RUN mode, overflow protection
- `watcher/config.py` — env-var configurable (`AINDY_WATCHER_*`); `load()` + `validate()` with clear error messages
- `watcher/watcher.py` — main loop entry point; argparse CLI (--dry-run, --poll-interval, --log-level); SIGINT/SIGTERM graceful shutdown; drain flush on exit
- `watcher/requirements_watcher.txt` — httpx, psutil, python-dotenv; platform-specific optionals documented
- `watcher/README.md` — setup, configuration reference, signal taxonomy, session state machine diagram, API docs

**Backend receiver:**
- `db/models/watcher_signal.py` — `WatcherSignal` ORM model; 5 indexes; `signal_metadata` JSONB column (renamed from metadata — SQLAlchemy reserved word)
- `alembic/versions/d7e6f5a4b3c2_watcher_signals_table.py` — Alembic migration (down_revision: c6e5d4f3b2a1); creates watcher_signals with full index set
- `routes/watcher_router.py` — `POST /watcher/signals` (batch receive, validation, persistence) + `GET /watcher/signals` (filter by session_id/signal_type, paginated); API key auth; `_trigger_eta_update` on session_ended (non-fatal)
- `routes/__init__.py` — registered watcher_router

**Signal types:** session_started | session_ended | distraction_detected | focus_achieved | context_switch | heartbeat
**Activity types:** work | communication | distraction | idle | unknown

**Tests:**
- `tests/test_watcher.py` — 65 new tests: classifier (17 tests), session_tracker (18 tests), watcher_router POST/GET/auth (19 tests), config (7 tests), signal_emitter (5 tests), window_detector (4 tests)
- `watcher_mock_db` fixture — reload-safe DI override using sys.modules["routes.watcher_router"].get_db pattern
- `.coveragerc` — omitted `watcher/watcher.py` (process entry-point, equivalent to CLI scripts)

---

## [Unreleased] — feat/sprint-n1-anchor-close

### Added (2026-03-23 - Sprint N+1 "Anchor and Close")

**FIX 1 — SECRET_KEY startup hardening (§15.8)**
- `config.py` — `warn_insecure_secret_key` validator warns when placeholder default is used
- `main.py` lifespan — raises `RuntimeError` if `SECRET_KEY` is placeholder in production; logs warning in dev/test

**FIX 2 — Dual DAO consolidation (§15.5)**
- `db/dao/memory_node_dao.py` — added `load_memory_node()` (alias for `get_by_id()`) and `find_by_tags()` (alias for `get_by_tags()`) for API compatibility
- `routes/bridge_router.py` — updated import from legacy `services.memory_persistence.MemoryNodeDAO` → canonical `db.dao.memory_node_dao.MemoryNodeDAO`

**FIX 3 — MemoryNode.children silent trace loss (§10.1)**
- `db/dao/memory_node_dao.py` `save()` — after persisting the node, reads `extra["children"]` and creates `MemoryLink` rows for each valid child UUID, so child references are no longer silently discarded

**FIX 4 — Lint violations**
- `ruff.toml` — excluded `Nodus Runner.py` and `Single File Engine.py` (untracked prototype files with invalid syntax/markdown fences); all ruff checks now pass clean

**STEP 5 — MasterPlan anchor + ETA migration**
- `db/models/masterplan.py` — added 9 new columns: `anchor_date`, `goal_value`, `goal_unit`, `goal_description`, `projected_completion_date`, `current_velocity`, `days_ahead_behind`, `eta_last_calculated`, `eta_confidence`
- `alembic/versions/c6e5d4f3b2a1_masterplan_anchor_eta_v1.py` — Alembic migration (additive, all nullable)

**STEP 6 — Anchor endpoint**
- `routes/masterplan_router.py` — `PUT /masterplans/{id}/anchor` with `AnchorRequest` (anchor_date, goal_value, goal_unit, goal_description); partial updates supported

**STEP 7 — ETA projection service + scheduler job**
- `services/eta_service.py` — `calculate_eta()` (velocity = tasks/14d rolling, projects completion, computes days_ahead_behind, writes to plan), `recalculate_all_etas()` (batch for all anchored plans)
- `routes/masterplan_router.py` — `GET /masterplans/{id}/projection` endpoint
- `services/task_services.py` `complete_task()` — ETA recalculation hook (fire-and-forget) when active plan has anchor_date
- `services/scheduler_service.py` — daily 6am `daily_eta_recalculation` APScheduler job

**STEP 8 — MasterPlanDashboard UI**
- `client/src/api.js` — `setMasterplanAnchor()`, `getMasterplanProjection()`
- `client/src/components/MasterPlanDashboard.jsx` — `ETAProjectionPanel` (velocity, ETA, days ahead/behind, confidence) + `AnchorModal` (set anchor_date, goal_value, goal_unit, goal_description)

**Tests**
- `tests/test_sprint_n1_anchor_close.py` — 42 new tests: SECRET_KEY hardening, dual DAO consolidation, children persistence, anchor columns, anchor endpoint, ETA service, projection endpoint, scheduler job, complete_task hook

---

## [Unreleased] — feat/flow-engine-console-ui

### Added (2026-03-23 - Flow Engine Console UI)

**Flow Engine Console — execution backbone made visible**

- `client/src/components/FlowEngineConsole.jsx` — 4-tab console in Dashboard:
  - **Flow Runs**: all workflow executions with status badges, filter by status + workflow type, summary bar (counts by status), inline run detail with node history timeline, state snapshot, timing per node, WAIT/RESUME controls with confirmation dialog
  - **Automation Logs**: Phase A scheduler execution log, APScheduler status + registered jobs, per-log detail (task name, attempts, duration, error), replay failed tasks with confirmation, "Replay all failed" batch action
  - **Registry**: all registered flows as visual node chains (CSS-only), all registered nodes as pills, click node to see which flows use it
  - **Strategies**: learned flow scores (0.0 → 2.0 bar), usage count + success rate per strategy, system vs user-specific strategies, informative empty state for new installations
- `client/src/api.js` — 9 new API functions: `getFlowRuns`, `getFlowRun`, `getFlowRunHistory`, `resumeFlowRun`, `getFlowRegistry`, `getAutomationLogs`, `getAutomationLog`, `replayAutomationLog`, `getSchedulerStatus`
- `client/src/components/Dashboard.jsx` — tabbed: Overview (existing, unchanged) + Execution (new FlowEngineConsole)
- `tests/test_flow_console_ui.py` — 19 backend endpoint tests covering auth protection, response shapes, and component/API existence

**Design**: manual refresh only (no polling), confirmation dialogs for RESUME + Replay, consistent status colors across all panels, full loading/data/error/empty states per panel.

---

## [Unreleased] — feature/memory-bridge-v4

### Added (2026-03-23 - Flow Engine Phase C + D)

**Phase C — Genesis → executable flow with WAIT states**

- `services/flow_definitions.py` — 3 new genesis nodes:
  - `genesis_validate_session`: validates session_id in state before tracking
  - `genesis_record_exchange`: WAIT/RESUME tracking node; no LLM call — router
    handles that; returns WAIT when synthesis not ready, SUCCESS when ready
  - `genesis_store_synthesis`: writes synthesis completion to Memory Bridge
    (non-fatal, returns SUCCESS even on exception)
- `services/flow_definitions.py` — `genesis_conversation` flow registered at startup:
  - `genesis_validate_session → genesis_record_exchange → genesis_store_synthesis`
  - Conditional edge: advances to `genesis_store_synthesis` when `synthesis_ready=True`
  - WAIT/RESUME: pauses at `genesis_record_exchange` between user messages; resumes
    via `route_event("genesis_user_message", ...)` on next message
- `routes/genesis_router.py` — fire-and-forget Phase C block in `genesis_message()`:
  - First message: starts a `genesis_conversation` FlowRun, stores `_genesis_flow_run_id`
    in `session.summarized_state`
  - Subsequent messages: routes `genesis_user_message` event to resume waiting run
  - Entire block is non-fatal (wrapped in `try/except`) — existing behaviour unchanged
- `tests/test_flow_engine_phase_c_d.py` — 38 tests covering Phase C + D

**Phase D — FlowHistory → Memory Bridge**

- `services/flow_engine.py` — `PersistentFlowRunner._capture_flow_completion()`:
  - Called automatically when a flow run reaches SUCCESS
  - Queries `FlowHistory` for the run, builds an execution pattern summary
    (node names, timing, success rate)
  - Writes summary to Memory Bridge via `MemoryCaptureEngine`
  - Maps `workflow_type` to significance event type:
    `arm_analysis` → `arm_analysis_complete`, `task_completion` → `task_completed`,
    `leadgen_search` → `leadgen_search`, `genesis_conversation` → `genesis_synthesized`,
    unknown → `flow_completion`
  - Skipped when `user_id` or `workflow_type` is `None` (system flows)
  - Non-fatal: storage failures do not crash the run
- `services/memory_capture_engine.py` — `"flow_completion": 0.5` added to
  `EVENT_SIGNIFICANCE` for unknown workflow type fallback

**Tech Debt Closed:**
- §15.19 Flow Engine Phase C: Genesis → executable flow with WAIT states
- §15.20 Flow Engine Phase D: FlowHistory → Memory Bridge

**Tests:** 790 passing, 0 failing, 69.22% coverage (was 752 / 69.16%)

---

## [Unreleased] — feature/flow-engine-phase-b

### Added (2026-03-22 - Flow Engine Phase B: PersistentFlowRunner Execution Backbone)

- `services/flow_engine.py` — clean rewrite of Single File Engine prototype architecture:
  - `PersistentFlowRunner`: stateful flow execution with DB checkpointing after each node
  - `NODE_REGISTRY` + `@register_node` decorator: global node function registry
  - `FLOW_REGISTRY` + `register_flow()`: named flow graph registry
  - `execute_node`: policy enforcement + attempt tracking + execution timing
  - `resolve_next_node`: simple and conditional edge resolution
  - `route_event`: WAIT/RESUME — resume waiting flow runs on external event arrival
  - `record_outcome`: EventOutcome DB writes for strategy learning
  - `select_strategy` / `update_strategy_score`: adaptive flow selection (score: min 0.1, max 2.0)
  - `execute_intent`: top-level entry point — intent → strategy or generated plan → flow → runner
- `services/flow_definitions.py` — A.I.N.D.Y. workflow flow graphs:
  - ARM analysis flow: `arm_validate_input → arm_analyze_code → arm_store_result`
  - Task completion flow: `task_validate → task_complete → task_store_outcome`
  - LeadGen search flow: `leadgen_validate → leadgen_search → leadgen_store`
  - `register_all_flows()` called at startup from `main.py` lifespan
- `db/models/flow_run.py` — 4 new SQLAlchemy ORM models: `FlowRun`, `FlowHistory`, `EventOutcome`, `Strategy`
- `alembic/versions/b5d4e3f2c1a0_flow_engine_phase_b_tables.py` — migration: `flow_runs`, `flow_history`, `event_outcomes`, `strategies` tables
- `routes/flow_router.py` — 5 new endpoints:
  - `GET /flows/runs` — list flow runs for current user (filterable by status, workflow_type)
  - `GET /flows/runs/{run_id}` — run detail with full state
  - `GET /flows/runs/{run_id}/history` — per-node execution audit trail
  - `POST /flows/runs/{run_id}/resume` — resume a WAIT-state run with an event payload
  - `GET /flows/registry` — inspect registered flows and nodes
- `tests/test_flow_engine_phase_b.py` — 62 new tests across 7 test classes

### Changed (2026-03-22 - Flow Engine Phase B)

- `runtime/execution_loop.py` — added `PersistentFlowRunner`, `execute_intent`, `register_node`, `register_flow`, `route_event` re-exports from `services/flow_engine`. Existing `ExecutionLoop` class preserved.
- `runtime/execution_registry.py` — added `NODE_REGISTRY`, `FLOW_REGISTRY`, `register_node`, `register_flow` re-exports from `services/flow_engine`. Existing `REGISTRY` singleton preserved.
- `db/models/__init__.py` — exports `FlowRun`, `FlowHistory`, `EventOutcome`, `Strategy`
- `routes/__init__.py` — registers `flow_router`
- `main.py` — calls `register_all_flows()` at startup lifespan

### Tech Debt Closed

- §15.18: Single File Engine integration — implemented as `services/flow_engine.py`
- §15.6: Runtime execution loop 0% coverage — flow_engine.py is fully tested; runtime files re-export for compat
- §11.6: ARM config process-local — FlowRun persists workflow execution state to DB per checkpoint

### Test Count: 752 passing, 0 failing | Coverage: 69.16%

---

## [Unreleased] ? feature/cpp-semantic-engine

### Added (2026-03-20 - Security Sprint)
- `alembic/versions/c1f2a9d0b7e4_add_user_id_to_calculation_results.py` - migration: adds `user_id` column + index on `calculation_results`.
- `tests/test_security_sprint2.py` - security regression tests for user scoping and ownership checks.

### Changed (2026-03-20 - Security Sprint)
- `routes/memory_router.py` - user-scoped tag search/link traversal and link ownership verification.
- `db/dao/memory_node_dao.py` - `get_by_tags()` now accepts `user_id` for scoping.
- `routes/bridge_router.py` - bridge node creation uses `MemoryCaptureEngine` and supports `user_id` + `source_agent`.
- `routes/analytics_router.py` - manual LinkedIn ingest now verifies MasterPlan ownership.
- `routes/main_router.py` - `/results` and `/masterplans` filtered by `user_id`; `/create_masterplan` sets `user_id`.
- `db/models/calculation.py` + `services/calculation_services.py` - calculations now store `user_id`.
- `routes/social_router.py` - profile upsert scoped by `user_id`.
- `routes/health_router.py` - fixed imports for `seo_services` and `memory_persistence`.
- `client/src/api.js` - added auth-wired helpers for dashboard, analytics, metrics, SEO, and freelance endpoints.
- `client/src/components/*` - replaced raw `fetch()`/`axios` with `authRequest()` helpers; updated AnalyticsPanel and LeadGen response mapping; removed stray Dashboard JSX.

### Added (2026-03-19 - Memory Bridge v5 Phase 3: Multi-Agent Memory)
- `alembic/versions/a2ec23964f2c_multi_agent_memory_v5_phase3.py` - migration: `agents` table; `source_agent` + `is_shared` on `memory_nodes`; seeds system agents.
- `db/models/agent.py` - Agent registry model and namespace constants.
- `db/dao/memory_node_dao.py` - federated DAO methods: `save_as_agent()`, `recall_from_agent()`, `recall_federated()`, `share_memory()`.
- `routes/memory_router.py` - federated endpoints:
  - `POST /memory/federated/recall`
  - `GET /memory/agents`
  - `GET /memory/agents/{namespace}/recall`
  - `POST /memory/nodes/{node_id}/share`
- `bridge/nodus_memory_bridge.py` - federation helpers: `recall_from`, `recall_all_agents`, `share`.
- `tests/test_memory_bridge_v5_phase3.py` - phase 3 test suite.
- `tests/validate_memory_v5_phase3.py` - live validation script.

### Changed (2026-03-19 - Memory Bridge v5 Phase 3)
- `services/memory_capture_engine.py` now tags nodes with `source_agent` and `is_shared` (ARM/Genesis auto-share).
- ARM, Genesis, LeadGen, Task workflows now pass `agent_namespace` to `MemoryCaptureEngine`.
- Genesis synthesis and conversation calls now query ARM shared insights before LLM calls.
- Nodus runtime built-ins extended: `recall_from`, `recall_all`, `share`.

### Added (2026-03-18 - Memory Bridge v5 Phase 1: Memory-Native Execution)
- `services/memory_capture_engine.py` — centralized capture engine (significance scoring, dedup, auto-tagging, auto-linking).
- `bridge/nodus_memory_bridge.py` — Nodus runtime bridge (recall/remember/suggest/record_outcome).
- `routes/memory_router.py` — v5 endpoints:
  - `POST /memory/execute`
  - `POST /memory/execute/complete`
  - `POST /memory/nodus/execute`
- `tests/test_memory_bridge_v5.py` — v5 test suite (capture engine, Nodus bridge, execution loop).
- `tests/validate_memory_v5.py` — live validation script.

### Changed (2026-03-18 - Memory Bridge v5 Phase 1)
- ARM analysis/codegen, task completion, genesis conversation, leadgen search now route memory writes through the capture engine.
- Genesis lock/activate memory writes upgraded to capture engine with `force=True`.

### Added (2026-03-18 ? Memory Bridge v4: Adaptive Intelligence)
- `alembic/versions/5b14b05e179f_memory_bridge_v4_feedback_columns.py` ? Migration: feedback columns on `memory_nodes` (`success_count`, `failure_count`, `usage_count`, `last_used_at`, `last_outcome`, `weight`).
- `services/memory_persistence.py` ? `MemoryNodeModel` now stores feedback counters and adaptive weight fields used by v4 scoring.
- `db/dao/memory_node_dao.py` ? feedback methods: `record_feedback()`, `get_success_rate()`, `get_usage_frequency_score()`, `get_graph_connectivity_score()`.
- `db/dao/memory_node_dao.py` ? Resonance v2 scoring (semantic, graph, recency, success rate, usage frequency) with adaptive weight multiplier and tag bonus.
- `routes/memory_router.py` ? v4 endpoints:
  - `POST /memory/nodes/{node_id}/feedback`
  - `GET /memory/nodes/{node_id}/performance`
  - `POST /memory/suggest`
- `db/dao/memory_node_dao.py::suggest()` ? suggestion engine returning actionable recommendations from high-performing memories.
- `bridge/__init__.py` ? `suggest_from_memory()` export for workflow hooks.
- `modules/deepseek/deepseek_code_analyzer.py` ? ARM auto-feedback on recalled memories based on analysis scores.
- `services/task_services.py` ? task completion auto-feedback on related decision memories.
- `tests/test_memory_bridge_v4.py` ? v4 test suite (feedback, resonance v2, suggestions, endpoints, bridge export).
- `tests/validate_memory_v4.py` ? live validation script for v4 success condition.
 ### Added (2026-03-18 - Memory Bridge v3: Structured Continuity) - `alembic/versions/dc59c589ab1e_memory_bridge_v3_history_table.py` - Migration: `memory_node_history` table (append-only change log) + index on (`node_id`, `changed_at`). - `alembic/versions/edc8c8d84cbb_repair_memory_nodes_tsv_trigger_drift.py` - Repair migration: removes stale `content_tsv` trigger/function/index drift from `memory_nodes` on upgraded databases. - `db/models/memory_node_history.py` - ORM model for history snapshots (previous values only). - `db/dao/memory_node_dao.py::update()` ??? explicit node updates now record prior state in history; optional embedding regeneration on content change. - `db/dao/memory_node_dao.py::get_history()` ??? returns history entries (reverse chronological). - `db/dao/memory_node_dao.py::traverse()` ??? DFS multi-hop traversal with cycle prevention + narrative summary. - `db/dao/memory_node_dao.py::expand()` ??? related node expansion (linked + semantic neighbors). - `db/dao/memory_node_dao.py::recall(expand_results=True)` ??? optional expanded context return. - `routes/memory_router.py` ??? v3 endpoints:   - `PUT /memory/nodes/{node_id}`   - `GET /memory/nodes/{node_id}/history`   - `GET /memory/nodes/{node_id}/traverse`   - `POST /memory/nodes/expand`   - `POST /memory/recall/v3` - `tests/test_memory_bridge_v3.py` ??? v3 unit + route coverage (history, traversal, expansion, recall v3). - `tests/validate_memory_v3.py` ??? live validation script for v3 success condition.  ### Added (2026-03-18 ??? Memory Bridge Phase 2: Make It Intelligent) - `alembic/versions/mb2embed0001` ??? Migration: `embedding VECTOR(1536)` column on `memory_nodes`. `CREATE EXTENSION IF NOT EXISTS vector` included. Idempotent (checks column existence before adding). - `services/embedding_service.py` ??? OpenAI `text-embedding-ada-002` embedding generation (1536 dims). Zero-vector fallback on failure (never crashes). 3-attempt retry with exponential backoff. `cosine_similarity()` uses C++ kernel (`memory_bridge_rs.semantic_similarity` via `bridge/memory_bridge_rs/target/debug`) with pure Python fallback. `cosine_similarity_python()` available as standalone fallback. - `services/memory_persistence.py` ??? `VALID_NODE_TYPES = {"decision", "outcome", "insight", "relationship"}`. SQLAlchemy `before_insert`/`before_update` event listener enforces type at ORM layer. `embedding = Column(Vector(1536), nullable=True)` added to `MemoryNodeModel`. - `db/dao/memory_node_dao.py::find_similar()` ??? Semantic similarity retrieval via pgvector `<=>` cosine distance operator. Filters by `user_id`, `node_type`, `min_similarity`. Returns nodes with `similarity` and `distance` fields. NULL embeddings excluded. - `db/dao/memory_node_dao.py::recall()` ??? Resonance-scored retrieval: `score = (semantic * 0.6) + (tag_match * 0.2) + (recency * 0.2)`. Recency decay: `exp(-age_days / 30.0)`. Deduplicates across semantic + tag paths. Primary retrieval method for Phase 3 workflow hooks. - `db/dao/memory_node_dao.py::recall_by_type()` ??? Type-filtered resonance recall. Validates against `VALID_NODE_TYPES`. Calls `recall()` internally. - `db/dao/memory_node_dao.py::save()` ??? Now accepts `generate_embedding: bool = True`. Generates and stores embedding via `embedding_service` before DB insert. - `routes/memory_router.py::POST /memory/nodes/search` ??? Semantic similarity search. Accepts `query`, `limit`, `node_type`, `min_similarity`. Generates query embedding, calls `find_similar()`. - `routes/memory_router.py::POST /memory/recall` ??? Primary retrieval API. Accepts `query`, `tags`, `limit`, `node_type`. Returns resonance-ranked results with scoring metadata (`semantic_weight`, `tag_weight`, `recency_weight`). Returns 400 if neither `query` nor `tags` provided. - `routes/memory_router.py` ??? `CreateNodeRequest.node_type` upgraded from `str` to `Literal["decision", "outcome", "insight", "relationship"]`. Pydantic validates at API boundary. - `tests/test_memory_bridge_phase2.py` ??? 24 tests covering: embedding service importability, 1536-dim output, zero-vector on empty input, cosine similarity (identical/orthogonal/zero vectors), C++ kernel confirmed working, embedding failure fallback, ORM column presence, DB column presence, resonance formula weights, recency decay, tag score calculation, type enforcement (VALID_NODE_TYPES, Literal schema), all 4 new route behaviors (auth required, 400 on missing params, recall with query, search with auth).  ### Changed (2026-03-18 ??? Memory Bridge Phase 2) - `tests/test_models.py::test_memory_node_has_no_embedding_column` renamed to `test_memory_node_has_embedding_column`; assertion inverted. Previously a diagnostic test tracking a known gap; now a regression guard confirming the column exists.  ### Added (2026-03-17 ??? ARM Phase 1) - `modules/deepseek/security_deepseek.py` ??? `SecurityValidator` fully implemented.   Replaces stub. Raises `HTTPException` (FastAPI-native). Validation layers: path   traversal blocking (BLOCKED_PATH_SEGMENTS), extension allowlist, regex-based   sensitive content detection (OpenAI sk- keys, AWS AKIA keys, PEM private key   blocks, generic `api_key=...` assignments, `.env` references), configurable size   limit. Previously: basic keyword scan with `PermissionError`. - `modules/deepseek/config_manager_deepseek.py` ??? `ConfigManager` fully implemented.   16-key `DEFAULT_CONFIG` (model, temperatures, token limits, retry settings,   Infinity Algorithm defaults). Runtime updates via `update(dict)` with key   allowlist (unknown keys silently dropped). `_persist()` writes to   `deepseek_config.json`. `calculate_task_priority()` implements Infinity Algorithm   `TP = (Complexity ?? Urgency) / Resource Cost` with zero-division guard.   Previously: 3-key minimal implementation. - `modules/deepseek/file_processor_deepseek.py` ??? `FileProcessor` fully implemented.   Line-boundary chunking (`chunk_content()`), UUID v4 session IDs   (`create_session_id()`), structured session log dicts with Infinity Algorithm   Execution Speed metric (tokens/second). Previously: activity log writer only. - `modules/deepseek/deepseek_code_analyzer.py` ??? `DeepSeekCodeAnalyzer` fully   implemented with OpenAI GPT-4o integration. `_call_openai()` uses   `response_format={"type": "json_object"}`, configurable retry with delay,   returns (text, input_tokens, output_tokens). `run_analysis()` full pipeline:   security validation ??? chunking ??? prompt construction ??? GPT-4o ??? DB persist   (`AnalysisResult`) ??? enriched result. `generate_code()` same pipeline for code   generation (`CodeGeneration` DB record). Both persist failure records on error.   Previously: keyword-counting stub returning summary string + template code. - `db/models/arm_models.py` ??? `AnalysisResult` and `CodeGeneration` SQLAlchemy   models added (UUID PKs, PostgreSQL dialect). `AnalysisResult`: session_id,   user_id, file_path, file_type, analysis_type, prompt_used, model_used,   input_tokens, output_tokens, execution_seconds, result_summary, result_full,   task_priority, status, error_message, created_at. `CodeGeneration`: links to   `AnalysisResult` via FK, generation_type, original_code, generated_code,   language, quality_notes. Existing `ARMRun`, `ARMLog`, `ARMConfig` models retained. - `routes/arm_router.py` ??? fully rewritten. Uses `DeepSeekCodeAnalyzer` directly   (bypasses `deepseek_arm_service.py`). Singleton analyzer with config-reset on   PUT /arm/config. New request schemas: `AnalyzeRequest` (file_path, complexity,   urgency, context), `GenerateRequest` (prompt, original_code, language,   generation_type, analysis_id), `ConfigUpdateRequest` (updates dict).   GET /arm/logs returns `{analyses, generations, summary}` with Infinity metrics. - `tests/test_arm.py` ??? 46 ARM-specific tests: `TestSecurityValidator` (16),   `TestConfigManager` (10), `TestFileProcessor` (8), `TestARMRoutes` (12).   OpenAI calls mocked; no real API calls. All 46 pass. - Frontend ARM components updated to match new API contracts:   `ARMAnalyze.jsx` ??? structured display with score badges, severity-tagged findings,   Infinity metrics row. `ARMGenerate.jsx` ??? prompt-based interface with language   selector, optional existing code, explanation + quality notes.   `ARMLogs.jsx` ??? aligned to `{analyses, generations, summary}` response shape with   metrics pills. `ARMConfig.jsx` + `api.js` ??? signatures updated to match new   endpoint contracts. - Total test suite: **208 passing, 0 failing** (up from 162).  ### Added (2026-03-17 ??? Genesis Blocks 1-3) - **Alembic migration** `a1b2c3d4e5f6_genesis_block1_missing_columns` ??? additive columns:   - `genesis_sessions`: `synthesis_ready` (Boolean, default false), `draft_json` (JSON),     `locked_at` (DateTime), `user_id_str` (String UUID)   - `master_plans`: `user_id` (String UUID), `status` (String, default "draft") - `db/models/masterplan.py` ??? `MasterPlan` gains `user_id` + `status`; `GenesisSessionDB`   gains `synthesis_ready`, `draft_json`, `locked_at`, `user_id_str`. - `services/masterplan_factory.py` ??? accepts `user_id` param; version count scoped per-user;   sets `masterplan.status = "locked"` and `session.locked_at` on lock. - `services/posture.py` ??? real posture detection replacing stub. Returns one of   `Stable | Accelerated | Aggressive | Reduced` based on `time_horizon_years` and   `ambition_score` from synthesis draft. Adds `posture_description()` helper. - `services/genesis_ai.py` ??? `call_genesis_synthesis_llm()` replaced stub with real   GPT-4o call using `response_format={"type": "json_object"}` and `SYNTHESIS_SYSTEM_PROMPT`.   Produces structured draft: vision, horizon, mechanism, ambition_score, phases, domains,   success_criteria, risk_factors. Fail-safe fallback on parse error. - `routes/genesis_router.py` ??? full rewrite with user isolation:   - All session queries scoped to `user_id_str` (from JWT `sub`)   - `POST /genesis/session` ??? binds `user_id_str`   - `POST /genesis/message` ??? persists `synthesis_ready` to DB as one-way flag   - `GET /genesis/session/{id}` ??? new endpoint (Block 2)   - `GET /genesis/draft/{id}` ??? new endpoint (Block 2)   - `POST /genesis/synthesize` ??? gated on `synthesis_ready`, persists `draft_json`   - `POST /genesis/lock` ??? passes `user_id` to factory   - `POST /genesis/{plan_id}/activate` ??? scoped to current user, sets `status = "active"` - `routes/masterplan_router.py` ??? new router (prefix `/masterplans`), JWT auth:   - `POST /masterplans/{id}/lock`, `GET /masterplans/`, `GET /masterplans/{id}`,     `POST /masterplans/{id}/activate` - `routes/__init__.py` ??? `masterplan_router` registered. - Frontend: `client/src/components/Genesis.jsx` ??? auth-wired rewrite using `api.js`   functions (no raw fetch). Synthesis-ready banner, draft preview with LOCK PLAN button,   locked confirmation panel. Phase 2/3 UI fully implemented. - Frontend: `client/src/components/GenesisDraftPreview.jsx` ??? new Phase 3 editable preview   component. Shows vision, horizon, mechanism, ambition score, phases, domains,   success criteria, risk factors. - Frontend: `client/src/components/MasterPlanDashboard.jsx` ??? rewritten to use   authenticated `listMasterPlans()` / `activateMasterPlan()` from `api.js`. Status badges:   ACTIVE (green) / LOCKED (yellow) / DRAFT (grey) / ARCHIVED (muted). Activate button on   locked plans. - `client/src/api.js` ??? `authRequest` helper (reads Bearer token from localStorage);   10 new functions: `startGenesisSession`, `sendGenesisMessage`, `getGenesisSession`,   `synthesizeGenesisDraft`, `getGenesisDraft`, `lockMasterPlan`, `listMasterPlans`,   `getMasterPlan`, `activateMasterPlan`. - Tests: 22 new tests in `tests/test_routes_genesis.py`:   - `TestGenesisBlock1` (10 tests): model column presence, factory signature, masterplan_router registration/auth   - `TestGenesisBlock2` (5 tests): new route registration, auth guards, one-way flag guard   - `TestGenesisBlock3` (7 tests): real LLM assertion, synthesis gate, posture logic, posture_description helper - Total test suite: **246 passing, 0 failing** (up from 224).  ### Added (2026-03-17 ??? ARM Phase 2) - `services/arm_metrics_service.py` ??? `ARMMetricsService` calculates all five   Infinity Algorithm Thinking KPI metrics from `analysis_results` and   `code_generations` DB history: Execution Speed (tokens/sec), Decision Efficiency   (% success), AI Productivity Boost (output/input token ratio), Lost Potential   (% wasted tokens on failed sessions), Learning Efficiency (speed trend first-half   vs second-half). Handles empty history without crashing. - `services/arm_metrics_service.py` ??? `ARMConfigSuggestionEngine` analyzes metrics   against 5 configurable thresholds and produces prioritized, risk-labelled config   suggestions. Categorises as auto_apply_safe (low-risk) or requires_approval   (medium/high). Returns `combined_suggested_config` for one-shot apply.   Suggestions are advisory only ??? never auto-applies. - `routes/arm_router.py` ??? two new endpoints:   - `GET /arm/metrics?window=30` ??? full Thinking KPI report   - `GET /arm/config/suggest?window=30` ??? config suggestions with metrics snapshot - Frontend: `client/src/components/ARMMetrics.jsx` ??? 5-card KPI dashboard with   window selector (7/30/90 days), colour-coded efficiency/waste indicators,   trend arrows for learning efficiency. - Frontend: `client/src/components/ARMConfigSuggest.jsx` ??? suggestion panel grouped   by priority (critical/warning/info), per-suggestion Apply button calls   PUT /arm/config, "Apply All Low-Risk" button for batch apply. - `client/src/api.js` ??? `getARMMetrics(window)` and `getARMConfigSuggestions(window)`   added. - Tests: 16 new tests in `tests/test_arm.py`: `TestARMMetrics` (4 route-level),   `TestARMMetricsService` (7 unit), `TestARMConfigSuggestions` (4 unit). No DB   required for service unit tests. - Total test suite: **224 passing, 0 failing** (up from 208).  ### Deferred to Phase 3 (ARM) - Memory Bridge feedback loop: after each analysis/generation, persist a `MemoryNode`   via `MemoryNodeDAO` with ARM results as structured content and tags.   (Deferred: bridge design in progress.) - Auto-approve low-risk config changes without user confirmation.   Phase 2 returns auto_apply_safe list; Phase 3 will apply them automatically.  ### Deferred to Phase 2 (ARM) ??? NOW COMPLETE - ~~Self-tuning config: `ConfigManager.update()` to be called by an Infinity Algorithm   feedback loop that adjusts temperature/model based on execution speed trends.~~   **DONE (ARM Phase 2):** `ARMConfigSuggestionEngine` + GET /arm/config/suggest. - ~~Infinity metric crosswalk: Decision Efficiency and Execution Speed metric   integration into ARM response payloads.~~   **DONE (ARM Phase 2):** All 5 metrics exposed via GET /arm/metrics.  ### Added (C++ semantic engine ??? earlier in this branch) - C++ semantic similarity engine (`memory_cpp/semantic.h` +   `semantic.cpp`) providing high-performance vector math - `cosine_similarity(a, b, len)` ??? foundation for semantic   memory node search; ready for when embeddings are added   to MemoryNode - `weighted_dot_product(values, weights, len)` ??? directly   powers `calculate_engagement_score()` in the Infinity Algorithm - Rust extern "C" FFI bridge (`src/cpp_bridge.rs`) safely wrapping   C++ operations for Python consumption - `semantic_similarity()` and `weighted_dot_product()` exposed   to Python via PyO3 in `memory_bridge_rs` - Python fallback implementations in `calculation_services.py`   (app works without compiled extension) - `bridge/benchmark_similarity.py` for performance verification  ### Changed - `calculate_engagement_score()` in `calculation_services.py`   now calls C++ `weighted_dot_product` kernel (with fallback) - `Cargo.toml` updated: `cc` build-dependency added - `build.rs` added for C++ compilation configuration  ### Fixed - `memorycore.py` (misnamed Rust source) archived to   `bridge/archive/memory_bridge_core_draft.rs` - `Memorybridgerecognitiontrace.rs` (orphan file) archived   to `bridge/archive/`  ### Technical Notes - Build toolchain: MSVC VS 2022 Community (x64) via registry - Build mode: debug (release blocked by Windows AppControl   policy in `target/` directories) - Benchmark (debug, dim=1536, 10k iters): Python 2.753s vs   C++ 3.844s ??? debug FFI overhead dominates; release build   expected to show 10???50x improvement - Branch: `feature/cpp-semantic-engine` - Commits: `6a14d64` (cleanup) + `2054914` (implementation)  ---  # ???? A.I.N.D.Y. v1.0 ??? The "Anti-LinkedIn" Social Layer Build  **Date:** November 23, 2025 **Branch:** main (merged from feature/social-layer) **Status:** ??? Release | Full Stack Active  ### ???? Summary This update transforms A.I.N.D.Y. from a backend engine into a **Full-Stack Social Operating System**. We have activated the **Social Layer** (MongoDB), the **Velocity Engine** (Task-to-Profile sync), and the **Memory Scribe** (Auto-Documentation).  ### ???? New Modules & Integrations * **`social_router.py`**: New API endpoints for Profiles, Feeds, and Trust Tiers. * **`mongo_setup.py`**: Added MongoDB connection to handle flexible social data alongside SQL metrics. * **`social_models.py`**: Pydantic schemas for `SocialProfile`, `SocialPost`, and `TrustTier`. * **`task_services.py`**: Upgraded to trigger **Real-Time Profile Updates** upon task completion.  ### ???? Frontend Evolution (React Client) * **`ProfileView.jsx`**: Live "Identity Node" displaying real-time TWR and Velocity scores. * **`Feed.jsx`**: The "Trust Feed" allowing filtered viewing by Inner Circle / Public tiers. * **`PostComposer.jsx`**: Input mechanism with Trust Tier selection. * **`TaskDashboard.jsx`**: Execution interface to create/complete tasks and drive velocity metrics.  ### ???? Systemic Synthesis * **The Loop is Closed:** Work (Tasks) $\to$ Velocity (Metrics) $\to$ Identity (Profile) $\to$ Memory (Bridge). * **Memory Scribe Activated:** Every social post is now auto-logged to the symbolic `bridge.py` for long-term AI recall. * **Legacy Repair:** Fixed Rust/Python import conflicts and updated OpenAI API syntax to v1.0+.  ### ?????? Developer Notes * **Requires MongoDB:** Ensure `mongod` is running locally or `MONGO_URL` is set in `.env`. * **Launch:** Run `uvicorn main:app --reload` (Backend) and `npm run dev` (Frontend).   # ???? A.I.N.D.Y. v0.9 ??? Research Engine Integration Build   **Date:** October 21, 2025   **Branch:** `main` (merged from `feature/research-engine`)   **Status:** ??? Pre-Release | System Integration Complete    ---  ## ???? Summary   This update marks the official merge of the **Research Engine** and **Memory Bridge v0.1** into the main A.I.N.D.Y. architecture.   It transforms A.I.N.D.Y. from a modular backend into a unified **AI-Native orchestration layer** ??? bridging metrics, symbolic memory, and service logic.  ---  ## ???? New Modules & Integrations - **`research_results_service.py`** ??? AI-native research module with symbolic logging to the Memory Bridge   - **`bridge.py`** ??? upgraded to **Memory Bridge v0.1** (Solon Protocol logic, continuity anchoring)   - **`freelance_service.py`**, **`leadgen_service.py`**, **`deepseek_arm_service.py`** ??? added as new autonomous functional agents   - **`main.py`** ??? unified all routers, added caching, threading, and middleware   - **`models.py`** ??? expanded SQLAlchemy schema to include performance metrics, business formulas, and research result tracking    ---  ## ???? Structural Changes - Reorganized **database layer** ??? `db/models/` with centralized Base imports   - Removed deprecated Alembic files and legacy `services/*` and `models/*` structures   - Introduced **modules/** directory for scalable extensions   - Added **tests/** folder for integration and performance testing   - Refined FastAPI startup events with threaded background tasks (`check_reminders`, `handle_recurrence`)    ---  ## ???? Symbolic & Systemic Additions - Embedded **Solon Continuity Layer** for symbolic recall   - Introduced **MemoryTrace()** runtime linkage for insight propagation   - Added tags and trace logic for recursive knowledge graph formation   - Marked start of **Bridge-to-Rust integration** for performance persistence    ---  ## ?????? Developer Notes Run local verification: ```bash uvicorn main:app --reload   Visit http://127.0.0.1:8000  Expected response:  {"message": "A.I.N.D.Y. API is running!"}  Version Roadmap Milestone	Focus	Status v0.8	Core DB + Router Sync	??? Completed v0.9	Research Engine + Memory Bridge	??? Merged v1.0	Rust Bridge + Frontend React Integration	???? In Progress v1.1	AI-Search Optimized API Docs + Knowledge Graph Indexing  ???? Upcoming  A.I.N.D.Y. Ecosystem Notes  Core Logic: Infinity Algorithm ??? Symbolic Continuity ??? Agentic Yield Architecture Lead Architect: Shawn Knight ??? Masterplan Infinite Weave Tagline: ???Quicker, Better, Faster, Smarter.??? 
