---
title: "Public Surface Contracts"
last_verified: "2026-04-27"
api_version: "1.0"
status: current
owner: "platform-team"
---

# Public Surface Contracts

Cross-domain callers must import only from `apps/{app}/public.py`.
Public surfaces are thin wrappers over provider-owned internals and must be the
only supported Python-level contract between domain apps.

| Providing app | Public function | Consumers |
|---|---|---|
| `agent` | `dispatch_tool_request` | `automation` |
| `analytics` | `save_calculation` | `network_bridge`, `search` |
| `analytics` | `get_user_kpi_snapshot` | `agent` |
| `analytics` | `run_infinity_orchestrator` | `arm` |
| `analytics` | `get_user_score` | none recorded |
| `analytics` | `get_user_scores` | `social` |
| `analytics` | `get_score_snapshot` | `rippletrace` |
| `analytics` | `list_score_snapshots` | `rippletrace` |
| `analytics` | `list_score_snapshot_drop_point_ids` | `rippletrace` |
| `analytics` | `create_score_snapshot` | `rippletrace` |
| `arm` | `get_analysis_result` | none recorded |
| `arm` | `list_analysis_results` | `analytics` |
| `authorship` | `register_author` | `network_bridge` |
| `authorship` | `list_authors` | `network_bridge` |
| `automation` | `execute_automation_action` | `freelance` |
| `automation` | `sync_job_log_to_automation_log` | none recorded |
| `automation` | `get_loop_adjustments` | `analytics` |
| `automation` | `get_user_feedback` | `analytics` |
| `automation` | `create_loop_adjustment` | `analytics` |
| `automation` | `update_loop_adjustment` | `analytics` |
| `automation` | `create_bridge_user_event` | `bridge` |
| `automation` | `list_automation_logs` | `masterplan` |
| `automation` | `list_watcher_signals` | `analytics`, `tasks` |
| `automation` | `persist_watcher_signals` | `tasks` |
| `automation` | `ensure_learning_thresholds` | `rippletrace` |
| `automation` | `update_learning_thresholds` | `rippletrace` |
| `automation` | `create_learning_record` | `rippletrace` |
| `automation` | `get_latest_learning_record` | `rippletrace` |
| `automation` | `list_learning_records` | `rippletrace` |
| `automation` | `list_learning_record_drop_point_ids` | `rippletrace` |
| `automation` | `update_learning_record` | `rippletrace` |
| `identity` | `get_context_for_prompt` | `masterplan` |
| `identity` | `get_recent_memory` | `analytics` |
| `identity` | `get_user_metrics` | `analytics` |
| `identity` | `observe_identity_event` | `masterplan` |
| `masterplan` | `calculate_eta` | none recorded |
| `masterplan` | `call_genesis_llm` | none recorded |
| `masterplan` | `call_genesis_synthesis_llm` | none recorded |
| `masterplan` | `create_masterplan_from_genesis` | none recorded |
| `masterplan` | `determine_posture` | none recorded |
| `masterplan` | `get_masterplan_execution_status` | none recorded |
| `masterplan` | `handle_score_updated` | none recorded |
| `masterplan` | `posture_description` | none recorded |
| `masterplan` | `recalculate_all_etas` | none recorded |
| `masterplan` | `sync_masterplan_tasks` | none recorded |
| `masterplan` | `update_goal_progress` | none recorded |
| `masterplan` | `validate_draft_integrity` | none recorded |
| `rippletrace` | `add_drop_point` | none recorded |
| `rippletrace` | `add_ping` | none recorded |
| `rippletrace` | `build_trace_graph` | none recorded |
| `rippletrace` | `generate_trace_insights` | none recorded |
| `rippletrace` | `get_all_drop_points` | none recorded |
| `rippletrace` | `get_all_pings` | none recorded |
| `rippletrace` | `get_recent_ripples` | none recorded |
| `rippletrace` | `get_ripples` | none recorded |
| `rippletrace` | `get_upstream_causes` | none recorded |
| `rippletrace` | `link_events` | none recorded |
| `rippletrace` | `log_ripple_event` | `network_bridge` |
| `rippletrace` | `update_strategy_score` | none recorded |
| `search` | `extract_flow_error` | `freelance` |
| `search` | `is_circuit_open_detail` | `freelance` |
| `search` | `build_ai_provider_unavailable_payload` | `freelance` |
| `social` | `adapt_linkedin_metrics` | `analytics` |
| `social` | `get_social_performance_signals` | `analytics` |
| `tasks` | `get_task_by_id` | `freelance` |
| `tasks` | `queue_task_automation` | none recorded |
| `tasks` | `update_task_status` | `freelance` |
| `tasks` | `queue_task_automation_by_id` | `freelance` |
| `tasks` | `count_tasks` | `masterplan` |
| `tasks` | `count_tasks_completed_since` | `masterplan` |
| `tasks` | `list_tasks_for_masterplan` | `masterplan` |
| `tasks` | `delete_tasks_by_ids` | `masterplan` |
