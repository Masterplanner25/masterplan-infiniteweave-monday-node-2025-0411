---
title: "Public Surface Audit"
last_verified: "2026-04-26"
api_version: "1.0"
status: current
owner: "platform-team"
---

# Public Surface Audit

## Function Audit

### `apps/automation/public.py`

| function | purpose | parameters | returns | imported by callers | bypass violations observed |
| --- | --- | --- | --- | --- | --- |
| `execute_automation_action` | Executes one automation payload through the automation service layer. | `payload: dict[str, Any]`, `db: Session` | `AutomationActionResult` | Yes: `apps/freelance/services/freelance_service.py` | None found |
| `sync_job_log_to_automation_log` | Mirrors a job log row into automation logs. | `db: Session`, `job_log_row: Any` | `None` | No cross-app callers found | None found |

### `apps/analytics/public.py`

| function | purpose | parameters | returns | imported by callers | bypass violations observed |
| --- | --- | --- | --- | --- | --- |
| `save_calculation` | Persists one analytics calculation result row. | `db: Session`, `metric_name: str`, `value: float`, `user_id: str | None` | `CalculationResult | None` | Yes: `apps/network_bridge/services/network_bridge_services.py` | `apps/search/routes/seo_routes.py`, `apps/network_bridge/routes/network_bridge_router.py` import `apps.analytics.services.calculations.calculation_services.save_calculation` directly |
| `get_user_kpi_snapshot` | Returns the latest KPI snapshot for one user. | `user_id: str`, `db: Session` | `UserKpiSnapshotDict | None` | Yes: `apps/agent/routes/agent_router.py`, `apps/agent/flows/agent_flows.py`, `apps/analytics/syscalls.py` | None found |
| `run_infinity_orchestrator` | Runs the analytics infinity orchestrator for one trigger event. | `user_id: str`, `trigger_event: str`, `db: Session` | `InfinityOrchestratorResult` | Yes: `apps/arm/services/deepseek/deepseek_code_analyzer.py` | None found |
| `get_user_score` | Returns one `UserScore` row as a plain dict. | `user_id: str`, `db: Session` | `UserScoreDict | None` | No caller imports found | None found |
| `get_user_scores` | Returns a batch of user score dicts keyed by user ID. | `user_ids: list[str]`, `db: Session` | `dict[str, UserScoreDict]` | Yes: `apps/social/__init__.py`, `apps/social/services/__init__.py`, `apps/social/services/social_service.py` | None found |
| `get_score_snapshot` | Returns the newest score snapshot for one drop point. | `drop_point_id: str`, `db: Session` | `ScoreSnapshotDict | None` | Yes: `apps/rippletrace/services/recommendation_engine.py` | None found |
| `list_score_snapshots` | Lists score snapshots for one drop point with optional filtering. | `drop_point_id: str`, `db: Session`, `limit`, `ascending`, `after_timestamp` | `list[ScoreSnapshotDict]` | Yes: `apps/rippletrace/services/prediction_engine.py`, `apps/rippletrace/services/narrative_engine.py`, `apps/rippletrace/services/learning_engine.py`, `apps/rippletrace/services/delta_engine.py` | None found |
| `list_score_snapshot_drop_point_ids` | Lists drop point IDs with enough snapshots for downstream analysis. | `db: Session`, `min_count: int` | `list[str]` | Yes: `apps/rippletrace/services/delta_engine.py` | None found |
| `create_score_snapshot` | Creates and flushes one score snapshot row, returning a plain dict. | `drop_point_id: str`, `db: Session`, `narrative_score: float`, `velocity_score: float`, `spread_score: float`, `timestamp`, `snapshot_id` | `ScoreSnapshotDict` | Yes: `apps/rippletrace/services/threadweaver.py` | None found |

### `apps/tasks/public.py`

| function | purpose | parameters | returns | imported by callers | bypass violations observed |
| --- | --- | --- | --- | --- | --- |
| `get_task_by_id` | Loads one task by primary key for a specific user. | `db: Session`, `task_id: int`, `user_id: str \| uuid.UUID \| None` | `Task \| None` | Yes: `apps/freelance/services/freelance_service.py` | None found |
| `queue_task_automation` | Dispatches automation for a task when automation metadata is present. | `db: Session`, `task: Task`, `user_id: str \| uuid.UUID \| None`, `reason: str` | `TaskAutomationDispatchResult \| None` | Yes: `apps/freelance/services/freelance_service.py` | None found |

## Cross-App Import Table

| app | caller | import path | is_public | action_needed |
| --- | --- | --- | --- | --- |
| automation | `apps/freelance/services/freelance_service.py` | `apps.automation.public.execute_automation_action` | yes | KEEP |
| automation | `apps/bridge/services/bridge_service.py` | `apps.automation.public.BridgeUserEvent` | yes | KEEP |
| automation | `apps/masterplan/services/masterplan_execution_service.py` | `apps.automation.public.AutomationLog` | yes | KEEP |
| automation | `apps/analytics/services/scoring/policy_adaptation_service.py` | `apps.automation.public.LoopAdjustment` | yes | KEEP |
| automation | `apps/analytics/services/scoring/kpi_weight_service.py` | `apps.automation.public.LoopAdjustment` | yes | KEEP |
| automation | `apps/analytics/services/integration/dependency_adapter.py` | `apps.automation.public.LoopAdjustment`, `apps.automation.public.UserFeedback` | yes | KEEP |
| automation | `apps/analytics/flows/analytics_flows.py` | `apps.automation.public.UserFeedback` | yes | KEEP |
| analytics | `apps/agent/routes/agent_router.py` | `apps.analytics.public.get_user_kpi_snapshot` | yes | KEEP |
| analytics | `apps/agent/flows/agent_flows.py` | `apps.analytics.public.get_user_kpi_snapshot` | yes | KEEP |
| analytics | `apps/arm/services/deepseek/deepseek_code_analyzer.py` | `apps.analytics.public.run_infinity_orchestrator` | yes | KEEP |
| analytics | `apps/network_bridge/services/network_bridge_services.py` | `apps.analytics.public.save_calculation` | yes | KEEP |
| analytics | `apps/social/__init__.py` | `apps.analytics.public.get_user_scores` | yes | KEEP |
| analytics | `apps/social/services/__init__.py` | `apps.analytics.public.get_user_scores` | yes | KEEP |
| analytics | `apps/social/services/social_service.py` | `apps.analytics.public.get_user_scores` | yes | KEEP |
| analytics | `apps/rippletrace/services/threadweaver.py` | `apps.analytics.public.create_score_snapshot` | yes | KEEP |
| analytics | `apps/rippletrace/services/recommendation_engine.py` | `apps.analytics.public.get_score_snapshot` | yes | KEEP |
| analytics | `apps/rippletrace/services/prediction_engine.py` | `apps.analytics.public.list_score_snapshots` | yes | KEEP |
| analytics | `apps/rippletrace/services/narrative_engine.py` | `apps.analytics.public.list_score_snapshots` | yes | KEEP |
| analytics | `apps/rippletrace/services/learning_engine.py` | `apps.analytics.public.list_score_snapshots` | yes | KEEP |
| analytics | `apps/rippletrace/services/delta_engine.py` | `apps.analytics.public.list_score_snapshot_drop_point_ids`, `apps.analytics.public.list_score_snapshots` | yes | KEEP |
| analytics | `apps/search/routes/seo_routes.py` | `apps.analytics.services.calculations.calculation_services.save_calculation` | no | MIGRATE |
| analytics | `apps/network_bridge/routes/network_bridge_router.py` | `apps.analytics.services.calculations.calculation_services.save_calculation` | no | MIGRATE |
| tasks | `apps/freelance/services/freelance_service.py` | `apps.tasks.public.get_task_by_id`, `apps.tasks.public.queue_task_automation` | yes | KEEP |
| tasks | `apps/masterplan/services/masterplan_execution_service.py` | `apps.tasks.public.Task` | yes | KEEP |
| tasks | `apps/masterplan/services/eta_service.py` | `apps.tasks.public.Task` | yes | KEEP |
