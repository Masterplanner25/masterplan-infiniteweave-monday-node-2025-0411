# Multi-Instance Flow Resume — Architecture and Validation

## Problem

`SchedulerEngine._waiting` is process-local. A flow registered on Instance A cannot
be resumed by Instance B because B has no entry in its `_waiting` dict.

## Solution

Replace Python lambda callbacks with serializable `ResumeSpec` dicts stored in Redis.
Any instance can reconstruct the callback from the spec and execute the resume.

## Data Flow

`register_wait(run_id, ...)`

- `_waiting[run_id] = {callback: lambda, ...}`  local, fast path
- Redis `SET aindy:wait:{run_id}` -> JSON(spec)  cross-instance path
- `WaitingFlowRun` DB row  crash recovery path

`notify_event(event_type)`

- scan `_waiting` -> match -> enqueue -> Redis `DEL`  local (`O(waiting)`)
- scan Redis `aindy:wait:*` -> match DB row  cross-instance
- Redis `DEL` (atomic claim)
- `build_callback_from_spec()`
- enqueue

## Failure Modes and Mitigations

| Scenario | Behavior |
|----------|----------|
| Redis unavailable | Cross-instance path silently skipped; local `_waiting` works |
| Two instances race on same `run_id` | Redis `DEL` is atomic; only one gets return=1 |
| Instance crashes before Redis write | DB fallback in `flow_run_rehydration.py` |
| Stale Redis key (DB row deleted) | `_load_wait_entry_from_db()` returns `None`; spec skipped |
| `build_callback_from_spec()` fails | `log.warning` + skip; other runs proceed |
| `get_all_specs()` Redis error | `log.warning` + return `{}`; no cross-instance resume this cycle |

## Operational Notes

- Redis key TTL: 86400 seconds (24 hours). Flows waiting longer than 24h will not
  be cross-instance resumable and will rely on startup rehydration from DB.
  Increase TTL in `redis_wait_registry.py` if your workflows require longer waits.

- Key namespace: `aindy:wait:*`. Ensure Redis memory limits account for pending flows.
  Each spec is roughly 200 bytes; 10,000 concurrent waiting flows is roughly 2 MB.

- The DB row (`WaitingFlowRun`) remains authoritative for `event_type` and persisted
  metadata. Redis holds only the resume spec (who to call). This separation keeps
  Redis keys minimal and avoids duplication drift.

## Production Readiness Checklist

Before deploying to multi-instance production:

- [ ] `AINDY_REDIS_URL` configured in environment (required for cross-instance resume)
- [ ] `fakeredis` installed in dev/CI: `pip install fakeredis`
- [ ] Run `test_multi_instance_resume.py` tests and confirm they pass
- [ ] Redis key TTL (86400s) is acceptable for your longest-running flows
- [ ] Monitor Redis memory usage: `redis-cli info memory`
- [ ] Set Redis eviction policy to `noeviction` or `allkeys-lru`, not `volatile-lru`
- [ ] Verify `WaitingFlowRun` cleanup: rows deleted when flows complete
- [ ] Verify startup rehydration (`flow_run_rehydration.py`) still runs on cold start
- [ ] Load test Redis scan performance under 10K+ concurrent waiting flows and tune SCAN count if needed

## What This Does NOT Solve

- Flows waiting longer than Redis TTL on a crashed instance: recovered by DB rehydration
- Redis itself crashing: falls back to local `_waiting` on surviving instances
- Postgres `WaitingFlowRun` table unavailable: startup rehydration fails; Redis path is unaffected
