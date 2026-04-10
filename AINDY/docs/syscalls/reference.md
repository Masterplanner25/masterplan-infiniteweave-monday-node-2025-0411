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
