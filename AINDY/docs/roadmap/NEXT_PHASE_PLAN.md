# A.I.N.D.Y. Next Phase Plan

Generated: 2026-03-23
Based on: docs/roadmap/*.md + docs/architecture/SYSTEM_SPEC.md + docs/architecture/DATA_MODEL_MAP.md + TECH_DEBT.md + CHANGELOG.md

---

## System State Summary

| Metric                   | Value                                         |
|--------------------------|-----------------------------------------------|
| Tests                    | **850 passing, 0 failing, 4 skipped** (42 new in Sprint N+1) |
| Coverage                 | ≥69% (threshold: 69%)                         |
| Ruff lint errors         | 0 (prototype files excluded from lint)        |
| API endpoints            | **134**                                       |
| Frontend components      | **40 JSX files**                              |
| DB tables                | ~35 (Postgres offline; derived from ORM models) |
| Flow nodes registered    | **12**                                        |
| Flows registered         | **4** (arm_analysis, task_completion, leadgen_search, genesis_conversation) |

---

## What Is Complete

Every item below is live, tested, and merged.

**Core Infrastructure**
- PostgreSQL + SQLAlchemy ORM, Alembic migrations with startup drift guard
- JWT auth + API-key auth on all routes; no unprotected endpoints
- SlowAPI rate limiting on AI-cost endpoints
- CI/CD: GitHub Actions (lint + test + coverage) on every push/PR
- APScheduler replacing daemon threads; AutomationLog + replay endpoint
- Structured JSON error responses; structured request logging; request metrics table
- DB background-task lease preventing duplicate work across instances

**Genesis + MasterPlan**
- Session → message → synthesize → lock → activate full lifecycle
- Real GPT-4o synthesis call; structured draft (vision, horizon, phases, domains)
- GenesisDraftPreview.jsx; MasterPlanDashboard.jsx with status badges
- Genesis conversation wired to Flow Engine (WAIT/RESUME across user messages)

**Autonomous Reasoning Module (ARM)**
- Full analysis + code generation pipeline (GPT-4o)
- 5 Thinking KPI metrics (Execution Speed, Decision Efficiency, AI Productivity Boost, Lost Potential, Learning Efficiency)
- Self-tuning config suggestions (advisory, risk-classified)
- ARM ↔ Memory Bridge hooks: recalls prior context before analysis; writes outcome node after

**Memory Bridge (v1–v5)**
- MemoryNode with pgvector embeddings (text-embedding-ada-002, 1536 dims)
- Resonance v2 scoring: semantic(0.40) + graph(0.15) + recency(0.15) + success_rate(0.20) + usage_freq(0.10) × adaptive weight
- Feedback loop: success/failure counters, adaptive weight, suggestion engine
- History table (append-only node snapshots); multi-hop graph traversal
- Federated agents: 5 agent namespaces, shared/private memory, federated recall
- MemoryCaptureEngine: centralized capture with significance scoring and dedup
- All 5 major workflows write to Memory Bridge (ARM, Task, Genesis, LeadGen, Freelance)
- FlowHistory → Memory Bridge bridge (Phase D)

**Flow Engine**
- PersistentFlowRunner with DB checkpointing after every node
- WAIT/RESUME for external event-driven workflows
- Adaptive strategy scoring (EventOutcome → Strategy table, score 0.1–2.0)
- 4-tab FlowEngineConsole.jsx: Flow Runs, Automation Logs, Registry, Strategies

**Identity Layer**
- Preference, behavior, and evolution tracking with LLM injection
- IdentityDashboard.jsx, AgentRegistry.jsx, MemoryBrowser.jsx

**Social Layer**
- Profiles + posts + feed (MongoDB); trust-tier weighted visibility scoring
- Social posts logged to Memory Bridge with DB session

**Search (LeadGen, Research, SEO)**
- LeadGen: GPT-4o scoring + external retrieval + Memory Orchestrator recall
- Research: live web retrieval + AI analysis + memory logging
- SEO: keyword extraction, readability, density, AI meta description

**Freelancing System**
- Order intake → delivery → feedback storage → basic revenue metrics
- Memory logging via MemoryCaptureEngine; user-scoped ownership

**RippleTrace**
- DropPoint + Ping storage; retrieval APIs (ripples, drop_points, pings, recent)
- Symbolic ripple event logging

**Security + Data Integrity**
- All routes user-scoped; UUID FKs enforced on all ownership tables
- CORS locked to explicit origins; no wildcard
- C++ semantic kernel (debug build; Python fallback active)

---

## Completion Gaps

Items that are documented in roadmap files but have no implementation.

| Item | Source Document | Section |
|------|----------------|---------|
| Masterplan anchor (goal value / target date) | MASTERPLAN_SAAS.md | Phase v1 |
| ETA projection / timeline compression output | MASTERPLAN_SAAS.md | Phase v2 |
| Dependency cascade model for tasks | MASTERPLAN_SAAS.md | Phase v3 |
| Execution automation layer (social/CRM/payments) | MASTERPLAN_SAAS.md | Phase v4 |
| Infinity Algorithm unified execution loop (`infinity_loop.py`) | INFINITY_ALGORITHM.md | Phase v4 |
| Expanded TWR model (multi-variable: quality, risk, AI lift) | INFINITY_ALGORITHM.md | Phase v2 |
| Ranking/Elo system (expected vs actual perf) | INFINITY_ALGORITHM.md | Phase v5 |
| Watcher service (focus, distraction, session tracking) | INFINITY_ALGORITHM_SUPPORT_SYSTEM.md | Phase v2 |
| Watcher signals fed into TWR/scoring | INFINITY_ALGORITHM_SUPPORT_SYSTEM.md | Phase v3 |
| User feedback capture (explicit + implicit) | INFINITY_ALGORITHM_SUPPORT_SYSTEM.md | Phase v5 |
| ~~Agentics runtime Phase 1 (agent_runtime.py — goal→plan→execute)~~ | AGENTICS.md | **DONE Sprint N+4** |
| ~~Agentics Phase 2 — dry-run preview + approval gate~~ | AGENTICS.md | **DONE Sprint N+4** |
| Agentics Phase 3 — Nodus integration (deterministic execution) | AGENTICS.md | Phase 3 |
| Agentics Phase 4 — capability/policy system | AGENTICS.md | Phase 4 |
| Agentics Phase 5 — agent_runs/agent_steps observability | AGENTICS.md | Phase 5 |
| RippleTrace Pattern Engine (ThreadWeaver v1–v3) | RIPPLETRACE.md | Completed |
| RippleTrace Graph Layer (Visibility Map + D3 UI) | RIPPLETRACE.md | Completed |
| RippleTrace Insight Engine (Proofboard + Graph tab) | RIPPLETRACE.md | Completed |
| Freelancing: AI generation pipeline for delivery | FREELANCING_SYSTEM.md | Phase v2 |
| Freelancing: execution speed + income efficiency metrics | FREELANCING_SYSTEM.md | Phase v2 |
| Freelancing: automation connectors (delivery/payment) | FREELANCING_SYSTEM.md | Phase v4 |
| Search System: unified query processing layer | SEARCH_SYSTEM.md | Phase v1 |
| Search System: SEO AI improvement suggestions (currently stubbed) | SEARCH_SYSTEM.md | Phase v1 |
| Search System: result history views (UI) | SEARCH_SYSTEM.md | Phase v5 |
| Social analytics dashboards | SOCIAL_LAYER.md | Phase v4 |
| Social feedback loop → visibility scoring | SOCIAL_LAYER.md | Phase v5 |
| Memory Engine Layer (Rust/C++ runtime scoring/traversal) | MEMORY_BRIDGE.md | Phase v5+ |
| RippleTrace frontend viewer (RippleTraceViewer.jsx) | TECH_DEBT.md | §15.16 |
| Observability frontend dashboard (ObservabilityDashboard.jsx) | TECH_DEBT.md | §15.17 |

---

## Open Tech Debt

Items still open in TECH_DEBT.md, annotated with risk level.

| § | Item | Risk |
|---|------|------|
| §15.8 | `SECRET_KEY` has hardcoded default `"dev-secret-change-in-production"` — JWT forgery if `.env` absent | **HIGH** |
| §15.5 | Dual DAO implementations for `memory_nodes` — `bridge_router.py` imports legacy path; `POST /bridge/link` breaks if swapped | **MEDIUM** |
| §10.1 | `MemoryNode.children` never persisted — recursive trace trees are silently dropped on process exit | **MEDIUM** |
| §12.3 | Embedding generation is synchronous on write path — OpenAI latency blocks every memory save | **MEDIUM** |
| §1 | ARM config updates are process-local — multi-instance deployment loses config changes | **MEDIUM** |
| §7 | Infinity Algorithm Support System is open-loop — Watcher missing, feedback not enforced | **MEDIUM** |
| §5/§1 | No distributed-safe scheduler — multi-instance APScheduler risks duplicated jobs beyond lease guard | **MEDIUM** |
| §15.16 | RippleTrace viewer has no frontend UI — signals captured but never surfaced | **LOW** |
| §15.17 | Observability dashboard has no frontend UI — request metrics and memory metrics not visible | **LOW** |
| §12.2 | `node_type="generic"` legacy rows — strict UPDATE enforcement would reject them | **LOW** |
| §10.9 | C++→Rust→PyO3 FFI chain for 2 math functions — high build friction, release build blocked by AppControl | **LOW** |
| §11.6 | ARM auto-approve low-risk config changes — still requires manual `PUT /arm/config` call | **LOW** |
| §14 | Pattern detection for recurring memory motifs — open conceptual gap in Memory Bridge | **LOW** |
| §14 | SYLVA agent reserved but inactive — namespace exists, no implementation | **LOW** |
| §14 | Embedding-based deduplication in capture engine (`_is_duplicate` is tag-only) | **LOW** |
| §15.11 | MongoDB credentials not validated at startup — silent failure if Mongo unavailable | **LOW** |
| §15.12 | Mixed cpython-311 / cpython-314 pycache — import resolution ambiguity | **LOW** |
| §4 | `print()` statements remain in some services — structured logging not fully consistent | **LOW** |
| §6 | No documented secret rotation policy | **LOW** |

---

## Leverage Matrix

Sorted by (Impact × Risk) / Effort descending.

```
┌─────────────────────────────────────────────┬────────┬────────┬──────┬────────────────────────────┬────────┐
│ Item                                        │ Impact │ Effort │ Risk │ Depends On                 │ Score  │
├─────────────────────────────────────────────┼────────┼────────┼──────┼────────────────────────────┼────────┤
│ §15.8 — Fix SECRET_KEY hardcoded default    │   2    │   1    │  4   │ None                       │  8.00  │
│ Masterplan anchor + ETA projection          │   4    │   2    │  4   │ Genesis lifecycle ✅        │  8.00  │
│ Infinity Algorithm execution loop           │   5    │   4    │  5   │ ARM ✅, Memory ✅, Tasks ✅ │  6.25  │
│ §10.1 — MemoryNode.children persist         │   3    │   2    │  3   │ Memory Bridge ✅           │  4.50  │
│ Watcher service (focus/session tracking)    │   4    │   3    │  3   │ Task system ✅             │  4.00  │
│ Agentics Phase 1 — Minimal runtime          │   5    │   4    │  3   │ Memory ✅, JWT ✅          │  3.75  │
│ Nodus integration (Agentics Phase 3)        │   5    │   5    │  3   │ Agentics Phase 1-2         │  3.00  │
│ §15.5 — Dual DAO consolidation              │   2    │   2    │  3   │ None                       │  3.00  │
│ ThreadWeaver v1–v3 (Delta + Prediction + Narrative) │   3    │   3    │  2   │ DropPoint/Ping ✅          │  2.00  │
│ Masterplan dependency cascade model         │   3    │   3    │  2   │ Masterplan anchor          │  2.00  │
│ Search System unified pipeline              │   3    │   4    │  2   │ SEO/LeadGen/Research ✅    │  1.50  │
│ Observability Dashboard UI                  │   3    │   2    │  1   │ Observability endpoints ✅ │  1.50  │
│ RippleTrace frontend viewer                 │   3    │   2    │  1   │ RippleTrace backend ✅     │  1.50  │
│ §12.3 — Async embedding generation          │   2    │   3    │  2   │ None                       │  1.33  │
│ Freelancing metrics completion              │   2    │   2    │  1   │ Orders/Feedback ✅         │  1.00  │
│ Social analytics layer                      │   2    │   2    │  1   │ Social CRUD ✅             │  1.00  │
│ ARM auto-approve low-risk config (§11.6)    │   2    │   2    │  1   │ ARM metrics ✅             │  1.00  │
│ C++ kernel release build                    │   2    │   2    │  1   │ AppControl removal         │  1.00  │
│ Memory pattern detection (§14)              │   3    │   4    │  1   │ Memory Bridge ✅           │  0.75  │
└─────────────────────────────────────────────┴────────┴────────┴──────┴────────────────────────────┴────────┘
```

Score = (Impact × Risk) / Effort. Range 1–5 per dimension.

---

## Recommended Next 3 Sprints

### ✅ Sprint N+1: "Anchor and Close" — COMPLETE (2026-03-23)

**Goal:** Give the MasterPlan a reference frame and eliminate the two highest-risk open items.

**Delivered:**
- ✅ `SECRET_KEY` hardened — startup rejection in prod, warning in dev (§15.8 closed)
- ✅ Dual DAO consolidated — `load_memory_node()` + `find_by_tags()` aliases on canonical DAO; `bridge_router.py` import updated (§15.5 closed)
- ✅ `MemoryNode.children` persistence — `save()` creates MemoryLink rows from `extra["children"]` (§10.1 closed)
- ✅ Ruff clean — prototype files excluded; 0 lint errors
- ✅ MasterPlan anchor columns — `anchor_date`, `goal_value`, `goal_unit`, `goal_description` + migration `c6e5d4f3b2a1`
- ✅ ETA projection — `services/eta_service.py`, `GET /masterplans/{id}/projection`, `PUT /masterplans/{id}/anchor`
- ✅ Velocity hook — `complete_task()` recalculates ETA for active plan on every task completion
- ✅ APScheduler daily 6am ETA recalculation job
- ✅ `MasterPlanDashboard.jsx` — `ETAProjectionPanel` + `AnchorModal`
- ✅ 42 new tests (850 total passing, 0 failing)

**Tech debt closed:** §15.8, §15.5, §10.1

---

### ✅ Sprint N+2: "The Watcher" — COMPLETE (2026-03-24)

**Delivered:**
- ✅ `watcher/window_detector.py` — cross-platform active window detection; Windows/macOS/Linux/psutil fallback; never raises
- ✅ `watcher/classifier.py` — `ActivityType` (WORK/COMMUNICATION/DISTRACTION/IDLE/UNKNOWN); 60+ process name patterns + window title regexes
- ✅ `watcher/session_tracker.py` — `SessionState` machine; 6 signal types: session_started, session_ended, distraction_detected, focus_achieved, context_switch, heartbeat
- ✅ `watcher/signal_emitter.py` — batched HTTP, 3-attempt retry, DRY_RUN mode
- ✅ `watcher/config.py` — env-var configurable; validate()
- ✅ `watcher/watcher.py` — main loop; argparse CLI; SIGINT/SIGTERM graceful shutdown
- ✅ `db/models/watcher_signal.py` + migration `d7e6f5a4b3c2`
- ✅ `routes/watcher_router.py` — `POST /watcher/signals`, `GET /watcher/signals`; API key auth; ETA recalc on session_ended
- ✅ 65 new tests (916 total passing, 0 failing)

**Tech debt closed:** INFINITY_ALGORITHM_SUPPORT_SYSTEM Phase v2 (Observation Layer — Watcher) §7

**Remaining from original N+2 scope (deferred to N+3):**
- `services/infinity_loop.py` — enforced execution feedback loop
- Watcher signals → TWR scoring integration (Phase v3)
- Freelancing metrics completion

---

### ✅ Sprint N+3: "Infinity Algorithm Loop" — COMPLETE (2026-03-24)

**Delivered:**
- ✅ `db/models/user_score.py` — `UserScore` + `ScoreHistory` + `KPI_WEIGHTS` (assert sum==1.0 at import)
- ✅ Alembic migration — `user_scores` (latest cache, unique per user) + `score_history` (append-only time series)
- ✅ `services/infinity_service.py` — 5 KPI calculators + `calculate_infinity_score()` (never raises)
  - `calculate_execution_speed`: task velocity sigmoid vs 14-day baseline
  - `calculate_decision_efficiency`: completion rate + ARM quality trend (parses result_full JSON)
  - `calculate_ai_productivity_boost`: ARM usage frequency + quality improvement trend
  - `calculate_focus_quality`: watcher session duration + distraction ratio (neutral 50.0 until user_id added to watcher_signals)
  - `calculate_masterplan_progress`: task completion % + days_ahead_behind schedule sigmoid
- ✅ Event triggers (fire-and-forget, try/except): task completion, watcher session_ended, ARM analysis complete
- ✅ APScheduler 7am daily `_recalculate_all_scores` job (after 6am ETA job)
- ✅ Social feed ranking updated: `_compute_infinity_ranked_score()` — recency(0.4) + author_score(0.4) + trust(0.2); batch PostgreSQL lookup per feed request
- ✅ `routes/score_router.py` — `GET /scores/me`, `POST /scores/me/recalculate`, `GET /scores/me/history`
- ✅ `InfinityScorePanel` in `Dashboard.jsx` — SVG score ring, 5 KPI cards, history sparkline
- ✅ `api.js` — `getMyScore`, `recalculateScore`, `getScoreHistory`
- ✅ 55 new tests (995 total passing, 5 pre-existing failures unchanged)

**Tech debt closed:** INFINITY_ALGORITHM §Phase v4, INFINITY_ALGORITHM_SUPPORT §Phase v3

**Known open (deferred to N+4):** `WatcherSignal.user_id` missing — focus_quality returns neutral until per-user association added

---

### Sprint N+4: "First Agent"

**Goal:** Launch the Agentics runtime Phase 1–2, and expose the system's invisible signals as visible surfaces.

**Items:**
- Build `services/agent_runtime.py`: accept a goal, call LLM planner → structured plan schema (`goal`, `steps`, `risk_level`), execute via tool registry — AGENTICS Phase 1
- Implement tool registry: wrap `task.create/complete`, `memory.recall/write`, `arm.analyze` as agent tools
- Dry-run preview: return plan before execution ("Here is what I will do") — AGENTICS Phase 2
- Approval gate: `POST /agent/runs/{id}/approve` for high-risk plans; risk scoring via `risk_level` in plan schema
- New routes: `POST /agent/runs`, `GET /agent/runs`, `POST /agent/runs/{id}/approve`, `GET /agent/runs/{id}`
- Frontend: `AgentConsole.jsx` — goal input, plan preview, approve/execute, step timeline
- ThreadWeaver v1–v3: detects time-to-response patterns, deltas, predictions, and narratives across Ping sequences; service `services.threadweaver.py` is fully implemented.
- Frontend: `RippleTraceViewer.jsx` — signal timeline, ripple chain visualization (§15.16)
- Frontend: `ObservabilityDashboard.jsx` — request latency, memory node counts, flow run counts (§15.17)

**Expected outcome for the user:** User describes a goal. A.I.N.D.Y. produces a plan, shows what it intends to do, and executes on approval. Tasks, memory, and analysis are triggered autonomously. RippleTrace signals become navigable. System health is visible without log scraping.

**Estimated tests added:** ~65
**Tech debt closed:** AGENTICS §Phase 1–2, RIPPLETRACE §Phase v2, §15.16, §15.17

---

## Strategic Assessment

A.I.N.D.Y. is designed to be a **self-improving autonomous execution system**: a trajectory engine that turns human work into compressed timelines, measurable identity, and adaptive intelligence. As of today, the foundation is genuinely impressive — 134 endpoints, a fully instrumented Memory Bridge, a working Flow Engine with WAIT/RESUME semantics, federated agent memory, and a tested auth/security layer. The system is architecturally coherent and technically solid. But it has a critical gap: **the loop is not closed.**

The Infinity Algorithm exists as five endpoints and some formulas. The Memory Bridge writes beautifully and recalls with resonance scoring. The Flow Engine tracks execution with node-level granularity. But none of these systems feed back into each other in an enforced, autonomous way. A task completion updates a score, but nothing adjusts future task prioritization. An ARM analysis captures a memory node, but nothing changes what question is asked next. The MasterPlan is locked, but there is no trajectory projection — the user cannot see whether they are ahead or behind. The system measures everything and acts on nothing.

The next 90 days should focus on two things above all else: **closing the feedback loop** (Infinity Algorithm v4 + Watcher) and **launching the first agent** (Agentics Phase 1). These two items together transform A.I.N.D.Y. from a sophisticated metrics and memory platform into an autonomous execution partner. The MasterPlan anchor work in Sprint N+1 is the prerequisite: you cannot compress a timeline without declaring one. Once ETA projection is live, every task completion becomes a signal that either advances or delays the target, and the system has a reason to act.

The Agentics runtime in Sprint N+3 is the most strategically important bet in the roadmap. The Nodus execution substrate already exists. The Memory Bridge already provides context. The tool surface (tasks, ARM, memory) is already built. What is missing is the thin adapter layer that wraps these capabilities into a goal-oriented execution loop. Agentics Phase 1 is not a research project — it is integration work on top of systems that already function. Once a user can say "grow my freelance pipeline" and receive a plan, approve it, and watch A.I.N.D.Y. execute tasks, query research, and store outcomes autonomously, the product crosses from "powerful tool" into "intelligent partner."

---

## Decisions Needed

Before Sprint N+2 can be written with full precision, the following strategic questions require your direction:

1. **Watcher scope**: The Watcher is documented as potentially including OS-level monitoring (active window/process tracking). Is the intended scope (a) manual session tracking only (user presses Start/Stop), (b) passive browser/app activity inference, or (c) full OS-level attention monitoring? The architecture of `watcher_service.py` changes significantly depending on the answer.

2. **Infinity Algorithm loop enforcement model**: Should the Infinity Algorithm loop be (a) a background process that scores continuously, (b) an event-driven recalculator triggered by task completion / ARM analysis, or (c) a scheduled periodic re-score job via APScheduler? Each has different latency and user-experience implications.

3. **Agentics autonomy level**: For Sprint N+3, should the first agent run be (a) always approval-gated (every plan requires human sign-off before execution), (b) risk-based (low-risk plans auto-execute, high-risk require approval), or (c) opt-in autonomous (user can flip a "trust this agent" flag)? This determines whether the approval gate is a soft feature or a hard invariant.

4. **MasterPlan anchor type**: Should the anchor be (a) a target completion date ("I want to hit this goal by 2026-12-31"), (b) a goal value ("I want $10k MRR"), or (c) both? The ETA projection formula differs for date-anchored vs value-anchored plans.

5. **RippleTrace vs Social overlap**: RippleTrace and the Social Layer both track content interactions. Should they merge into a single signal surface (one unified "influence layer"), or remain separate systems serving different purposes (RippleTrace = external/invisible signals; Social = internal/explicit interactions)? This affects Sprint N+3 scope.
