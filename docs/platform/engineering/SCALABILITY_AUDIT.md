---
title: "Scalability Readiness Audit (Multi-Instance Risks)"
last_verified: "2026-04-18"
api_version: "1.0"
status: current
owner: "platform-team"
---
# Scalability Readiness Audit (Multi-Instance Risks)

## Summary
This audit focuses on process-level state, cross-instance consistency, and multi-worker behavior beyond background task leases.

## Findings (Current Risk)

1) In-memory request cache (per-process)
- Location: `AINDY/main.py` ? `FastAPICache.init(InMemoryBackend())`
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
- Location: `AINDY/services/task_services.py` + `AINDY/services/scheduler_service.py` + `AINDY/main.py`
- Risk: Previously — APScheduler started unconditionally on every instance regardless of DB lease; `start_background_tasks()` returned None and the lease check only gated a log message, not scheduler startup.
- Resolution (Sprint N+9, 2026-03-25): `start_background_tasks()` now returns `bool` (True = lease acquired). `main.py` lifespan calls `start_background_tasks()` first; `scheduler_service.start()` is only called when it returns True. A `background_lease_heartbeat` APScheduler job (60s interval) keeps the lease alive so it does not expire (TTL=120s) while the leader is running. `is_background_leader()` public helper + `GET /observability/scheduler/status` endpoint expose current state.
- Status: ? Resolved (Sprint N+9).

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

8) SchedulerEngine._waiting (per-process WAIT registry)
- Location: `kernel/scheduler_engine.py` ? `SchedulerEngine._waiting`
- Risk: Previously — `_waiting` was in-memory only. A FlowRun entering WAIT on Instance A would never resume if the resume event arrived on Instance B.
- Resolution (2026-04-07): `kernel/event_bus.py` introduces a Redis pub/sub distributed event bus. `notify_event(broadcast=True)` publishes to `aindy:scheduler_events` after the local scan. All instances subscribe and call `notify_event(broadcast=False)` on their own scheduler when a message arrives. Exactly-once execution is guaranteed by an atomic `UPDATE flow_runs SET status='executing' WHERE status='waiting'` DB claim — only the winning instance proceeds. All others return immediately. Startup rehydration re-registers all waiting FlowRun and EU callbacks on every instance so any instance can resume any waiting flow after a restart.
- Status: ? Resolved (2026-04-07). Remaining known limitation: collective restart race window (all instances restart simultaneously during an in-flight event) — requires Redis Streams for full elimination.

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
- `docs/platform/engineering/TECH_DEBT.md`: add cache inconsistency note + ARM config propagation note.
- `docs/deployment/DEPLOYMENT_MODEL.md`: note cache backend is per-process, not shared.

