# Scalability Readiness Audit (Multi-Instance Risks)

## Summary
This audit focuses on process-level state, cross-instance consistency, and multi-worker behavior beyond background task leases.

## Findings (Current Risk)

1) In-memory request cache (per-process)
- Location: `AINDY/main.py` → `FastAPICache.init(InMemoryBackend())`
- Risk: Cache is per-process only; multi-instance deployments yield inconsistent cache results and uneven load distribution.
- Impact: Stale or divergent cached results across instances; no cross-instance invalidation.
- Status: Open (no shared cache backend configured).

2) MongoDB client singleton (process-level)
- Location: `AINDY/db/mongo_setup.py`
- Risk: Singleton is per-process, but acceptable for Mongo usage; no cross-instance coupling.
- Impact: None for correctness; only operational if Mongo is down (startup can fail).
- Status: Acceptable (documented in `SYSTEM_SPEC.md`).

3) ARM analyzer singleton (process-level)
- Location: `AINDY/routes/arm_router.py`
- Risk: Cached analyzer config is per-process; config updates require per-process reload.
- Impact: Config update in one instance won’t affect others until they receive requests (or restart).
- Status: Open (multi-instance propagation).

4) OpenAI embedding client singleton
- Location: `AINDY/services/embedding_service.py`
- Risk: Per-process; acceptable. No cross-instance inconsistency.
- Impact: None for correctness.
- Status: Acceptable.

5) Background task runner isolation
- Location: `AINDY/services/task_services.py` + DB lease
- Risk: Lease prevents duplicate task runner start, but other background work (if added later) could still run without lease checks.
- Impact: Duplicate background execution if other services spawn threads without leases.
- Status: Partially mitigated.

6) Gateway state persistence
- Location: `AINDY/server.js` + `/network_bridge/authors`
- Risk: None for persistence (now DB-backed).
- Impact: Improved; no in-memory gateway state.
- Status: Resolved.

7) MemoryTrace in-memory shadow state
- Location: `AINDY/bridge/bridge.py`
- Risk: Divergent per-process state; not shared between instances.
- Impact: Inconsistent memory view; already captured in TECH_DEBT.
- Status: Resolved (deprecated in-memory trace with runtime warning).

## Actionable Recommendations (No redesign)
- Replace `InMemoryBackend` with Redis/DB cache if cache consistency is required.
- Document that ARM config changes require restart or reload across instances.
- Ensure any new background workers use DB leases like task_services.

## Files to Review / Track
- `AINDY/main.py` (cache backend)
- `AINDY/db/mongo_setup.py` (singleton)
- `AINDY/routes/arm_router.py` (singleton analyzer)
- `AINDY/services/embedding_service.py` (singleton client)
- `AINDY/services/task_services.py` (lease-gated runner)
- `AINDY/bridge/bridge.py` (MemoryTrace in-memory state)

## Proposed Doc Updates
- `docs/roadmap/TECH_DEBT.md`: add cache inconsistency note + ARM config propagation note.
- `docs/engineering/DEPLOYMENT_MODEL.md`: note cache backend is per-process, not shared.

