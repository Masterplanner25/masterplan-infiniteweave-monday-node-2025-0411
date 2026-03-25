# TECH DEBT — A.I.N.D.Y.

## Closed

### ✅ INFINITY_ALGORITHM §Phase v4: unified execution loop (closed 2026-03-24)
`services/infinity_service.py` created. Event-driven scoring loop: task completion,
watcher session_ended, ARM analysis, and daily scheduler all trigger score recalculation.
Score persisted in `user_scores` (latest) and `score_history` (time series).

### ✅ INFINITY_ALGORITHM_SUPPORT §Phase v3: watcher signals → scoring (closed 2026-03-24)
Focus quality KPI calculator reads watcher session signals.
Note: `WatcherSignal` lacks `user_id` — focus_quality returns neutral (50.0) until
per-user watcher association is implemented (Sprint N+4 agentics task).

### ✅ Flow Engine has no UI (closed 2026-03-23)
FlowEngineConsole.jsx added to Dashboard Execution tab. All flow runs, automation logs,
registered flows/nodes, and learned strategies are now visible and controllable from the UI.

---

## Open

### ⏳ Strategy seeding — system strategies not seeded yet
The Strategies tab in FlowEngineConsole will show an empty state until the engine generates
strategies organically through ARM analysis, Genesis sessions, and task completions.
No `/flows/strategies` endpoint exists yet — the panel gracefully handles the 404.

**To close:** Implement `GET /flows/strategies` endpoint querying the `strategies` table,
then optionally seed system strategies for each registered workflow type.

### ⏳ apscheduler not installed in test environment
`services/scheduler_service.py` imports `apscheduler` at module level, causing 266+ test
errors when the `client` fixture tries to import `main`. All router-level endpoint tests
that need the test client fail with `ModuleNotFoundError: No module named 'apscheduler'`.

**To close:** Add `apscheduler` to `requirements.txt` / test environment, or lazy-import it
inside functions rather than at module level.

### ⏳ WatcherSignal lacks user_id — focus_quality scores are system-wide
`WatcherSignal` has no `user_id` column. The watcher uses API-key auth, so signals
are not associated with individual users. `calculate_focus_quality()` currently scores
system-wide sessions (returns neutral 50.0 when no session data). This affects all users'
focus KPI equally, reducing scoring accuracy.

**To close:** (a) Add `user_id` (nullable) to `watcher_signals` table, (b) update
`SignalPayload` to accept optional `user_id`, (c) update `_trigger_eta_update` to pass
`user_id` when known. This is a Sprint N+4 agentics prerequisite.

### ✅ Sprint N+4 — First Agent (agentics Phase 1+2) (closed 2026-03-24)
`services/agent_tools.py`, `services/agent_runtime.py`, `routes/agent_router.py`,
`client/src/components/AgentConsole.jsx`. Goal → GPT-4o plan → trust gate → execute.
9 tools, 3 DB tables, 9 endpoints, 70 tests.

---

## Open (continued)

### ⏳ Sprint N+5 — Agentics Phase 3: Nodus Integration (Determinism)
Replace Python execution loop in agent_runtime.py with PersistentFlowRunner-backed
deterministic execution. Wire A.I.N.D.Y. tools as Nodus tasks for retries + checkpoints.

### ⏳ Score-driven agent suggestions (INFINITY_ALGORITHM §Phase v5)
Use Infinity score KPI data to influence agent plan prioritization and tool selection.
Requires agent runtime to be stable (Phase 1+2 complete ✅).
