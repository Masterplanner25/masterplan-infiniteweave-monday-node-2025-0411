# Syscall API Changelog

## Purpose
This file tracks changes to the versioned syscall ABI surface. Breaking changes require a new version prefix; additive changes are recorded here but do not require a version bump. For request/response examples, see [reference.md](/C:/dev/masterplan-infiniteweave-monday-node-2025-0411/docs/syscalls/reference.md:1).

## Version History

### v1 — Current Stable (introduced: 2026-04-24)

#### Stable Syscalls
##### `sys.v1.memory.*`
| Full Name | Domain | Description | Input Fields | Output Fields |
|---|---|---|---|---|
| `sys.v1.memory.read` | `memory` | Recall memory nodes for the calling user. | `query, tags, limit, node_type, path` | `nodes, count` |
| `sys.v1.memory.write` | `memory` | Persist a new memory node. | `content, tags, node_type, path` | `node, path` |
| `sys.v1.memory.search` | `memory` | Semantic search over user memory nodes. | `query, limit, path` | `nodes, count` |

##### `sys.v1.flow.*`
| Full Name | Domain | Description | Input Fields | Output Fields |
|---|---|---|---|---|
| `sys.v1.flow.run` | `flow` | Execute a registered flow by name. | `flow_name, initial_state` | None declared in registry |
| `sys.v1.flow.execute_intent` | `flow` | Top-level intent execution with learned strategy selection. | `intent_data` | `intent_result` |

##### `sys.v1.agent.*`
| Full Name | Domain | Description | Input Fields | Output Fields |
|---|---|---|---|---|
| `sys.v1.agent.execute` | `agent` | Execute an approved AgentRun via the deterministic runtime. | `run_id` | `run_result` |

##### `sys.v1.job.*`
| Full Name | Domain | Description | Input Fields | Output Fields |
|---|---|---|---|---|
| `sys.v1.job.submit` | `job` | Submit a named async job to the automation pipeline. | `task_name, payload, source, max_attempts` | `log_id, task_name, source` |

##### `sys.v1.nodus.*`
| Full Name | Domain | Description | Input Fields | Output Fields |
|---|---|---|---|---|
| `sys.v1.nodus.execute` | `nodus` | Execute a Nodus script via flow-backed orchestration. | `script, input_payload, error_policy, workflow_type, trace_id, node_max_retries` | `nodus_result` |

##### `sys.v1.event.*`
| Full Name | Domain | Description | Input Fields | Output Fields |
|---|---|---|---|---|
| `sys.v1.event.emit` | `event` | Emit a SystemEvent on the A.I.N.D.Y. event bus. | `event_type, payload` | None declared in registry |

#### Deprecated Syscalls
None. Deprecations will be listed here as they are introduced.

#### Experimental Syscalls
| Full Name | Domain | Status Note |
|---|---|---|
| `sys.v1.memory.list` | `memory` | Registered in `v1` but marked `stable=False`. |
| `sys.v1.memory.tree` | `memory` | Registered in `v1` but marked `stable=False`. |
| `sys.v1.memory.trace` | `memory` | Registered in `v1` but marked `stable=False`. |
| `sys.v2.memory.read` | `memory` | Registered as experimental next-version surface; not part of stable `v1`. |

## ABI Stability Contract
1. Required input fields MAY NOT be removed within the same version.
2. New fields MUST be optional (no new required fields in same version).
3. Output shape MUST remain consistent within a version.
4. Breaking changes MUST use a new version ("sys.v2.*").
5. Deprecated syscalls MUST emit a warning and point to a replacement.

## How to Introspect the Live Syscall Surface
Use:

```http
GET /platform/syscalls
```

The live response shape is:

```json
{
  "versions": ["v1", "v2"],
  "syscalls": {
    "v1": {
      "memory.read": {
        "full_name": "sys.v1.memory.read",
        "name": "memory.read",
        "version": "v1",
        "capability": "memory.read",
        "description": "Recall memory nodes for the calling user.",
        "input_schema": {},
        "output_schema": {},
        "stable": true,
        "deprecated": false,
        "deprecated_since": null,
        "replacement": null
      }
    }
  },
  "total_count": 13
}
```

This endpoint is generated from the live `SYSCALL_REGISTRY` through `SyscallSpec.to_dict()`. It is the authoritative runtime source for available versions, names, schemas, stability, and deprecation metadata.
