---
title: "Syscall Reference"
last_verified: "2026-04-29"
api_version: "1.0"
status: current
owner: "platform-team"
---
# Syscall Reference

Use `POST /platform/syscall` to execute a syscall and `GET /platform/syscalls?version=v1` to inspect the live ABI registry.

## Request shape

```json
{
  "name": "sys.v1.memory.read",
  "payload": {
    "query": "recent launch notes",
    "limit": 3
  }
}
```

Auth: `Authorization: Bearer <jwt>` or `X-Platform-Key: aindy_<token>`.

## Stable v1 syscalls

### `sys.v1.memory.read`
- Capability: `memory.read`
- Purpose: recall memory nodes for the authenticated user

| Input | Type |
| --- | --- |
| `query` | `string` |
| `tags` | `list` |
| `limit` | `int` |
| `node_type` | `string` |
| `path` | `string` |

| Output | Type |
| --- | --- |
| `nodes` | `list` |
| `count` | `int` |

### `sys.v1.memory.write`
- Capability: `memory.write`
- Purpose: persist a memory node

| Input | Type |
| --- | --- |
| `content` | `string` |
| `tags` | `list` |
| `node_type` | `string` |
| `path` | `string` |

| Output | Type |
| --- | --- |
| `node` | `dict` |
| `path` | `string` |

### `sys.v1.memory.search`
- Capability: `memory.search`
- Purpose: semantic search over user memory

| Input | Type |
| --- | --- |
| `query` | `string` |
| `limit` | `int` |
| `path` | `string` |

| Output | Type |
| --- | --- |
| `nodes` | `list` |
| `count` | `int` |

### `sys.v1.flow.run`
- Capability: `flow.run`
- Purpose: execute a registered flow

| Input | Type |
| --- | --- |
| `flow_name` | `string` |
| `initial_state` | `dict` |

| Output | Type |
| --- | --- |
| `flow_result` | `dict` |

### `sys.v1.event.emit`
- Capability: `event.emit`
- Purpose: emit a `SystemEvent`

| Input | Type |
| --- | --- |
| `event_type` | `string` |
| `payload` | `dict` |

| Output | Type |
| --- | --- |
| `event_id` | `string` |

## Domain syscalls

Domain syscalls are registered by app bootstrap modules. They are available
through the same dispatcher and endpoint as platform syscalls. Use
`GET /platform/syscalls?version=v1` to view the live registry with full
input/output schemas.

The following table lists stable domain syscalls by namespace:

### Task namespace

| Syscall | Capability | Purpose |
| --- | --- | --- |
| `sys.v1.task.create` | `tasks.write` | Create a task |
| `sys.v1.task.complete` | `tasks.write` | Mark a task complete |
| `sys.v1.task.complete_full` | `tasks.write` | Complete with orchestration |
| `sys.v1.task.start` | `tasks.write` | Start a task |
| `sys.v1.task.pause` | `tasks.write` | Pause a task |
| `sys.v1.task.orchestrate` | `tasks.write` | Post-completion orchestration |
| `sys.v1.task.get` | `tasks.read` | Get a task by ID |
| `sys.v1.task.get_user_tasks` | `tasks.read` | List tasks for a user |

### Analytics namespace

| Syscall | Capability | Purpose |
| --- | --- | --- |
| `sys.v1.analytics.get_kpi_snapshot` | `analytics.read` | Current KPI snapshot for a user |
| `sys.v1.analytics.save_calculation` | `analytics.write` | Persist a KPI calculation |
| `sys.v1.analytics.execute_infinity` | `analytics.write` | Trigger Infinity Algorithm |
| `sys.v1.analytics.init_user_score` | `analytics.write` | Initialize user score record |
| `sys.v1.analytics.get_latest_adjustment` | `analytics.read` | Most recent loop adjustment |
| `sys.v1.score.recalculate` | `analytics.write` | Full score recalculation |
| `sys.v1.score.feedback` | `analytics.write` | Persist user feedback signal |

### Agent namespace

| Syscall | Capability | Purpose |
| --- | --- | --- |
| `sys.v1.agent.execute` | `agent.run` | Execute an approved AgentRun |
| `sys.v1.agent.count_runs` | `agent.read` | Count runs for a user (with optional status filter) |
| `sys.v1.agent.list_recent_runs` | `agent.read` | Recent runs as serialized dicts |
| `sys.v1.agent.ensure_initial_run` | `agent.write` | Find or create signup sentinel run |
| `sys.v1.agent.suggest_tools` | `agent.read` | KPI-driven tool suggestions |
| `sys.v1.agent.dispatch_tool` | `agent.run` | Proxy an approved agent tool call |

### Masterplan namespace

| Syscall | Capability | Purpose |
| --- | --- | --- |
| `sys.v1.masterplan.assert_owned` | `masterplan.read` | Verify user owns a MasterPlan |
| `sys.v1.masterplan.get_active` | `masterplan.read` | Get the active MasterPlan for a user |
| `sys.v1.masterplan.get_eta` | `masterplan.read` | Get ETA for a MasterPlan |
| `sys.v1.masterplan.cascade_activate` | `masterplan.write` | Activate a plan with cascade |
| `sys.v1.goal.create` | `masterplan.write` | Create a goal |

### Automation namespace

| Syscall | Capability | Purpose |
| --- | --- | --- |
| `sys.v1.automation.list_feedback` | `automation.read` | List UserFeedback records for a user |
| `sys.v1.automation.list_loop_adjustments` | `automation.read` | List LoopAdjustment records |
| `sys.v1.automation.create_loop_adjustment` | `automation.write` | Create a LoopAdjustment |
| `sys.v1.automation.update_loop_adjustment` | `automation.write` | Update a LoopAdjustment |

### Social namespace

| Syscall | Capability | Purpose |
| --- | --- | --- |
| `sys.v1.social.adapt_linkedin` | `social.read` | Adapt raw LinkedIn metrics to canonical shape |
| `sys.v1.social.get_performance_signals` | `social.read` | Recent social performance signals |

### Other domain namespaces

| Syscall | Capability | Purpose |
| --- | --- | --- |
| `sys.v1.identity.get_context` | `identity.read` | Identity context for prompt enrichment |
| `sys.v1.identity.observe` | `identity.write` | Record an identity observation event |
| `sys.v1.arm.analyze` | `arm.execute` | Run ARM code analysis |
| `sys.v1.arm.generate` | `arm.execute` | Run ARM code generation |
| `sys.v1.arm.store` | `arm.write` | Persist ARM result to Memory Bridge |
| `sys.v1.leadgen.search` | `leadgen.execute` | B2B lead search |
| `sys.v1.leadgen.search_ai` | `leadgen.execute` | AI-powered lead search |
| `sys.v1.research.query` | `research.execute` | Web research query |
| `sys.v1.watcher.ingest` | `watcher.write` | Persist WatcherSignal batch |
| `sys.v1.watcher.query` | `watcher.read` | Query WatcherSignal records |
| `sys.v1.authorship.list_authors` | `authorship.read` | Recent authors for a user |
| `sys.v1.rippletrace.list_recent_pings` | `rippletrace.read` | Recent RippleTrace pings |

## Execution entry-point syscalls (v1)

These syscalls gate the host-layer execution entry points. Routes, agents, and schedulers call the corresponding public proxy functions (`run_flow()`, `execute_intent()`, etc.) — the proxy builds a `SyscallContext` and dispatches here. Callers with `user_id=None` skip the syscall layer entirely and invoke the underlying `_direct()` function.

### `sys.v1.flow.execute_intent`
- Capability: `flow.execute`
- Purpose: intent-based flow execution — selects a registered strategy, generates a plan if none found, compiles it to a flow, and runs via `PersistentFlowRunner`

| Input | Type |
| --- | --- |
| `intent_data` | `dict` |

| Output | Type |
| --- | --- |
| `intent_result` | `dict` |

### `sys.v1.nodus.execute`
- Capability: `nodus.execute`
- Purpose: run a Nodus script through the standard `NODUS_SCRIPT_FLOW` pipeline

| Input | Type |
| --- | --- |
| `script` | `string` |
| `input_payload` | `dict` |
| `error_policy` | `string` |
| `workflow_type` | `string` |
| `trace_id` | `string` |
| `node_max_retries` | `integer` |

| Output | Type |
| --- | --- |
| `nodus_result` | `dict` |

### `sys.v1.job.submit`
- Capability: `job.submit`
- Purpose: submit an async job; wraps `platform_layer.async_job_service.submit_async_job()` for quota tracking on non-Nodus callers

| Input | Type |
| --- | --- |
| `job_type` | `string` |
| `job_data` | `dict` |
| `user_id` | `string` |

| Output | Type |
| --- | --- |
| `job_result` | `dict` |

### `sys.v1.agent.execute`
- Capability: `agent.execute`
- Purpose: execute an agent run; wraps `agents.agent_runtime.execute_run()` for capability enforcement and observability on external callers

| Input | Type |
| --- | --- |
| `run_id` | `string` |
| `user_id` | `string` |

| Output | Type |
| --- | --- |
| `agent_result` | `dict` |

## Experimental v1 syscalls

These are present in the `v1` registry but marked `stable=false`.

### `sys.v1.memory.list`
- Capability: `memory.list`

| Input | Type |
| --- | --- |
| `path` | `string` |
| `limit` | `int` |

| Output | Type |
| --- | --- |
| `nodes` | `list` |
| `count` | `int` |
| `path` | `string` |

### `sys.v1.memory.tree`
- Capability: `memory.tree`

| Input | Type |
| --- | --- |
| `path` | `string` |
| `limit` | `int` |

| Output | Type |
| --- | --- |
| `tree` | `dict` |
| `node_count` | `int` |

### `sys.v1.memory.trace`
- Capability: `memory.trace`

| Input | Type |
| --- | --- |
| `path` | `string` |
| `depth` | `int` |

| Output | Type |
| --- | --- |
| `chain` | `list` |
| `depth` | `int` |

## Examples

```bash
curl -X POST http://localhost:8000/platform/syscall \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{"name":"sys.v1.memory.write","payload":{"content":"hello","tags":["demo"]}}'
```

```bash
curl -X POST http://localhost:8000/platform/syscall \
  -H "X-Platform-Key: aindy_your_key" \
  -H "Content-Type: application/json" \
  -d '{"name":"sys.v1.memory.read","payload":{"query":"hello","limit":5}}'
```

```python
import requests

resp = requests.post(
    "http://localhost:8000/platform/syscall",
    headers={
        "Authorization": f"Bearer {JWT}",
        "Content-Type": "application/json",
    },
    json={
        "name": "sys.v1.event.emit",
        "payload": {
            "event_type": "demo.completed",
            "payload": {"source": "docs"},
        },
    },
    timeout=30,
)
print(resp.json())
```

For the full live schema, call `GET /platform/syscalls?version=v1`.
