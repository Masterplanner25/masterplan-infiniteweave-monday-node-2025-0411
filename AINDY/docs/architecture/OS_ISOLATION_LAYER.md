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

---

## 4. SchedulerEngine

Handles priority-based scheduling and WAIT/RESUME flow control.

```python
from kernel.scheduler_engine import get_scheduler_engine

se = get_scheduler_engine()

# Queue an execution unit for scheduling
se.schedule(execution_unit_id, priority=5)

# Signal a waiting execution to resume
se.resume(execution_unit_id, signal_payload={...})

# Check current run state
state = se.get_state(execution_unit_id)
```

### WAIT / RESUME Pattern

Nodus flows can pause execution and wait for an external signal:

1. Flow node calls `sys("sys.v1.event.wait", {"event_type": "approval.granted"})`.
2. Dispatcher sets execution unit status to `WAIT`.
3. When the event arrives, `SchedulerEngine.resume()` is called with the event payload.
4. Execution resumes from the next node.

This enables human-in-the-loop and async integration patterns without blocking threads.

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

## 9. Key Files

| File | Role |
|------|------|
| `kernel/tenant_context.py` | `TenantContext`, core OS layer primitives |
| `kernel/resource_manager.py` | `ResourceManager`, quota check + usage recording |
| `kernel/scheduler_engine.py` | `SchedulerEngine`, priority scheduling, WAIT/RESUME |
| `kernel/syscall_dispatcher.py` | OS layer integration points (Steps 5, 6, 11) |
| `routes/platform_router.py` | `GET /platform/tenants/{id}/usage` |
| `tests/unit/test_os_layer.py` | 64 OS isolation tests |
