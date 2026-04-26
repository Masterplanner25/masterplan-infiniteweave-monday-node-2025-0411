---
title: "Cross-Domain Public Surface Contracts"
last_verified: "2026-04-26"
api_version: "1.0"
status: current
owner: "platform-team"
---

# Cross-Domain Public Surface Contracts

This document defines the contract for each domain app's public surface.
Cross-domain callers MUST import only from these public surfaces.
Direct imports from domain internals (services/, models/, routes/) are
a coupling violation documented in CROSS_DOMAIN_COUPLING.md.

## Contract Rules

1. Every public surface has a `PUBLIC_API_VERSION` constant.
   Callers may read it to detect version changes at runtime.

2. Minor-version bumps (1.0 → 1.1): new exports added. Old exports unchanged.
   Callers do not need to change.

3. Major-version bumps (1.x → 2.0): breaking change. At least one export
   was renamed, removed, or changed its return type. Callers MUST migrate.
   A migration guide is added to the surface's changelog section below.

4. Adding a new export: update __all__ and PUBLIC_API_VERSION (minor bump).
   Document in the changelog section of this file.

5. Removing or renaming an export: bump to next major version and write a
   migration guide in the changelog before merging.

## Automation Public Surface (`apps/automation/public.py`)

**Current version:** `PUBLIC_API_VERSION = "1.0"`
**Consumers:** `apps/bridge`, `apps/freelance`, `apps/masterplan`, `apps/analytics`

### Exports

| Name | Type | Parameters | Returns | Notes |
|------|------|-----------|---------|-------|
| `execute_automation_action` | function | `payload: dict[str, Any]`, `db: Session` | `AutomationActionResult` | Circuit-breaker protected wrapper over automation execution service. |
| `get_loop_adjustments` | function | `user_id: str \| UUID`, `db: Session`, `limit: int = 10`, `with_prediction_accuracy: bool = False`, `unevaluated_only: bool = False`, `decision_type: str \| None = None`, `with_actual_score: bool = False`, `with_expected_score: bool = False`, `order_by: str = "applied_desc"`, `for_update: bool = False` | `list[dict[str, Any]]` | Returns serialized rows, not ORM objects. Primary replacement for cross-domain `LoopAdjustment` querying. |
| `get_user_feedback` | function | `user_id: str \| UUID`, `db: Session`, `limit: int = 20` | `list[dict[str, Any]]` | Returns serialized feedback rows ordered by `created_at DESC`. |
| `create_loop_adjustment` | function | `db: Session`, `**kwargs` | `dict[str, Any]` | Creates and flushes one `LoopAdjustment` row, then serializes it. |

### Usage Example

```python
from apps.automation.public import get_loop_adjustments

rows = get_loop_adjustments(
    user_id,
    db,
    limit=10,
    with_prediction_accuracy=True,
)
```

### Changelog

#### v1.0 (2026-04-26)
- Initial documented version. All exports are as-built.
- Contract currently exposes only service functions in `__all__`; ORM model classes are not part of the documented public API.

## Analytics Public Surface (`apps/analytics/public.py`)

**Current version:** `PUBLIC_API_VERSION = "1.0"`
**Consumers:** `apps/agent`, `apps/arm`, `apps/network_bridge`, `apps/social`, `apps/rippletrace`

### Exports

| Name | Type | Parameters | Returns | Notes |
|------|------|-----------|---------|-------|
| `save_calculation` | function | `db: Session`, `metric_name: str`, `value: float`, `user_id: str \| None = None` | `CalculationResult \| None` | Returns an ORM row from analytics internals. This is the only exported non-dict service result. |
| `get_user_kpi_snapshot` | function | `user_id: str`, `db: Session` | `UserKpiSnapshotDict \| None` | Circuit-breaker protected KPI snapshot lookup. |
| `run_infinity_orchestrator` | function | `user_id: str`, `trigger_event: str`, `db: Session` | `InfinityOrchestratorResult` | Executes the analytics orchestrator through the public contract. |
| `get_user_score` | function | `user_id: str`, `db: Session` | `UserScoreDict \| None` | Returns the latest persisted score row as a plain dict. |
| `get_user_scores` | function | `user_ids: list[str]`, `db: Session` | `dict[str, UserScoreDict]` | Batch score lookup keyed by normalized user ID string. |
| `get_score_snapshot` | function | `drop_point_id: str`, `db: Session` | `ScoreSnapshotDict \| None` | Returns the newest score snapshot for one drop point. |
| `list_score_snapshots` | function | `drop_point_id: str`, `db: Session`, `limit: int \| None = None`, `ascending: bool = False`, `after_timestamp: datetime \| None = None` | `list[ScoreSnapshotDict]` | Snapshot history query for rippletrace-style consumers. |
| `list_score_snapshot_drop_point_ids` | function | `db: Session`, `min_count: int = 2` | `list[str]` | Returns drop point IDs with at least `min_count` snapshots. |
| `create_score_snapshot` | function | `drop_point_id: str`, `db: Session`, `narrative_score: float`, `velocity_score: float`, `spread_score: float`, `timestamp: datetime \| None = None`, `snapshot_id: str \| None = None` | `ScoreSnapshotDict` | Creates and flushes one score snapshot row. |

### Usage Example

```python
from apps.analytics.public import get_user_score

score = get_user_score(user_id, db)
if score is not None:
    master_score = score["master_score"]
```

### Changelog

#### v1.0 (2026-04-26)
- Initial documented version. All exports are as-built.

## Tasks Public Surface (`apps/tasks/public.py`)

**Current version:** `PUBLIC_API_VERSION = "1.0"`
**Consumers:** `apps/freelance`, `apps/masterplan`

### Exports

| Name | Type | Parameters | Returns | Notes |
|------|------|-----------|---------|-------|
| `get_task_by_id` | function | `db: Session`, `task_id: int`, `user_id: str \| uuid.UUID \| None` | `Task \| None` | Returns the owning domain ORM object for one task. |
| `queue_task_automation` | function | `db: Session`, `task: Task`, `user_id: str \| uuid.UUID \| None`, `reason: str` | `TaskAutomationDispatchResult \| None` | Dispatches task-linked automation work when metadata is present. |

### Usage Example

```python
from apps.tasks.public import get_task_by_id

task = get_task_by_id(db, task_id=42, user_id=user_id)
```

### Changelog

#### v1.0 (2026-04-26)
- Initial documented version. All exports are as-built.
- Current contract exposes service functions only; `Task` is used as a parameter/return type but is not exported in `__all__`.

## Identity Public Surface (`apps/identity/public.py`)

**Current version:** `PUBLIC_API_VERSION = "1.0"`
**Consumers:** `apps/masterplan`, `apps/analytics`

### Exports

| Name | Type | Parameters | Returns | Notes |
|------|------|-----------|---------|-------|
| `get_context_for_prompt` | function | `user_id: str`, `db: Session` | `str` | Safe wrapper around `IdentityService.get_context_for_prompt()`. Returns `""` on failure. |
| `get_recent_memory` | function | `user_id: str`, `db: Session`, `context: str = "infinity_loop"` | `list[dict[str, Any]]` | Safe wrapper around identity boot memory recall. |
| `get_user_metrics` | function | `user_id: str`, `db: Session` | `dict[str, Any]` | Safe wrapper around identity boot metrics lookup. |
| `observe_identity_event` | function | `user_id: str`, `db: Session`, `event_type: str`, `context: dict[str, Any]` | `bool` | Records an identity inference event. Returns `False` if unavailable. |

### Usage Example

```python
from apps.identity.public import get_context_for_prompt

identity_context = get_context_for_prompt(user_id, db)
```

### Changelog

#### v1.0 (2026-04-26)
- Initial documented version. All exports are as-built.
