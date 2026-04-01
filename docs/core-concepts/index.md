# Core Concepts

Five things. That's it.

---

## 1. Execution Unit

An Execution Unit is anything that runs: an agent run, a flow run, a Nodus script execution. Every unit gets an ID, a tenant owner, a resource budget, and a trace.

```
ExecutionUnit
  id:             "run-abc123"
  tenant_id:      "user-456"
  status:         "running" | "success" | "failed" | "waiting"
  syscall_count:  12
  cpu_time_ms:    340
  priority:       5
```

When you call `client.flow.run(...)`, a new Execution Unit is created. All syscalls dispatched during that run are billed to it. When it hits quota, it stops.

**You don't manage Execution Units directly.** They're created for you. You interact with them through the flow and syscall APIs.

---

## 2. Flow

A Flow is a named sequence of nodes. Each node runs a function and passes state to the next.

```
analyze_tasks
  ┌─────────────────┐
  │  recall_memory  │  → reads relevant memory
  └────────┬────────┘
           │
  ┌────────▼────────┐
  │   run_planner   │  → calls GPT-4o with context
  └────────┬────────┘
           │
  ┌────────▼────────┐
  │  write_insight  │  → persists the output to memory
  └─────────────────┘
```

Run a flow:

```python
result = client.flow.run("analyze_tasks", {"context": "sprint 12"})
```

Register a new flow at runtime (no restart):

```bash
POST /platform/flows
{
  "name": "my_flow",
  "nodes": ["node_a", "node_b"],
  "edges": {"node_a": ["node_b"]},
  "start": "node_a",
  "end": ["node_b"]
}
```

Flows can pause and wait for external signals (`WAIT`/`RESUME`), enabling human-in-the-loop patterns.

---

## 3. Memory Address Space

Every memory node lives at a path:

```
/memory/{tenant_id}/{namespace}/{type}/{node_id}
```

Real examples:

```
/memory/shawn/tasks/outcome/4f9a...
/memory/shawn/insights/decision/7c3b...
/memory/shawn/_legacy/insight/1a2b...   ← auto-derived for old nodes
```

Access patterns:

| Pattern | Meaning | Example |
|---------|---------|---------|
| Exact | One node by full path | `/memory/shawn/tasks/outcome/4f9a...` |
| `/*` | Direct children | `/memory/shawn/tasks/*` |
| `/**` | All descendants | `/memory/shawn/**` |

```python
# Read all task nodes
client.memory.read("/memory/shawn/tasks/*")

# Read everything (recursive)
client.memory.read("/memory/shawn/**", query="sprint goals")

# Hierarchical tree view
client.memory.tree("/memory/shawn/sprint-12")
```

Memory nodes also support semantic search (vector embeddings) via `client.memory.search()`.

---

## 4. Syscalls

A syscall is the only way for Nodus scripts to cross the sandbox boundary. Every call to memory, flows, or events goes through the syscall dispatcher.

```
Nodus script
    │
    │  sys("sys.v1.memory.read", {query: "auth"})
    ▼
SyscallDispatcher
    │  1. parse version
    │  2. check capability
    │  3. validate input schema
    │  4. execute handler
    │  5. return envelope
    ▼
{ status, data, version, warning, duration_ms }
```

Syscalls are versioned (`sys.v1.*`, `sys.v2.*`) and declare typed schemas. The dispatcher validates inputs before any handler runs. See the [Syscall Reference](../syscalls/index.md) for the full list.

---

## 5. Nodus

Nodus is the control language. It's a sandboxed scripting layer — no imports, no filesystem, no network. The only thing scripts can do is call syscalls and manipulate state.

```js
// Read memory
let tasks = sys("sys.v1.memory.read", {path: "/memory/demo/tasks/*", limit: 5})

// Run a flow
let result = sys("sys.v1.flow.run", {flow_name: "analyze_tasks", input: {nodes: tasks.data.nodes}})

// Write the output back
sys("sys.v1.memory.write", {
    path: "/memory/demo/insights/outcome",
    content: result.data.summary,
    tags: ["auto"]
})

// Surface the result
set_state("summary", result.data.summary)
emit("analysis.done", {count: tasks.data.nodes.length})
```

Nodus scripts run through the same Execution Unit, the same syscall dispatcher, and the same quota system as everything else. See [Nodus](../nodus/index.md) for the full language reference.

---

## How they fit together

```
Developer / External System
        │
        │  SDK / REST API
        ▼
   AINDYClient  ──────────────────────────────────┐
        │                                          │
        ├── memory.read/write/search               │
        ├── flow.run                               │
        ├── events.emit               POST /platform/syscall
        └── nodus.run_script                       │
                                                   ▼
                                        SyscallDispatcher
                                                   │
                                    ┌──────────────┼──────────────┐
                                    ▼              ▼              ▼
                               Memory           Flows          Events
                           (MAS + pgvector)  (Flow Engine)  (SystemEvent)
```

Everything is an Execution Unit. Execution Units run Flows. Flows call Syscalls. Syscalls touch Memory and Events. Nodus scripts are the glue.
