# Changelog

All notable changes to this project will be documented in this file.

The format is based on the "Keep a Changelog" style and follows semantic-style versioning where possible.

---

# [Unreleased]

Changes that have been implemented but are not yet part of a tagged release.

## Syscall Convergence Refactor — 2026-04-09

### Changed
* **`kernel/syscall_registry.py`** — `_handle_flow_run` updated to reuse caller's DB session via `context.metadata["_db"]` (opens own session only when absent, preserving route-managed transaction boundaries). Four new execution entry-point handlers added: `_handle_flow_execute_intent`, `_handle_nodus_execute`, `_handle_job_submit`, `_handle_agent_execute`. Four new syscalls registered: `sys.v1.flow.execute_intent` (cap: `flow.execute`), `sys.v1.nodus.execute` (cap: `nodus.execute`), `sys.v1.job.submit` (cap: `job.submit`), `sys.v1.agent.execute` (cap: `agent.execute`).
* **`runtime/flow_engine.py`** — `execute_intent()` and `run_flow()` are now thin syscall proxies. Real implementations moved to `_execute_intent_direct()` and `_run_flow_direct()` respectively. Both fall back to `_direct()` when `user_id=None`. `run_flow()` signature relaxed to `db: Session = None`.
* **`runtime/nodus_execution_service.py`** — `run_nodus_script_via_flow()` is now a thin syscall proxy. Real implementation moved to `_run_nodus_via_flow_direct()`. Falls back to `_direct()` when `user_id=None`. Optional fields (`trace_id`, `node_max_retries`) are excluded from the syscall payload when `None` to satisfy input schema validation.

### Architecture
* Single execution model achieved: all authenticated execution — Nodus scripts, routes, agents, schedulers — now routes through `SyscallDispatcher`. Capability enforcement, quota tracking, and observability apply uniformly.
* `ExecutionPipeline`, `ExecutionDispatcher`, `SchedulerEngine`, and flow engine core were **not changed**.
* No route handlers changed — they call `run_flow()` which is now a proxy; no API contract changes.

### Tests
* 110 syscall/Nodus unit tests pass; 410 flow/nodus/execute tests pass.
* 7 pre-existing auth failures in `test_syscall_versioning.py::TestSyscallsEndpoint` (401 Unauthorized — unrelated to this refactor).

---

## Distributed Execution + PRODUCTION-READY OS — 2026-04-07

### Added
* **`kernel/event_bus.py`** — Redis pub/sub distributed event bus. `EventBus` class wraps publish and subscriber paths. `get_event_bus()` singleton. `publish_event(event_type, correlation_id)` is the **only** public API for firing resume events — replaces all direct `notify_event()` call sites. Subscriber daemon thread reconnects with exponential backoff (1 s → 30 s cap). `AINDY_EVENT_BUS_ENABLED=false` disables entirely for local-only deployments.

### Changed
* **`kernel/scheduler_engine.py`** — `notify_event()` gains `broadcast: bool = True` parameter. When `True` (default), publishes to Redis after the local `_waiting` scan. When `False` (called from subscriber), suppresses re-publication to prevent infinite loops. `_waiting` entries are deleted under lock before enqueue — prevents same-instance duplicate resume.
* **`kernel/resource_manager.py`** — `mark_completed()` now calls `publish_event("resource_available")` (was `get_scheduler_engine().notify_event(...)`). Distributed broadcast on capacity transition.
* **`core/system_event_service.py`** — `emit_event()` now calls `publish_event(event_type, correlation_id=corr)` (was `get_scheduler_engine().notify_event(...)`).
* **`runtime/flow_engine.py`** — `route_event()` now calls `publish_event(event_type, correlation_id=corr)` (was `scheduler.notify_event(...)`). `PersistentFlowRunner.resume()` gains atomic FlowRun soft-lock: `UPDATE flow_runs SET status='executing' WHERE status='waiting'`; `rowcount=0` → returns `SKIPPED` immediately.
* **`core/flow_run_rehydration.py`** — `_make_resume_callback` enforces 3-step execution ordering: (1) FlowRun atomic claim, (2) EU status transition — only if claim won, (3) flow execution — only if claim won. Losing instances (rowcount=0) return immediately with no side effects.
* **`core/wait_rehydration.py`** — EU resume callback gains FlowRun ownership guard: if `FlowRun.status != "waiting"` when the callback fires, EU transition is skipped — avoids bookkeeping side effects on the losing instance.
* **`main.py`** — `get_event_bus().start_subscriber()` called at startup before WAIT rehydration. `rehydrate_waiting_flow_runs()` called after `rehydrate_waiting_eus()` (FlowRun callbacks registered after EU callbacks).

### Tests
* **`tests/unit/test_event_bus.py`** — 26 new tests (Groups A–D): singleton, publish, subscriber thread, `_handle_message` dispatch, fault-tolerance
* **`tests/system/test_flow_engine_phase_c_d.py`** — 7 new `TestResumeSoftLock` tests (Phase E): atomic claim, SKIPPED on double-claim, commit failure, EU/FlowRun ordering
* **`tests/unit/test_flow_run_rehydration.py`** — 12 new tests (Groups G and H): 3-step ordering, claim gate, losing-instance skip
* Assertion updates in `test_os_layer.py` and `test_flow_engine_phase_c_d.py` to reflect `broadcast=True` kwarg

### Results
* 254 tests passing in targeted suite; 0 regressions
* **Classification: PRODUCTION-READY OS** (upgraded from OS-LIKE, 2026-04-06)

## Unified RetryPolicy System — 2026-04-05

### Added
* **`core/retry_policy.py`** — central retry policy definition. `RetryPolicy` frozen dataclass (`max_attempts`, `backoff_ms`, `exponential_backoff`, `high_risk_immediate_fail`). Named constants: `FLOW_NODE_DEFAULT`, `AGENT_LOW_MEDIUM`, `AGENT_HIGH_RISK`, `ASYNC_JOB_DEFAULT`, `NODUS_SCHEDULED_DEFAULT`, `NO_RETRY`. `resolve_retry_policy(execution_type, risk_level, node_max_retries, job_max_retries)` is the single resolver. `is_retryable_error()` classifies error strings.

### Changed
* **`core/execution_gate.py`** — `require_execution_unit()` now resolves and persists a `retry_policy` dict into `ExecutionUnit.extra` for every execution. `_resolve_policy_for_eu()` maps `eu_type` + `workflow_type` + `risk_level` to the correct policy. Existing EUs are backfilled on the executing transition.
* **`runtime/flow_engine.py`** — module-level `_FLOW_RETRY_POLICY` resolved from `resolve_retry_policy(execution_type="flow")`. Retry gate at `node_status == "RETRY"` replaced `POLICY["max_retries"]` with `_run_policy.max_attempts`, where `_run_policy` is resolved per-node from `self.flow.get("node_configs", {})` supporting per-run overrides. `POLICY["max_retries"]` retained for backward compatibility but no longer gates retries.
* **`runtime/nodus_adapter.py`** — `_execute_agent_step()` replaces `max_attempts = 1 if risk_level == "high" else MAX_STEP_RETRIES` with `_step_policy = resolve_retry_policy(execution_type="agent", risk_level=risk_level)`. High-risk break condition replaced from `if risk_level == "high"` to `if _step_policy.high_risk_immediate_fail`. `MAX_STEP_RETRIES` retained as reference constant.
* **`platform_layer/async_job_service.py`** — `_execute_job_inline()` exception handler now checks `log.attempt_count < log.max_attempts` before marking a job failed. If true: resets status to `"pending"`, commits, and resubmits via executor. Current default `max_attempts=1` preserves existing no-retry behavior; callers that submit with `max_attempts > 1` now get actual retries.
* **`runtime/nodus_execution_service.py`** — `run_nodus_script_via_flow()` adds `node_max_retries: Optional[int] = None`. When provided, injects `node_configs = {"nodus.execute": {"max_retries": node_max_retries}}` into a per-run copy of the flow dict. The shared `NODUS_SCRIPT_FLOW` constant is never mutated.
* **`runtime/nodus_schedule_service.py`** — `_run_scheduled_job()` now passes `node_max_retries=job.max_retries` to `run_nodus_script_via_flow()`. Resolves the audit WARNING: scheduled jobs previously stored `max_retries` correctly in `AutomationLog` but the flow engine always defaulted to 3 retries regardless of the job's configured limit.

### Results
* Tests: 2,088 passing, 19 skipped — all green
* Audit: 0 violations, 0 warnings (nodus_schedule_service WARNING resolved)

---

## Execution Unification Layer — 2026-04-05

### Added
* **`core/execution_gate.py`** — new unification layer. `require_execution_unit()` creates or attaches an `ExecutionUnit` record before any execution begins (idempotent, non-fatal). `to_envelope()` produces the canonical `{eu_id, trace_id, status, output, error, duration_ms, attempt_count}` shape. Adapter functions `flow_result_to_envelope()`, `agent_result_to_envelope()`, `nodus_result_to_envelope()`, and `job_result_to_envelope()` map existing domain records to that shape without model deletion.
* **`core/execution_envelope.py`** — added `unified()` function alongside existing `success()` and `error()` helpers.

### Changed
* **`runtime/nodus_execution_service.py`** — EU creation moved before `execute_nodus_runtime()` call (was created after completion). Pre-EU lifecycle: create EU → execute → update status. Ensures stuck runs are tracked even if the process dies mid-execution.
* **`routes/agent_router.py`** — `_run_flow_agent()` embeds `execution_envelope` in dict-typed results using `to_envelope(..., output=None)`. Fixed `data = result.get("data") or {}` coercing empty lists to dicts (now uses explicit `if data is None` guard — fixes `test_no_cross_user_leakage`).
* **`routes/automation_router.py`** — `_run_flow_automation()` embeds `execution_envelope`; `replay_automation_log` and `trigger_task_automation` handlers now call `require_execution_unit()` before dispatch.
* **`routes/flow_router.py`** — `resume_flow_run` handler calls `require_execution_unit()` before dispatch and embeds `execution_envelope` in response.
* **`routes/platform_router.py`** — `compile_and_run_nodus_flow` now runs full EU lifecycle around `PersistentFlowRunner.start()` (the only route that called it directly). `_run_flow_platform()` and `run_nodus_script` embed `execution_envelope` in responses.

### Results
* Tests: 2,088 passing, 19 skipped — all green
* No new test failures introduced

---

## Current Workspace

### Fixed
* **`services/async_job_service.py`** — async submission and worker execution are now split cleanly. Jobs always persist `AutomationLog` before exit, emit `execution.started` at submission time, emit `async_job.started|completed|failed` during queued worker execution, and roll back handler-side partial writes before persisting terminal failure state.
* **`services/system_event_service.py`** — required event failures now roll back the broken session, attempt a fallback `error.system_event_failure`, and then raise fail-closed instead of allowing the caller to continue with a dirty session.
* **`services/agent_tools.py`** and **`services/nodus_adapter.py`** — capability decisions now emit explicit `capability.allowed` and `capability.denied` ledger events at the real execution boundary.
* **`routes/agent_router.py`** — invalid agent `run_id` path inputs now fail cleanly as HTTP `400` instead of surfacing UUID parsing as a server error.
* **`runtime/memory/strategies.py`** — `StrategySelector` now returns cloned strategy objects instead of mutating shared global strategy instances. This fixed cross-test and cross-request recall poisoning where one execution path could override `node_types` for later runs.
* **`services/system_event_service.py`** — successful-path `SystemEvent` persistence diagnostics improved. Emit attempts and persistence success/failure are now logged; persistence uses `flush()` before commit and logs a stable `event_id`.
* **`services/async_job_service.py`** — async heavy-execution jobs now emit `execution.started`, `execution.completed`, and `execution.failed` / `error.async_job_execution` with `trace_id == automation_log_id`.
* **`routes/auth_router.py`** — successful auth routes now emit `auth.register.completed` and `auth.login.completed`.
* **`routes/health_router.py`** — successful health routes now emit `health.liveness.completed` and `health.readiness.completed` as best-effort observability events.
* **`services/task_services.py`** — background lease timestamps normalized to timezone-aware UTC; naive DB values are coerced before comparison. Live worker startup warning `can't compare offset-naive and offset-aware datetimes` eliminated.
* **`services/agent_runtime.py`** — UUID-backed agent run lookups now normalize `run_id` consistently across execution, replay, and event timeline paths.
* **`services/nodus_adapter.py`** — UUID-backed agent-step persistence and agent-run lookups now normalize runtime IDs before querying or writing.
* **`services/capability_service.py`** — capability mappings now persist UUID-safe `agent_run_id` values instead of leaking string IDs into UUID columns.
* **`services/agent_event_service.py`** and **`services/system_event_service.py`** — user IDs and payloads are normalized for UUID-backed persistence; `SystemEvent` payloads now serialize UUID values safely.
* **`routes/agent_router.py`** — `/agent/runs/{run_id}/events` fallback lookup now uses UUID-safe run ID parsing.
* **`tests/conftest.py`** — pytest runtime now injects secure test env defaults for `PERMISSION_SECRET` and enables the legacy compatibility surface explicitly in `TEST_MODE`, keeping API-key coverage intact without relying on developer-local env files.
* **Structured test suite** — remaining stale UUID, path, and side-effect assumptions were aligned to the current runtime contracts:
  - legacy compatibility routes are exercised with `api_key_headers`
  - anchor/ETA tests use UUID user IDs and repo-root Alembic path resolution
  - agent ORM metadata assertions no longer depend on fragile `Base` import order

### Added
* **`tests/system/test_hardening.py`** — new DB-backed hardening suite covering:
  - async job terminal-state guarantees
  - rollback integrity on mid-job failure
  - lease exclusivity and expired-lease reclaim
  - canonical event-chain completeness
  - clean invalid-UUID handling on agent execution routes
* **`tests/system/test_invariants.py`** — new DB-backed system invariant suite covering:
  - execution emits durable events
  - cross-user isolation
  - capability denial changes execution outcome
  - memory create/read consistency
  - request metrics and dashboard visibility
* **`tests/system/test_agent_events.py`**, **`tests/system/test_deterministic_agent.py`**, and **`tests/system/test_capability_system.py`** were rebuilt around the real SQLite-backed fixture stack. The old `MockSession` / fake-query-chain patterns were removed from these files in favor of persisted `AgentRun`, `AgentStep`, `AgentEvent`, `SystemEvent`, and `AutomationLog` rows with boundary-only mocks.

### Verified
* `pytest -q` → full suite green
* Live compose validation confirmed durable `system_events` rows for successful:
  - health
  - readiness
  - auth register/login
  - async heavy execution
* `pytest -q --no-cov` → full suite green (`1290 passed, 4 skipped`)
* `pytest tests/system/test_invariants.py tests/system/test_agent_events.py tests/system/test_deterministic_agent.py tests/system/test_capability_system.py --no-cov -q` → `22 passed`

## Sprint N+7: Agent Observability — 2026-03-25

### Added
* **`services/stuck_run_service.py`** — `scan_and_recover_stuck_runs(db, staleness_minutes)` startup scan. Queries `FlowRun.status="running"` rows older than `AINDY_STUCK_RUN_THRESHOLD_MINUTES` (default 10). For `workflow_type="agent_execution"`: marks both `FlowRun` and linked `AgentRun` as failed, reconstructs `AgentRun.result` from committed `AgentStep` rows. Non-agent types: mark `FlowRun` failed silently. Per-run try/except + outer try/except; never raises.
* **`recover_stuck_agent_run(run_id, user_id, db, force=False)`** in `stuck_run_service.py` — manual recovery with distinct 409 error codes: `wrong_status` ("Run is not in executing state") and `too_recent` ("Run started less than N minutes ago (use ?force=true to override)"). `force=True` bypasses age guard only.
* **`POST /agent/runs/{run_id}/recover`** — manual recovery endpoint.
* **`replay_run(run_id, user_id, db, mode="same_plan")`** in `agent_runtime.py` — creates new `AgentRun` from original plan; trust gate re-applied; prior approval does not carry forward.
* **`_create_run_from_plan(..., replayed_from_run_id=None)`** in `agent_runtime.py` — internal helper that persists a new run from an existing plan dict, skipping GPT-4o.
* **`POST /agent/runs/{run_id}/replay`** — replay endpoint.
* **Migration `d3e4f5a6b7c8`** — `replayed_from_run_id` nullable VARCHAR on `agent_runs`, chains off `c2d3e4f5a6b7`.
* **`AgentRun.replayed_from_run_id`** — nullable column tracking replay lineage.
* **`main.py` lifespan** — startup scan hook after `register_all_flows()`, gated behind `enable_background` and `not PYTEST_CURRENT_TEST`.
* **`tests/test_agent_observability.py`** — 55 tests across Phase 1 (scan), Phase 2 (recover), and Phase 3 (replay, migration, serializer unification).

### Changed
* **`_run_to_response()` in `routes/agent_router.py`** — now delegates to `_run_to_dict()` from `services/agent_runtime.py`. All 12 agent endpoints now return a consistent shape including `flow_run_id` and `replayed_from_run_id`.
* **`_run_to_dict()` in `services/agent_runtime.py`** — includes `replayed_from_run_id`.
* Agent router docstring updated with 12-endpoint list.

### Results
* Tests: 1,256 passing (+55), 5 pre-existing failures, 1 pre-existing error
* Coverage: 69.24% (threshold: 69%)

---

## Sprint N+6: Deterministic Agent — 2026-03-25

### Added
* **`services/nodus_adapter.py`** — `NodusAgentAdapter` with 3 registered flow nodes:
  - `agent_validate_steps`: validates plan, initialises iteration state
  - `agent_execute_step`: executes one step with internal for-loop retry (low/medium: 3x; high: 1 attempt, no retry)
  - `agent_finalize_run`: marks `AgentRun.status="completed"`, writes step results
* **`AGENT_FLOW`** — DAG with self-loop: `agent_validate_steps → agent_execute_step` (loops via `_more_steps()`) `→ agent_finalize_run`.
* **`NodusAgentAdapter.execute_with_flow()`** — links `FlowRun.id → AgentRun.flow_run_id`; on FAILURE reconstructs `AgentRun.result` from committed `AgentStep` rows; never raises.
* **Migration `c2d3e4f5a6b7`** — `flow_run_id` nullable VARCHAR on `agent_runs`, chains off `b1c2d3e4f5a6`.
* **`AgentRun.flow_run_id`** — nullable column linking to `FlowRun.id`.
* **`tests/test_deterministic_agent.py`** — 81 tests across 15 classes covering model column, migration, 3 nodes, flow graph, adapter, exception recovery, approve/reject, and serializer.

### Changed
* **`execute_run()` in `services/agent_runtime.py`** — N+4 sequential for-loop fully removed; now marks `"executing"` then delegates entirely to `NodusAgentAdapter.execute_with_flow()`.
* **`_run_to_dict()`** — includes `flow_run_id`.

### Key Notes
* Nodus pip package (`venv/Lib/site-packages/nodus/`) is a separate scripting-language VM requiring Nodus VM closures and filesystem JSON checkpoints — NOT used. `PersistentFlowRunner` is the execution substrate.
* High-risk no-retry rule: `genesis.message` and other `risk_level="high"` steps halt immediately on first failure.

### Results
* Tests: 1,201 passing (+81), 5 pre-existing failures, 1 pre-existing error
* Coverage: 69.18% (threshold: 69%)

---

## Sprint N+5: Score-Aware Agent — 2026-03-24

### Added
* **`WatcherSignal.user_id`** column + migration `b1c2d3e4f5a6` — enables per-user focus quality calculation.
* **`calculate_focus_quality()`** updated — now queries `watcher_signals` filtered by `user_id`; returns neutral 50.0 when no data.
* **`_build_kpi_context_block()`** in `agent_runtime.py` — injects live Infinity Score snapshot into planner system prompt (focus guidance, execution speed bias, ARM suggestion, high-score unlock).
* **`suggest_tools(kpi_snapshot)`** in `agent_tools.py` — returns up to 3 KPI-driven tool suggestions with pre-filled goal strings; returns `[]` when no snapshot.
* **`GET /agent/suggestions`** — KPI-based tool suggestions endpoint.
* **`AgentConsole.jsx`** — suggestion chips rendered below goal input; clicking a chip pre-fills the goal field.
* **`tests/test_score_aware_agent.py`** — 55 tests across all 3 phases.

### Results
* Tests: 1,120 passing (+55), 5 pre-existing failures, 1 pre-existing error
* Coverage: 69% (threshold: 69%)

---

## Sprint N+4: First Agent (Agentics Phase 1+2) — 2026-03-24

### Added
* **`services/agent_runtime.py`** — full agent lifecycle: `generate_plan()` (GPT-4o JSON mode), `_requires_approval()` trust gate, `create_run()`, `execute_run()`, `approve_run()`, `reject_run()`, `_run_to_dict()`.
* **`services/agent_tools.py`** — 9-tool registry: `task.create`, `task.complete`, `memory.recall`, `memory.write`, `arm.analyze`, `arm.generate`, `leadgen.search`, `research.query`, `genesis.message`. Each entry has risk level, description, executor.
* **`db/models/agent_run.py`** — `AgentRun`, `AgentStep`, `AgentTrustSettings` ORM models.
* **Migrations** — `agent_runs`, `agent_steps`, `agent_trust_settings` tables.
* **`routes/agent_router.py`** — 10 endpoints: `POST /agent/run`, `GET /agent/runs`, `GET /agent/runs/{id}`, `POST /agent/runs/{id}/approve`, `POST /agent/runs/{id}/reject`, `GET /agent/runs/{id}/steps`, `GET /agent/tools`, `GET /agent/trust`, `PUT /agent/trust`, `GET /agent/suggestions`.
* **`AgentConsole.jsx`** — goal input, plan preview with risk badge, step timeline, approve/reject controls.
* **`tests/test_first_agent.py`** — 70 tests.

### Tech Debt Closed
* AGENTICS.md Phase 1 (Minimal Runtime) — **DONE**
* AGENTICS.md Phase 2 (Dry-Run + Approval) — **DONE**

### Results
* Tests: 1,065 passing (+70), 5 pre-existing failures
* Coverage: ≥69% (threshold: 69%)

---

## Migration Policy — Schema Sync (Additive) — 2026-03-22

### Changed
* **ORM models** — aligned `nullable=False` with DB reality:
  - `automation_log.py`: `attempt_count`, `max_attempts` now `nullable=False`
  - `user_identity.py`: `observation_count` now `nullable=False`
  - `agent.py`: `is_active` now `nullable=False`
* **Migration `a4c9e2f1b8d3`** — additive-only schema sync applied. Adds 3 missing indexes and 1 unique constraint:
  - `ix_master_plans_user_id` (master_plans.user_id)
  - `uq_memory_links_unique` (memory_links: source+target+type, unique)
  - `ix_memory_metrics_id` (memory_metrics.id)
  - `uq_user_identity_user` (user_identity.user_id, unique)
* Deleted dangerous draft `fdfbc1dce688` (would have dropped HNSW vector index + request_metrics FK).

### Skipped (documented in TECH_DEBT.md §15)
* `ix_memory_nodes_embedding_hnsw` — HNSW pgvector index, managed manually, must not be dropped
* `request_metrics_user_id_fkey` — intentional FK, kept
* `ix_request_metrics_path_created_at` — composite index, kept
* `background_task_leases` constraint rename — risky, deferred

### Results
* `alembic current == alembic heads == a4c9e2f1b8d3` ✅
* Tests: 690 passed, 0 failed, 3 skipped
* Coverage: 69.08% (threshold: 69%)

---

## Flow Engine Phase A — APScheduler + tenacity replaces daemon threads — 2026-03-22

### Added
* **`services/scheduler_service.py`** — APScheduler `BackgroundScheduler` wrapper with tenacity retry, `AutomationLog` audit trail, task registry (`@register_task`), `run_task_now()` / `replay_task()` / `get_scheduler()`, and 3 system jobs on startup: `task_reminder_check` (1 min), `cleanup_stale_logs` (1 hr), `task_recurrence_check` (every 6 hrs via cron).
* **`db/models/automation_log.py`** — `AutomationLog` ORM model with 14 columns covering source, status, attempt tracking, user scoping, payload, result, and timestamps.
* **Migration `37020d1c3951`** — `automation_logs` table + 3 indexes. Applied.
* **`routes/automation_router.py`** — `GET /automation/logs`, `GET /automation/logs/{id}`, `POST /automation/logs/{id}/replay`, `GET /automation/scheduler/status`.
* **`tests/test_flow_engine_phase_a.py`** — 38 tests across scheduler service, lifecycle, model, endpoints, and daemon-thread elimination assertions.

### Changed
* **`services/task_services.py`** — All 3 `daemon=True` threads eliminated. `start_background_tasks()` now acquires inter-instance DB lease only; recurring jobs moved to `scheduler_service`. `threading` module import removed entirely.
* **`main.py`** — `scheduler_service.start()` before `start_background_tasks()` in lifespan; `scheduler_service.stop()` in shutdown.

### Tech Debt Closed
* §partially-resolved "Background tasks supervised via daemon threads" → **FULLY RESOLVED**: 0 daemon threads, APScheduler running, tenacity retry, `AutomationLog` audit trail + replay.

### Results
* Tests: 690 passed, 0 failed, 3 skipped (was: 652)
* Coverage: 69.08% (threshold: 69%)
* daemon=True occurrences in task_services.py: 0

---

## Make It Visible UI Sprint — 2026-03-22

### Added
* **MemoryBrowser.jsx** — full React component surfacing Memory Bridge v4 recall, suggestions, agent filtering, per-node resonance bar, feedback (thumbs up/down with optimistic update), share toggle, and expandable detail panel (performance / history / traverse tabs). Route: `/memory`.
* **IdentityDashboard.jsx** — 2×2 dimension grid (Communication, Tools, Decision Making, Learning) with inline edit modal, evolution timeline with observation count / change stats / arc badge / recent-changes log, and collapsible "how AINDY sees you" context preview. Route: `/identity`.
* **AgentRegistry.jsx** — per-agent cards with memory stats, inline recall panel per agent, federated recall panel with namespace filter chips, active/inactive sections. Route: `/agents`.
* **Sidebar.jsx** — new "Memory" section with items: 🧠 Memory Browser → `/memory`, 👤 Identity Profile → `/identity`, 🤖 Agent Federation → `/agents`.
* **App.jsx** — imports and routes for all 3 new components.
* **16 new API functions in `client/src/api.js`** — `getMemoryNodes`, `recallMemory`, `getMemorySuggestions`, `recordMemoryFeedback`, `getNodePerformance`, `traverseMemory`, `getNodeHistory`, `getFederatedRecall`, `shareMemoryNode`, `getIdentityProfile`, `updateIdentityProfile`, `getIdentityEvolution`, `getIdentityContext`, `getAgents`, `recallFromAgent`, `getFederatedMemory`.
* **`tests/test_memory_browser_ui.py`** — 27 backend endpoint smoke tests across `TestMemoryBrowserEndpoints`, `TestIdentityDashboardEndpoints`, `TestAgentRegistryEndpoints`. Verifies auth enforcement, response shape, and 200-vs-404-vs-500 handling.

### Results
* Tests: 640 passed, 0 failed, 15 skipped (was: 613 passed)
* Coverage: 69.76% (threshold: 69%)
* Memory Bridge, Identity Layer, and Agent Federation now have frontend surfaces

---

## Quick Wins Cleanup — 2026-03-22

### Fixed
* **Tests (Fix 1):** Deleted 3 stale orphan-documentation tests that were asserting a bug that was correctly fixed (`test_orphan_save_memory_node_exists_at_module_level`, `test_orphan_save_memory_node_causes_type_error_if_called`, `test_memory_node_body_has_incomplete_logic`). Result: 3 fewer test failures.
* **Tests (Fix 2):** `test_migrations.py` — replaced `python -m alembic` subprocess call (fails due to local `alembic/` package shadowing the installed one) with direct `alembic` CLI call. Test now skips gracefully in unit-test environments where the DB is unavailable rather than failing.
* **Identity Service (Fix 3):** `IdentityService.get_evolution_summary()` now returns a consistent shape for both new and existing users. New-user early-return now includes `total_changes`, `dimensions_evolved`, `most_changed_dimension`, `recent_changes`, `evolution_arc` keys (with zero/empty values) matching the existing-user return shape.
* **Tests (Fix 4):** `test_identity_profile_shape` updated to assert the real `GET /identity/` response shape (`communication`, `tools`, `decision_making`, `learning` keys) instead of a non-existent top-level `profile` key. Result: 2 fewer test failures.
* **Lint (Fix 5):** All 6 ruff violations resolved — 4 E712 (SQLAlchemy `== True` → `.is_(True)` in filter expressions across `routes/main_router.py` and `routes/memory_router.py`) and 2 F405 (`settings` added as explicit import in `main.py` to fix star-import shadowing). Result: 0 ruff violations.
* **Architecture (Fix 6):** Hardcoded Windows path `r"C:\dev\Coding Language\src"` in `routes/memory_router.py::execute_nodus_task()` replaced with `os.environ.get("NODUS_SOURCE_PATH", ...)`. `NODUS_SOURCE_PATH` added to `.env.example`.
* **CI (Fix 8):** Coverage threshold raised from 64% to 69% in `pytest.ini` to close the 5.6-point gap between floor and actual baseline (69.62%).
* **Config (Fix 9):** `PERMISSION_SECRET` given a default empty string in `config.py` — the HMAC path it protected was removed in Sprint 6; requiring deployment to set a meaningless secret caused friction.

### Blocked
* **Fix 7 (bridge_router DAO import):** Could not be completed as a simple import swap. The legacy `MemoryNodeDAO` in `services/memory_persistence.py` exposes `load_memory_node()` which the canonical DAO in `db/dao/memory_node_dao.py` does not implement. Swapping the import breaks `POST /bridge/link`. Requires DAO interface alignment (separate sprint item).

### Results
* Tests: 613 passed, 0 failed, 15 skipped (was: 611 passed, 6 failed, 14 skipped)
* Lint: 0 violations (was: 6)
* Coverage: 69.62% (threshold raised to 69%)

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
* Symbolic memory ingest: `services/memory_ingest_service.py` and `tools/memory/ingest_memory.py`
* Request metrics baseline: `request_metrics` table + structured request logging middleware
* Observability route tests for `GET /observability/requests`
* Route-level tests for `/dashboard/overview`, `/identity/*`, and `/memory/metrics*`

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
* Legacy SEO endpoints removed; health ping list aligned to `/seo/*` and `/memory/metrics`
* Benchmark similarity script guarded with `__main__` to prevent import-time execution
* Ownership UUID normalization for `research_results`, `freelance_orders`, `client_feedback`, `drop_points`, `pings` (migration `2359cded7445`)
* Migration drift guard added via `tests/test_migrations.py`

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
* **`apps/freelance/models/freelance.py`** — `FreelanceOrder` and `ClientFeedback` ORM models updated with `user_id` column.
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
* **`docs/deployment/DEPLOYMENT_MODEL.md`** — added development reminder in Section 4: run migrations before starting the server or tests.
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
* **`apps/arm/services/deepseek/deepseek_code_analyzer.py`** — three memory hooks added:
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
* **`docs/platform/engineering/TECH_DEBT.md`** — §10.5, §10.6, §10.7, §8 embedding item closed. §12 (Phase 3 open items) added.

---

# [main — Docker pgvector Setup] — 2026-03-18

## Added

* **`docker-compose.yml`** (repo root) — `pgvector/pgvector:pg16` container on port `5433`
  with named volume `aindy_pgdata` for data persistence and `unless-stopped` restart policy.
* **`docs/deployment/DOCKER_SETUP.md`** — full operational guide: quick start, connection details,
  common commands, data persistence, rollback to PG18 instructions.
* **`AINDY/.env.pg18`** — backup of original PG18 connection string (gitignored); allows
  one-file rollback to local PostgreSQL 18 if needed.
* **`pgvector==0.4.2`** added to `requirements.txt` (Python package; installed in venv).
* **`.env.pg18`** added to root `.gitignore`.

## Notes

* Docker Desktop is not yet installed on the development machine. Container is not running.
  `.env` and `alembic.ini` still point to `localhost:5432` (PG18). Port update (`5432→5433`),
  `CREATE EXTENSION IF NOT EXISTS vector`, and `alembic upgrade head` are deferred until
  Docker Desktop is installed. See `docs/deployment/DOCKER_SETUP.md` for the complete runbook.
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

* **`bridge/bridge.py` ImportError** — `from db.models.models import CalculationResult` corrected to `from db.models.calculation import CalculationResult`. `db/models/models.py` does not exist; every call to `create_memory_node()` (social posts, leadgen) was crashing with `ImportError` before reaching any DB logic. Wrong-table architectural issue (`calculation_results` vs `memory_nodes`) remains tracked in `docs/platform/engineering/TECH_DEBT.md` §2.
* **`routes/genesis_router.py` NameError crashes** — Three missing imports added: `call_genesis_synthesis_llm` (from `domain.genesis_ai`), `create_masterplan_from_genesis` (from `domain.masterplan_factory`), `MasterPlan` (from `db.models`). A cascading `ModuleNotFoundError` was also resolved by creating `services/posture.py` stub (`determine_posture()`). `POST /genesis/synthesize` and `POST /genesis/lock` no longer crash with `NameError` before reaching business logic.
* **`calculate_twr()` ZeroDivisionError → HTTP 500** — Three-layer fix: (1) Pydantic `@validator("task_difficulty")` on `TaskInput` rejects `<= 0` at schema level with automatic 422; (2) `ValueError` guard added inside `calculate_twr()` as second line of defense; (3) `try/except ValueError/ZeroDivisionError` in `routes/main_router.py` maps both to HTTP 422 with a clear message. Route previously returned HTTP 500 on zero-difficulty input.

## Added

* `services/posture.py` — minimal stub for `determine_posture()`, required by `masterplan_factory.py` import chain.

## Documentation

* `docs/platform/engineering/TECH_DEBT.md` — §9 status updated for all three crash bugs; import path fix noted as resolved; genesis NameError crashes noted as resolved; TWR ValueError guard noted as resolved.

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
* All 7 remaining failures are intentional `_WILL_FAIL` security gap tests (no auth, wildcard CORS, no rate limiting) — tracked in `docs/platform/engineering/TECH_DEBT.md` §6 for Phase 2.

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

* `docs/platform/engineering/TECH_DEBT.md` — added §8 C++ Semantic Kernel Debt; added specific items to §1 (Structural), §2 (Schema/Migration), §3 (Testing)
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

