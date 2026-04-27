---
title: "Relational Integrity Audit"
last_verified: "2026-04-26"
api_version: "1.0"
status: current
owner: "platform-team"
---

# Relational Integrity Audit - 2026-04-26

## Fixed (this sprint)
| Table | Column | Constraint added | Migration |
| --- | --- | --- | --- |
| `agent_steps` | `run_id` | `fk_agent_steps_run_id_agent_runs` (`ON DELETE CASCADE`) | `4d6e8f0a1b2c_add_agent_graph_foreign_keys.py` |
| `agent_events` | `run_id` | `fk_agent_events_run_id_agent_runs` (`ON DELETE CASCADE`) | `4d6e8f0a1b2c_add_agent_graph_foreign_keys.py` |
| `agent_capability_mappings` | `capability_id` | `fk_agent_capability_mappings_capability_id_capabilities` (`ON DELETE CASCADE`) | `4d6e8f0a1b2c_add_agent_graph_foreign_keys.py` |
| `agent_capability_mappings` | `agent_run_id` | `fk_agent_capability_mappings_agent_run_id_agent_runs` (`ON DELETE CASCADE`) | `4d6e8f0a1b2c_add_agent_graph_foreign_keys.py` |
| `agent_runs` | `flow_run_id` | `fk_agent_runs_flow_run_id_flow_runs` (`ON DELETE SET NULL`) | `5e7f901b2c3d_add_flow_link_foreign_keys.py` |
| `execution_units` | `flow_run_id` | `fk_execution_units_flow_run_id_flow_runs` (`ON DELETE SET NULL`) | `5e7f901b2c3d_add_flow_link_foreign_keys.py` |
| `waiting_flow_runs` | `run_id` | `fk_waiting_flow_runs_run_id_flow_runs` (`ON DELETE CASCADE`) | `5e7f901b2c3d_add_flow_link_foreign_keys.py` |

## Deferred (acceptable for now)
| Table | Column | Reason deferred |
| --- | --- | --- |
| `nodus_trace_events` | `execution_unit_id` | Child column is `String(128)` while `execution_units.id` is UUID; tightening this safely requires a type migration and backfill, not a pure FK add. |
| `nodus_trace_events` | `user_id` | Ownership FK is lower risk than the execution-graph orphan paths fixed this sprint; defer to a user-ownership cleanup pass. |
| `nodus_scheduled_jobs` | `user_id` | Missing ownership FK, but soft-deleted scheduler rows are lower risk than run-graph integrity and need a clear delete policy before enforcing `SET NULL` or `RESTRICT`. |
| `flow_runs` | `job_log_id` | Historical `automation_log_id` FK was intentionally removed during rename; restoring a hard link to `job_logs` needs an explicit retention policy for audit rows. |
| `autonomy_decisions` | `job_log_id` | Same retention-policy question as `flow_runs.job_log_id`; not a core parent-child ownership edge. |
| `execution_units` | `source_id` | Explicitly polymorphic by design (`operation`, `agent_run`, `flow_run`, `job`); cannot be represented as a single FK. |
| `waiting_flow_runs` | `eu_id` | Column width/type does not match `execution_units.id` UUID storage and the wait registry remains valid without a hard EU link. |
| `agent_runs` | `replayed_from_run_id` | Historical provenance link rather than a lifecycle owner; hardening it could block replay of imported/legacy runs. |
| `learning_records` | `drop_point_id` | Analytical lineage table, lower operational risk than execution tables, and likely needs orphan cleanup before any `drop_points` FK is safe. |
| `score_snapshots` | `drop_point_id` | Same as `learning_records.drop_point_id`; telemetry lineage rather than lifecycle ownership. |
| `playbooks` | `strategy_id` | Legacy RippleTrace strategy linkage uses string IDs and has no agreed delete behavior yet. |
| `analysis_results` | `session_id` | No verified parent session table declaration in the audited ARM models to anchor a safe DB FK. |
| `code_generations` | `session_id` | Same as `analysis_results.session_id`; parent session contract is not declared in the audited schema layer. |
| `search_history` | `user_id` | Missing ownership FK, but lower risk than core orchestration tables and would require an app-specific ownership policy review. |

## Not applicable
| Table | Explanation |
| --- | --- |
| `users` | Root ownership table; no parent FK required. |
| `agents` | `owner_user_id` already has a DB FK to `users.id`. |
| `agent_registry` | Registry table has no parent reference columns. |
| `agent_trust_settings` | `user_id` already has a DB FK to `users.id`. |
| `api_keys` | `user_id` already has a DB FK and ORM delete-orphan cascade. |
| `background_task_leases` | Lease table has no parent reference columns. |
| `capabilities` | Root lookup table; no parent FK required. |
| `dynamic_flows` | Standalone registry table with no parent reference columns. |
| `dynamic_nodes` | Standalone registry table with no parent reference columns. |
| `event_outcomes` | `user_id` already has a DB FK to `users.id`. |
| `flow_history` | `flow_run_id` already has a DB FK to `flow_runs.id` with `ON DELETE CASCADE`. |
| `flow_runs` | `user_id` already has a DB FK to `users.id`; dead-letter columns are scalar metadata, not references. |
| `job_logs` | `user_id` already has a DB FK to `users.id`. |
| `memory_metrics` | `user_id` already has a DB FK to `users.id`. |
| `memory_node_history` | `node_id` already has a DB FK to `memory_nodes.id` with `ON DELETE CASCADE`. |
| `memory_traces` | `user_id` already has a DB FK to `users.id`. |
| `memory_trace_nodes` | `trace_id` and `node_id` already have DB FKs with `ON DELETE CASCADE`. |
| `request_metrics` | `user_id` already has a DB FK to `users.id`. |
| `system_events` | Existing DB FKs cover `user_id`, `agent_id`, and `parent_event_id`. |
| `event_edges` | Existing DB FKs cover both event endpoints and optional target memory node. |
| `system_health_logs` | Standalone operational log table; no parent reference columns. |
| `system_state_snapshots` | Standalone snapshot table; no parent reference columns. |
| `user_identities` | `user_id` already has a DB FK to `users.id`. |
| `watcher_signals` | `user_id` already has a DB FK to `users.id`. |
| `webhook_subscriptions` | Standalone subscription table; no parent reference columns. |
| `analysis_results` | `user_id` already has a DB FK to `users.id`. |
| `arm_runs` / `arm_logs` | `arm_logs.run_id` is already constrained to `arm_runs.id`; config tables are standalone. |
| `code_generations` | `user_id` already has a DB FK to `users.id`, and `analysis_id` already has a DB FK to `analysis_results.id`. |
| `automation_logs` | `user_id` already has a DB FK to `users.id`. |
| `bridge_user_events` | Standalone event ingest table with no verified parent FK contract. |
| `loop_adjustments` | `user_id` already has a DB FK to `users.id`. |
| `user_feedback` | `user_id` already has a DB FK to `users.id`; `loop_adjustment_id` remains deferred. |
| `master_plans` | `user_id`, `parent_id`, and `linked_genesis_session_id` already have DB FKs; uniqueness on genesis linkage was added earlier. |
| `genesis_sessions` | `user_id` already has a DB FK to `users.id`. |
| `goals` | `user_id` already has a DB FK to `users.id`. |
| `goal_states` | `goal_id` already has a DB FK to `goals.id`. |
| `tasks` | `masterplan_id`, `parent_task_id`, and `user_id` already have DB FKs. |
| `drop_points` | `user_id` already has a DB FK to `users.id`. |
| `pings` | `drop_point_id` and `user_id` already have DB FKs. |
| `ripple_edges` | Existing DB FKs cover both event endpoints and optional target memory node. |
| `strategies` | DB already has `user_id` ownership constraint from the UUID-normalization migration. |
| `calculation_results` | `user_id` already has a DB FK to `users.id`. |
| `canonical_metrics` | `masterplan_id` and `user_id` already have DB FKs. |
| `score_history` | `user_id` already has a DB FK to `users.id`. |
| `user_scores` | `user_id` already has a DB FK to `users.id`. |
| `user_kpi_weights` | `user_id` already has a DB FK to `users.id`. |
| `user_policy_thresholds` | `user_id` already has a DB FK to `users.id`. |
| `authors` | `user_id` already has a DB FK to `users.id`. |
| `research_results` | `user_id` already has a DB FK to `users.id`. |
| `leadgen_results` | `user_id` already has a DB FK to `users.id`. |
| `freelance_orders` | `masterplan_id`, `task_id`, `automation_log_id`, and `user_id` already have DB FKs. |
| `client_feedback` | `order_id` already has a DB FK to `freelance_orders.id` with `ON DELETE CASCADE`; `user_id` already has a DB FK to `users.id`. |
| `freelance_payment_records` | `order_id` already has a DB FK to `freelance_orders.id` with `ON DELETE CASCADE`; `user_id` already has a DB FK to `users.id`. |
| `freelance_refund_records` | `order_id` already has a DB FK to `freelance_orders.id` with `ON DELETE CASCADE`; `user_id` already has a DB FK to `users.id`. |
| `freelance_webhook_events` | Standalone webhook log table; no parent reference columns. |
| `social` models | `apps/social/models/social_models.py` defines Pydantic models only, not SQLAlchemy tables. |
