## Sprint N+9 — Phase 4 Completion + Request Context

- **Branch:** `feat/infinity-algorithm-loop`
- **Date:** 2026-03-25
- **Tests:** 1,326 passing | 69.65% coverage | +30 tests

### Summary

Three focused hardening items shipped across three phases:

**Phase 1 — APScheduler lease gating:** `start_background_tasks()` now returns `bool`. `scheduler_service.start()` is only called when the lease is acquired, so APScheduler no longer starts on follower instances in multi-worker deployments. A `background_lease_heartbeat` APScheduler job (60s interval) keeps the 120s lease alive. `is_background_leader()` public helper exposes leader state.

**Phase 2 — Request context propagation:** `_request_id_ctx: ContextVar[str]` added at `main.py` module level. `RequestContextFilter` injects `request_id` from the ContextVar into every `LogRecord`. All root-logger handlers upgraded in-place to format `%(asctime)s - %(levelname)s - [%(request_id)s] - %(message)s`. The `log_requests` middleware sets the ContextVar before `call_next()` so all downstream logs within a request carry the UUID. Non-request code paths log `[-]`.

**Phase 3 — Scheduler visibility:** `GET /observability/scheduler/status` (JWT-gated) returns `{scheduler_running, is_leader, lease: {owner_id, acquired_at, heartbeat_at, expires_at}}`.

### API Contract Updates
- `GET /observability/scheduler/status` added (JWT required).

### Tech Debt Closed
- TECH_DEBT.md §5: APScheduler multi-instance concurrency debt — fully resolved.
- TECH_DEBT.md §7: Request-id context propagation in log lines — resolved.
- EVOLUTION_PLAN.md Phase 4 (Scalability Readiness) — marked complete.

### Deployment Notes
- No new migrations. No new environment variables.

---

## Sprint N+8 — Agent Event Log

- **Branch:** `feat/infinity-algorithm-loop`
- **Date:** 2026-03-25
- **Tests:** 1,296 passing | 69.48% coverage | +40 tests

### Summary

Structured lifecycle event log for agent runs. Every lifecycle transition now emits a row in `agent_events` with a `correlation_id` (`run_<uuid4>`) that threads through `AgentRun`, `AgentStep`, and `AgentEvent`. A unified timeline endpoint merges lifecycle events and synthesised step events into a single chronological view.

Key deliverables: `AgentEvent` ORM model + migration; `emit_event()` always-non-fatal emitter; `correlation_id` propagated end-to-end; `GET /agent/runs/{id}/events` merged timeline; `new_plan` replay mode (re-calls GPT-4o for fresh plan); `AgentConsole.jsx` Timeline tab with colored event badges and pending-approval badge.

Architecture note: step events (STEP_EXECUTED/STEP_FAILED) are synthesised from `AgentStep` rows at read time — no double-write. Pre-N+8 runs return `{correlation_id: null, events: []}` gracefully.

### API Contract Updates
- `GET /agent/runs/{run_id}/events` added (JWT required) — 13th agent endpoint.

### Tech Debt Closed
- TECH_DEBT.md §16.2: `new_plan` replay mode — resolved.
- AGENTICS.md §3/§9 event log requirement — resolved.

### Deployment Notes
- Migration `c9d8e7f6a5b4` required: `agent_events` table + `correlation_id` columns on `agent_runs` and `agent_steps`.

---

## Sprint N+7 — Agent Observability

- **Branch:** `feat/infinity-algorithm-loop`
- **Date:** 2026-03-25
- **Tests:** 1,256 passing | 69.24% coverage | +55 tests

### Summary

Stuck-run recovery and full agent replay infrastructure. A startup scan marks any `AgentRun` or `FlowRun` rows stranded in `executing`/`running` status beyond the threshold (default 10 minutes) as `failed`. Manual `/recover` distinguishes `wrong_status` from `too_recent` via distinct 409 codes. The `/replay` endpoint creates a lineage-tracked re-run with `replayed_from_run_id`. All 12 agent endpoints were unified to return consistent run shape via `_run_to_dict()`.

### API Contract Updates
- `POST /agent/runs/{run_id}/recover` added.
- `POST /agent/runs/{run_id}/replay` added.
- All agent endpoints: serializer unified — `flow_run_id` + `replayed_from_run_id` now present on every run response.

### Deployment Notes
- Migration `d3e4f5a6b7c8` required: `replayed_from_run_id` on `agent_runs`.
- New env var: `AINDY_STUCK_RUN_THRESHOLD_MINUTES` (default: 10).

---

## Sprint N+6 — Deterministic Agent

- **Branch:** `feat/infinity-algorithm-loop`
- **Date:** 2026-03-25
- **Tests:** 1,201 passing | 69.18% coverage | +81 tests

### Summary

Replaced the Sprint N+4 for-loop executor with `NodusAgentAdapter` + `PersistentFlowRunner`. The `AGENT_FLOW` DAG has three nodes: `agent_validate_steps` → `agent_execute_step` (self-loop) → `agent_finalize_run`. Per-step retry policy: low/medium risk = 3 attempts; high-risk = 1 attempt (no silent replay). DB checkpointing occurs after each node. On completion, `FlowHistory` entries are captured into Memory Bridge. `AgentRun.flow_run_id` links every run to its `FlowRun` for audit. The installed `nodus` pip package is confirmed NOT usable (separate scripting-language VM with no PostgreSQL integration path).

### API Contract Updates
- All run responses: `flow_run_id` field added.

### Deployment Notes
- Migration `c2d3e4f5a6b7` required: `flow_run_id` on `agent_runs`.

---

## Sprint N+5 — Score-Aware Agent

- **Branch:** `feat/infinity-algorithm-loop`
- **Date:** 2026-03-24
- **Tests:** 1,120 passing | ≥69% coverage | +55 tests

### Summary

Three phases: (1) `WatcherSignal.user_id` added so `calculate_focus_quality()` produces per-user scores instead of neutral 50.0. (2) `_build_kpi_context_block()` injects a live Infinity Score snapshot into the GPT-4o planner system prompt so plans are KPI-aware. (3) `suggest_tools()` returns up to 3 KPI-driven tool suggestions with pre-filled goal strings; `GET /agent/suggestions` exposes them via API; `AgentConsole.jsx` renders suggestion chips below the goal input.

### API Contract Updates
- `GET /agent/suggestions` added (JWT required).

### Deployment Notes
- Migration `b1c2d3e4f5a6` required: `user_id` on `watcher_signals`.

---

## Sprint N+4 — First Agent (Agentics Phase 1 + 2)

- **Branch:** `feat/infinity-algorithm-loop`
- **Date:** 2026-03-24
- **Tests:** 1,065 passing | ≥69% coverage | +70 tests

### Summary

First complete agent runtime: a user submits a goal string, GPT-4o (JSON mode) generates a structured plan (`goal`, `steps[]`, `overall_risk`), the trust gate evaluates risk and either auto-executes or holds for approval, and each step invokes the appropriate registered tool. The 9-tool registry wraps `task.create`, `task.complete`, `memory.recall`, `memory.write`, `arm.analyze`, `arm.generate`, `leadgen.search`, `research.query`, and `genesis.message`. `AgentTrustSettings` allows per-user configuration of auto-execution for low and medium risk. `AgentConsole.jsx` provides goal input, plan preview with risk badge, approve/reject controls, and a step execution timeline.

### API Contract Updates
- 10 new agent endpoints: `POST /agent/run`, `GET /agent/runs`, `GET /agent/runs/{id}`, `POST /agent/runs/{id}/approve`, `POST /agent/runs/{id}/reject`, `GET /agent/runs/{id}/steps`, `GET /agent/tools`, `GET /agent/trust`, `PUT /agent/trust`, plus suggestions in N+5.

### Tech Debt Closed
- AGENTICS.md Phase 1 (Minimal Runtime) and Phase 2 (Dry-Run + Approval) — both resolved.

### Deployment Notes
- Migrations required: `AgentRun`, `AgentStep`, `AgentTrustSettings` tables.

---

## Release: Phase 8 — Data Integrity + Operational Hygiene

- **Version/Tag:** `main` (commit `106f381`)
- **Date:** 2026-03-22
- **Owner:** Shawn Knight
- **Designated maintainer:** Shawn Knight

### Summary

Phase 8 integrity and hygiene:
- **Ownership UUID normalization:** `user_id` converted to UUID for `research_results`, `freelance_orders`, `client_feedback`, `drop_points`, `pings` with FKs to `users.id` (migration `2359cded7445`).
- **Backfill verification:** `tools/maintenance/backfill_user_ids.py` dry-run shows no NULL `user_id` rows remaining in `tasks`, `leadgen_results`, `authors`.
- **Dead code cleanup:** removed orphan `save_memory_node` helper; moved `deepseek_arm_service.py` to `legacy/`.
- **Test hygiene:** duplicate `test_get_results` names in `test_routes.py` removed.
- **Migration drift guard:** `tests/test_migrations.py` added to enforce `alembic current == alembic heads`.

### Evidence Checklist

- Tests executed: Not recorded in release note (see latest CI run)
- `alembic current`: `2359cded7445`
- `alembic heads`: `2359cded7445`

### API Contract Updates

- None (schema + test hygiene only).

### Deployment Notes

- **Environment:** No new environment variables required.
- **Migration steps:** `alembic upgrade head` required to apply UUID normalization.

### Sign-Off

- **Approved by:** Shawn Knight
- **Maintainer sign-off (Shawn Knight):** Pending
- **Approval date:** 2026-03-22

---

## Release: Phase 7 — Contract + Test Coverage Hardening

- **Version/Tag:** `main` (commit `1258c4e`)
- **Date:** 2026-03-22
- **Owner:** Shawn Knight
- **Designated maintainer:** Shawn Knight

### Summary

Phase 7 contract and test coverage hardening:
- **API contract cleanup:** removed stale duplicate `/create_masterplan` gap note.
- **SEO legacy routes removed:** `/analyze_seo/`, `/generate_meta/`, `/suggest_improvements/` removed; docs aligned.
- **Health pings aligned:** `/health` targets updated to `/seo/*` and `/memory/metrics`.
- **Observability + route tests:** new tests for `/observability/requests`, `/dashboard/overview`, `/identity/*`, `/memory/metrics*`.
- **Legacy diagnostics guarded:** `bridge/benchmark_similarity.py` now guarded by `__main__`.

### Evidence Checklist

- Tests executed: Not recorded in release note (see latest CI run)
- Schema changes: None

### API Contract Updates

- SEO legacy endpoints removed from contract.

### Deployment Notes

- **Environment:** No new environment variables required.
- **Migration steps:** None.

### Sign-Off

- **Approved by:** Shawn Knight
- **Maintainer sign-off (Shawn Knight):** Pending
- **Approval date:** 2026-03-22

---
## Release: Phase 6 — Ownership Cleanup + Observability Hardening

- **Version/Tag:** `main` (commit `2b43f54`)
- **Date:** 2026-03-22
- **Owner:** Shawn Knight
- **Designated maintainer:** Shawn Knight

### Summary

Phase 6 cleanup and observability hardening:
- **Ownership backfill tooling:** `tools/maintenance/backfill_user_ids.py` added (dry-run capable) for legacy user_id gaps.
- **MasterPlan version cleanup:** `master_plans.version` removed; `version_label` is canonical.
- **Identity normalization:** `genesis_sessions.user_id` and `canonical_metrics.user_id` now UUID FK (legacy columns removed).
- **Observability surface:** `GET /observability/requests` added for request metrics query.
- **Health alignment:** `/health` pings aligned with active endpoints.
- **Memory metrics:** single write path enforced from execution loop.

### Evidence Checklist

- Tests executed: Not recorded in release note (see latest CI run)
- `alembic current`: `c4f2a9d1e7b3`, `d2a7f4c1b9e8`
- `alembic heads`: `c4f2a9d1e7b3`, `d2a7f4c1b9e8`
- Schema vs. migration verification: MasterPlan version removal + request metrics indices verified via migration logs

### API Contract Updates

- `GET /observability/requests` added (JWT required).

### Deployment Notes

- **Environment:** No new environment variables required.
- **Migration steps:** `alembic upgrade head` required for schema cleanup.
- **Known issues:** Legacy rows with `user_id = NULL` were checked via `tools/maintenance/backfill_user_ids.py` dry-run; none remain.

### Sign-Off

- **Approved by:** Shawn Knight
- **Maintainer sign-off (Shawn Knight):** Pending
- **Approval date:** 2026-03-22

---



