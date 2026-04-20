# A.I.N.D.Y. Documentation

**A.I.N.D.Y.** is a language-executing runtime. You write Nodus scripts that read and write memory, trigger flows, and emit events — all through a clean syscall interface.

---

## Start here

| | |
|---|---|
| [Getting Started](getting-started/index.md) | Up and running in 5 minutes |
| [Core Concepts](core-concepts/index.md) | Five things you need to know |
| [Syscall Reference](syscalls/index.md) | Every v1 syscall with examples |
| [Nodus](nodus/index.md) | The control language |
| [SDK](sdk/index.md) | Python SDK for external integrations |
| [Tutorials](tutorials/index.md) | Three end-to-end walkthroughs |

---

## Architecture

| | |
|---|---|
| [Plugin Registry Pattern](architecture/PLUGIN_REGISTRY_PATTERN.md) | How domain apps integrate with the AINDY runtime — the actual wiring mechanism |
| [Cross-Domain Coupling](architecture/CROSS_DOMAIN_COUPLING.md) | Where analytics and automation intentionally cross domain boundaries, and the rules for doing so safely |
| [System Spec](architecture/SYSTEM_SPEC.md) | Top-level system specification |

---

## Runtime

| | |
|---|---|
| [Execution Contract](runtime/EXECUTION_CONTRACT.md) | What the flow engine guarantees |
| [Retry Policy](runtime/RETRY_POLICY.md) | Per-step retry rules |
| [OS Isolation Layer](runtime/OS_ISOLATION_LAYER.md) | Tenant isolation, quota enforcement, priority scheduling |
| [Syscall System](runtime/SYSCALL_SYSTEM.md) | Syscall dispatch, versioning, capability scope |
| [Agent Runtime](runtime/AGENT_RUNTIME.md) | Agent lifecycle, capability enforcement, recovery |
| [Memory Address Space](runtime/MEMORY_ADDRESS_SPACE.md) | Hierarchical path-addressable memory |
| [Memory Bridge](runtime/MEMORY_BRIDGE.md) | Write path, recall, embeddings |
| [Memory Bridge Contract](runtime/MEMORY_BRIDGE_CONTRACT.md) | Read/write contract for memory operations |
| [Runtime Behavior](runtime/RUNTIME_BEHAVIOR.md) | Scheduler, event bus, execution modes |
| [Execution Audit](runtime/EXECUTION_AUDIT.md) | Observability and audit trail |

---

## What can I do with A.I.N.D.Y.?

```python
from AINDY.sdk.aindy_sdk import AINDYClient

client = AINDYClient("http://localhost:8000", api_key="aindy_...")

# Read memory, run a flow, write back the result
tasks  = client.memory.read("/memory/shawn/tasks/**")
result = client.flow.run("analyze_tasks", {"nodes": tasks["data"]["nodes"]})
client.memory.write("/memory/shawn/insights", result["data"]["summary"])
```

That's the whole pattern. Three lines. Everything else is detail.
