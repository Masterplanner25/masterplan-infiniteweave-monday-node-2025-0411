# OS Isolation Layer

The OS Isolation Layer provides tenant isolation, resource quota enforcement, and priority-based execution scheduling for A.I.N.D.Y. execution units (AgentRuns, flow runs). It sits between the syscall dispatcher and raw handler execution.

---

## 1. Overview

```
SyscallDispatcher.dispatch()
    │
    ├─ Step 5: tenant isolation (user_id check)
    ├─ Step 6: quota check → ResourceManager.check_quota()
    │
    ▼
Handler executes
    │
    ├─ Step 11: usage record → ResourceManager.record_usage()
    └─ ...
```

The OS layer is **non-fatal by design** — all `ResourceManager` and `SchedulerEngine` calls are wrapped in `try/except`. A broken quota system never kills a real execution.

---

## 2. TenantContext

Defined in `kernel/tenant_context.py`.

```python
@dataclass
class TenantContext:
    tenant_id:   str         # matches user_id
    quota_group: str         # e.g. "default", "premium"
    priority:    int         # 1 (low) to 10 (high)
    metadata:    dict        # optional extra fields
```

Every execution unit carries a `TenantContext`. It is resolved from `SyscallContext.user_id` at dispatch time.

---

## 3. ResourceManager

Manages per-execution-unit quotas and usage tracking.

```python
from kernel.resource_manager import get_resource_manager

rm = get_resource_manager()

# Check if an execution unit is within quota
ok, reason = rm.check_quota(execution_unit_id)
# ok=False → reason is a human-readable string returned in the error envelope

# Record actual usage after handler completes
rm.record_usage(execution_unit_id, {
    "syscall_count": 1,
    "cpu_time_ms": 42,
})
```

### Quota Fields (on ExecutionUnit model)

| Column | Type | Description |
|--------|------|-------------|
| `tenant_id` | String | Owning tenant |
| `cpu_time_ms` | Integer | Accumulated CPU time |
| `memory_bytes` | Integer | Peak memory usage |
| `syscall_count` | Integer | Total syscalls dispatched |
| `priority` | Integer | Scheduling priority (1–10) |
| `quota_group` | String | Quota tier (e.g. `"default"`, `"premium"`) |

These 6 columns were added to `ExecutionUnit` in the OS Layer sprint migration.

### Quota Enforcement

When `check_quota()` returns `(False, reason)`, the dispatcher returns an error envelope immediately — no handler runs. This prevents runaway executions from consuming unbounded resources.

### Cross-Instance Limitation

**ResourceManager is a per-process in-memory singleton.**

In a multi-instance deployment, each server instance maintains its own `_active_eus` dict and per-EU usage records. Concurrent execution quota (`MAX_CONCURRENT_PER_TENANT`) is enforced within a single process only.

A tenant can exceed the configured limit by distributing requests across N instances â€” each instance will allow up to `MAX_CONCURRENT_PER_TENANT` executions independently.

CPU time and memory quota are per-execution and correctly reflect usage within the process that runs the execution. They are not affected by this limitation.

**To enforce concurrent execution limits globally in a multi-instance deployment, the `can_execute()` / `mark_started()` / `mark_completed()` methods require Redis-backed atomic counters.** This is tracked as a known gap. Until resolved, treat `MAX_CONCURRENT_PER_TENANT` as a per-instance limit, not a per-tenant global limit.

---

## 4. SchedulerEngine

Handles priority-based scheduling and WAIT/RESUME flow control.

```python
from kernel.scheduler_engine import get_scheduler_engine, ScheduledItem

se = get_scheduler_engine()

# Queue an execution unit
item = ScheduledItem(
    execution_unit_id="eu-abc",
    tenant_id="user-123",
    priority="normal",
    run_callback=lambda: runner.resume(run_id),
    run_id="run-uuid",
)
se.enqueue(item)
se.schedule()  # drain up to MAX_PER_SCHEDULE_CYCLE items

# Register a WAIT — flow engine calls this internally
se.register_wait(run_id, wait_for_event="task.completed", ...)

# Signal a waiting run to resume (via distributed path)
from kernel.event_bus import publish_event
publish_event("task.completed", correlation_id="chain-abc")
```

### WAIT / RESUME Pattern

Nodus flows can pause execution and wait for an external signal:

1. Flow node calls `sys("sys.v1.event.wait", {"event_type": "approval.granted"})`.
2. `SchedulerEngine.register_wait(run_id, ...)` stores the callback in `_waiting`.
3. When the event fires, `publish_event(event_type)` is called.
4. `notify_event()` matches `_waiting` entries, deletes them under lock, and re-enqueues callbacks.
5. On resume, `PersistentFlowRunner.resume()` claims the FlowRun atomically before executing.

This enables human-in-the-loop and async integration patterns without blocking threads.

### Priority Levels

| Constant | Value |
|----------|-------|
| `PRIORITY_HIGH` | `"high"` |
| `PRIORITY_NORMAL` | `"normal"` |
| `PRIORITY_LOW` | `"low"` |

Round-robin fairness within each priority level prevents any single tenant from starving others.

---

## 5. ExecutionUnit Columns

The OS layer added these columns to the `ExecutionUnit` model (migration in OS Layer sprint):

| Column | Description |
|--------|-------------|
| `tenant_id` | Owning tenant/user |
| `cpu_time_ms` | Accumulated CPU time in ms |
| `memory_bytes` | Peak memory bytes |
| `syscall_count` | Total syscall invocations |
| `priority` | Scheduling priority (1=low, 10=high) |
| `quota_group` | Quota tier name |

---

## 6. Tenant Isolation Enforcement

The dispatcher enforces tenant isolation at Step 5:

```python
if not context.user_id:
    return error_envelope("TENANT_VIOLATION: syscall requires authenticated tenant context")
```

This ensures:
- No anonymous executions can reach any handler.
- Every syscall is attributable to a specific tenant.
- Cross-tenant data access is structurally impossible within the dispatcher path.

Route-level isolation (user_id scoping on queries) is enforced separately in DAO methods and API handlers.

---

## 7. OS Layer API

```
GET /platform/tenants/{tenant_id}/usage
```

Auth: JWT or Platform API key with `memory.read` scope.

Returns current quota usage for a tenant's active execution unit:

```json
{
    "tenant_id": "user-abc",
    "quota_group": "default",
    "syscall_count": 42,
    "cpu_time_ms": 1240,
    "memory_bytes": 0,
    "priority": 5
}
```

---

## 8. Non-Fatal Integration Pattern

All OS layer calls in the dispatcher use this pattern:

```python
try:
    rm = _get_rm()
    quota_ok, quota_reason = rm.check_quota(context.execution_unit_id)
    if not quota_ok:
        return self._error_envelope(name, context, quota_reason, ...)
except Exception as _rm_exc:
    logger.debug("[SyscallDispatcher] resource quota check skipped: %s", _rm_exc)
```

The `try/except` ensures that if `ResourceManager` is unavailable (e.g., test environment without OS layer tables), execution continues rather than failing. Quota enforcement is a best-effort guarantee, not a hard blocker in degraded environments.

---

## 9. Distributed Event Bus

All resume events go through a single public API function that guarantees distributed delivery:

```python
from kernel.event_bus import publish_event

# Emit to all instances — the only correct way to fire a resume event
publish_event("task.completed", correlation_id="chain-abc")
```

**Execution path:**
1. `publish_event()` calls `SchedulerEngine.notify_event(broadcast=True)`.
2. Local `_waiting` scan runs immediately; matched callbacks are enqueued.
3. Event is published to a Redis pub/sub channel (`aindy:scheduler_events`).
4. All other instances receive the broadcast and call `notify_event(broadcast=False)` on their local scheduler.
5. `broadcast=False` suppresses re-publication, preventing infinite loops.

**Duplicate execution prevention:**
- `_waiting` entries are deleted under lock before any enqueue (within-instance guard).
- `PersistentFlowRunner.resume()` claims the `FlowRun` atomically: `UPDATE WHERE status='waiting'`. Only the winner proceeds; all others get `rowcount=0` and return `SKIPPED`.

**Fault tolerance:**
- Redis unavailable → local delivery only (no exception propagates).
- Subscriber thread reconnects with exponential backoff (1 s → 30 s cap).
- `AINDY_EVENT_BUS_ENABLED=false` disables the bus entirely for single-instance deployments.

**Configuration:**

| Variable | Default | Description |
|----------|---------|-------------|
| `AINDY_REDIS_URL` | `redis://localhost:6379/0` | Redis connection URL |
| `AINDY_EVENT_BUS_CHANNEL` | `aindy:scheduler_events` | Pub/sub channel name |
| `AINDY_EVENT_BUS_ENABLED` | `true` | Set to `false` for local-only mode |

## 10. FlowRun Execution Guarantee

The FlowRun claim is the single gatekeeper for execution ordering across all instances:

```
Event fires on any instance
  → publish_event(event_type)
  → notify_event() wakes matching _waiting callbacks on this instance
  → Redis broadcast wakes _waiting callbacks on all other instances
  → All instances race to claim: UPDATE flow_runs SET status='executing' WHERE status='waiting'
  → Winner (rowcount=1): EU resume → flow execution
  → Losers (rowcount=0): immediate return — no side effects
```

Callback ordering within the winning instance:

1. **FlowRun atomic claim** — `UPDATE WHERE status='waiting'`
2. **EU status transition** — `waiting → resumed → executing` (only if claim won)
3. **Flow execution** — `PersistentFlowRunner.resume()` (only if claim won)

The EU callback registered by `rehydrate_waiting_eus()` includes an ownership guard: if the FlowRun is no longer `"waiting"` when it fires, the EU callback skips — avoiding bookkeeping side effects on the losing instance.

## 11. Key Files

| File | Role |
|------|------|
| `kernel/tenant_context.py` | `TenantContext`, core OS layer primitives |
| `kernel/resource_manager.py` | `ResourceManager`, quota check + usage recording |
| `kernel/scheduler_engine.py` | `SchedulerEngine`, priority scheduling, WAIT/RESUME, distributed broadcast |
| `kernel/event_bus.py` | Redis pub/sub distributed event bus; `publish_event()` public API |
| `kernel/syscall_dispatcher.py` | OS layer integration points (Steps 5, 6, 11) |
| `core/flow_run_rehydration.py` | Startup rehydration of FlowRun WAIT callbacks |
| `core/wait_rehydration.py` | Startup rehydration of EU WAIT callbacks |
| `routes/platform_router.py` | `GET /platform/tenants/{id}/usage` |
| `tests/unit/test_os_layer.py` | OS isolation + capacity event tests |
| `tests/unit/test_event_bus.py` | Distributed event bus tests (26 tests) |
