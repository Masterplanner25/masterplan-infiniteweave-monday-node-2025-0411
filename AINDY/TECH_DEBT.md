# TECH DEBT — A.I.N.D.Y.

## Closed

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
