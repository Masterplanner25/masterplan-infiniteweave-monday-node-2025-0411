# automation_flows.py Split — 2026-04-26

## Node distribution
| Node function | Original file | New file |
| --- | --- | --- |
| `automation_logs_list_node` | `apps/automation/flows/automation_system_flows.py` | `apps/automation/flows/system_flows.py` |
| `automation_log_get_node` | `apps/automation/flows/automation_system_flows.py` | `apps/automation/flows/system_flows.py` |
| `automation_log_replay_node` | `apps/automation/flows/automation_system_flows.py` | `apps/automation/flows/system_flows.py` |
| `automation_scheduler_status_node` | `apps/automation/flows/automation_system_flows.py` | `apps/automation/flows/system_flows.py` |
| `automation_task_trigger_node` | `apps/automation/flows/automation_system_flows.py` | `apps/automation/flows/system_flows.py` |
| `agent_run_*`, `agent_trust_*`, `agent_tools_*`, `agent_suggestions_*` | legacy mixed automation layer | `apps/agent/flows/agent_flows.py` |
| `watcher_signals_*`, `watcher_evaluate_trigger_*` | legacy mixed automation layer | `apps/automation/flows/watcher_flows.py` |
| memory runtime nodes | legacy mixed automation layer | `AINDY.runtime.flow_definitions_memory` via `apps/automation/flows/memory_flows.py` |

## Registration equivalence
Confirmed: `automation_system_flows.py` registered 5 node functions before the split, and `system_flows.py` registers the same 5 node functions after the split.

Compatibility re-exports retained:
- `apps/automation/flows/automation_system_flows.py` now re-exports the five moved system nodes and `register()` from `system_flows.py`.
- `apps/automation/flows/memory_flows.py` is a compatibility shim that preserves the package split while runtime memory registration stays owned by `AINDY.runtime.flow_definitions_memory`.

## Node names (immutable — stored in DB)
These names must never change:
- `automation_logs_list_node`
- `automation_log_get_node`
- `automation_log_replay_node`
- `automation_scheduler_status_node`
- `automation_task_trigger_node`
