# User-ID Scoping Audit

**Date:** 2026-04-20  
**Scope:** All `db.query(...)` calls in `apps/*/services/*.py` and `apps/automation/flows/*.py`

A.I.N.D.Y. is a single-tenant-per-user system (`tenant_id == user_id`). Every domain
model that holds user data must filter queries by `user_id` when a user context is
available.  Omitting the filter allows one user's authenticated request to read or
mutate another user's data.

---

## CRITICAL — Fixes Applied

### 1. `apps/tasks/services/task_service.py:831` — `_check_reminders_once`

**Before:** `db.query(Task).all()` — returned ALL users' tasks.  
**After:** Optional `user_id` kwarg added. When provided, adds `.filter(Task.user_id == user_id)` before `.all()`. Default (`None`) preserves the existing background-job behavior of scanning all users.

```python
# added parameter: *, user_id=None
q = db.query(Task)
if user_id is not None:
    q = q.filter(Task.user_id == user_id)
tasks = q.all()
```

**Test:** `tests/unit/test_user_id_scoping.py::TestCheckRemindersUserScoping`

---

### 2. `apps/tasks/services/task_service.py:848` — `_handle_recurrence_once`

**Before:** `db.query(Task).filter(Task.status == "completed").all()` — all users, no tenant scope.  
**After:** Optional `user_id` kwarg added. When provided, chains `.filter(Task.user_id == user_id)` after the status filter.

```python
# added parameter: *, user_id=None
q = db.query(Task).filter(Task.status == "completed")
if user_id is not None:
    q = q.filter(Task.user_id == user_id)
tasks = q.all()
```

**Test:** `tests/unit/test_user_id_scoping.py::TestHandleRecurrenceUserScoping`

---

### 3. `apps/masterplan/services/goal_service.py:91` — `update_goal_progress`

**Before:** `db.query(Goal).filter(Goal.id == goal_id).first()` — any caller knowing a `goal_id` could update any user's goal.  
**After:** Optional `user_id` kwarg added. When provided, adds `.filter(Goal.user_id == normalize_uuid(user_id))` — cross-user updates return `None`.

```python
# added parameter: *, user_id: str | None = None
q = db.query(Goal).filter(Goal.id == goal_id)
if user_id is not None:
    q = q.filter(Goal.user_id == normalize_uuid(user_id))
goal = q.first()
```

**Test:** `tests/unit/test_user_id_scoping.py::TestUpdateGoalProgressUserScoping`

---

## ACCEPTABLE — Intentionally Global Queries

These queries were reviewed and confirmed to be correctly unscoped.

| Location | Model | Reason |
|---|---|---|
| `apps/analytics/bootstrap.py:152` | `User` | Admin bootstrap — intentionally enumerates all users to seed scores |
| `apps/masterplan/services/eta_service.py:141` | `MasterPlan` | `recalculate_all_etas()` is an APScheduler batch job; iterates all plans and correctly passes `plan.user_id` to per-plan ETA calculation |
| `apps/automation/flows/dashboard_autonomy_flows.py:50` | `SystemHealthLog` | Platform-level health log — not user-scoped by design |
| `apps/masterplan/services/masterplan_factory.py:35` | `MasterPlan` | `else` branch fires only when `user_id=None`; all production callers supply `user_id`, triggering the already-scoped `if` branch on line 33 |
| `apps/automation/services/job_log_sync_service.py:50` | `AutomationLog` | Internal sync job that looks up logs by system-assigned ID; user_id is not meaningful in this context |
| `apps/automation/services/automation_execution_service.py:257` | `AutomationLog` | Internal polling by log ID; caller controls which ID is queried |
| `apps/masterplan/services/masterplan_execution_service.py:95` | `AutomationLog` | Filtered by `user_id` on line 96: `.filter(AutomationLog.user_id == owner_user_id)` |

---

## Already Correctly Scoped — No Action Needed

These locations were flagged in the initial report but are already scoped:

| Location | Evidence |
|---|---|
| `apps/analytics/services/infinity_service.py:146,155,169,211,216` | All Task/WatcherSignal queries include `Task.user_id == user_id` / `WatcherSignal.user_id == user_id` |
| `apps/masterplan/services/masterplan_service.py:19,101,152,185` | All MasterPlan queries include `MasterPlan.user_id == user_id` |
| `apps/masterplan/services/eta_service.py:34,61,77,86` | All Task/MasterPlan queries include user_id via `require_user_id(user_id)` |
| `apps/masterplan/services/masterplan_execution_service.py:24,67,79` | All Task queries include `Task.user_id == owner_user_id` |
| `apps/masterplan/services/goal_service.py:45` | `get_active_goals` filters by `Goal.user_id == normalize_uuid(user_id)` |

---

## Enforcement Pattern

All service functions that access user-owned data must:
1. Accept `user_id` as a parameter (keyword-only where possible)
2. Apply `.filter(Model.user_id == normalized_user_id)` before `.first()` / `.all()`
3. Return `None` or `[]` when the user_id filter excludes the record (not 403 — that is the route layer's responsibility)

The fail-safe default (`user_id=None` → no filter added) is used only for background
jobs and internal system services where a user context is genuinely unavailable.
