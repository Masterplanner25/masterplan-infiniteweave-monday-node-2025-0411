# Syscall Reference — v1

All syscalls follow the same pattern:

```python
result = client.syscalls.call("sys.v1.{domain}.{action}", payload)
# or via the higher-level APIs:
result = client.memory.read("/memory/shawn/**")
```

Every call returns the same envelope:

```json
{
    "status":            "success",
    "data":              {},
    "version":           "v1",
    "warning":           null,
    "trace_id":          "run-abc",
    "execution_unit_id": "run-abc",
    "syscall":           "sys.v1.memory.read",
    "duration_ms":       8,
    "error":             null
}
```

`data` is the handler output on success. `error` is set on failure. `warning` is set when the syscall is deprecated.

`trace_id` and `execution_unit_id` are **automatically propagated** through nested syscall chains. If your script or handler dispatches one syscall that internally dispatches another, every call in the chain shares the same `trace_id` — you never need to thread these IDs manually.

---

## Memory

### `sys.v1.memory.read`

Read memory nodes by path, text query, or both.

**Input**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `path` | string | No | MAS path expression (`/memory/…`, `/*`, `/**`) |
| `query` | string | No | Free-text filter |
| `limit` | integer | No | Max results (default 10) |

**Output** (`data`)

```json
{
    "nodes": [
        {
            "id":         "4f9a...",
            "content":    "Decided to use MAS for path-addressable memory",
            "tags":       ["architecture", "sprint"],
            "node_type":  "decision",
            "path":       "/memory/shawn/decisions/decision/4f9a...",
            "created_at": "2026-04-01T10:00:00Z"
        }
    ]
}
```

**Examples**

```python
# Wildcard — all task nodes
client.memory.read("/memory/shawn/tasks/*")

# Recursive + text filter
client.memory.read("/memory/shawn/**", query="authentication")

# No path — text search only
client.memory.read(query="sprint goals", limit=5)
```

```js
// In a Nodus script
let result = sys("sys.v1.memory.read", {path: "/memory/demo/**", limit: 20})
let nodes = result.data.nodes
```

---

### `sys.v1.memory.write`

Persist a memory node at a MAS path.

**Input**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `path` | string | Yes | Target MAS path. Node ID auto-generated if omitted. |
| `content` | string | Yes | Text content of the node |
| `tags` | list[string] | No | Tag list (default `[]`) |
| `node_type` | string | No | `"decision"` \| `"outcome"` \| `"insight"` \| `"relationship"` |
| `extra` | dict | No | Arbitrary metadata |

**Output** (`data`)

```json
{
    "node": {
        "id":      "7c3b...",
        "path":    "/memory/shawn/insights/outcome/7c3b...",
        "content": "...",
        "tags":    ["sprint"]
    }
}
```

**Examples**

```python
client.memory.write(
    "/memory/shawn/insights/outcome",
    "Completed SDK sprint — zero external deps",
    tags=["sdk", "completed"],
    node_type="outcome",
)
```

```js
sys("sys.v1.memory.write", {
    path: "/memory/demo/insights/outcome",
    content: "Task analysis complete",
    tags: ["auto"],
    node_type: "insight"
})
```

---

### `sys.v1.memory.search`

Semantic similarity search using vector embeddings.

**Input**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `query` | string | Yes | Natural-language search string |
| `limit` | integer | No | Max results (default 10) |
| `node_type` | string | No | Filter by node type |
| `min_similarity` | float | No | Minimum cosine similarity (0.0–1.0) |

**Output** (`data`)

```json
{
    "nodes": [
        {
            "id":         "...",
            "content":    "...",
            "similarity": 0.87
        }
    ]
}
```

**Example**

```python
client.memory.search("authentication design decisions", limit=5, min_similarity=0.75)
```

---

### `sys.v1.memory.list`

List direct children of a path (one level, no recursion).

**Input**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `path` | string | Yes | Parent path — no wildcard needed |
| `limit` | integer | No | Max results (default 100) |

**Example**

```python
client.memory.list("/memory/shawn/tasks")
# Returns nodes whose parent_path == "/memory/shawn/tasks"
```

---

### `sys.v1.memory.tree`

Return a full hierarchical tree from a path prefix.

**Input**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `path` | string | Yes | Root prefix to walk |
| `limit` | integer | No | Max nodes (default 100) |

**Output** (`data`)

```json
{
    "tree": {
        "/memory/shawn/sprint-12": {
            "node": null,
            "children": [
                { "node": {...}, "children": [] }
            ]
        }
    },
    "flat": [ ... ]
}
```

**Example**

```python
client.memory.tree("/memory/shawn/sprint-12")
```

---

### `sys.v1.memory.trace`

Follow `source_event_id` causal links backward from a node.

**Input**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `path` | string | Yes | Exact path to starting node |
| `depth` | integer | No | Hops to follow (default 5, max 10) |

**Output** (`data`)

```json
{
    "chain": [
        { "id": "...", "content": "...", "path": "..." },
        { "id": "...", "content": "...", "path": "..." }
    ]
}
```

**Example**

```python
client.memory.trace("/memory/shawn/decisions/decision/4f9a...", depth=3)
```

---

## Flow

### `sys.v1.flow.run`

Execute a registered Nodus flow by name.

**Input**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `flow_name` | string | Yes | Name of the registered flow |
| `input` | dict | No | Initial state passed into the flow |

**Output** (`data`)

Flow-specific — contains whatever the flow's terminal node puts in state.

**Example**

```python
result = client.flow.run("analyze_tasks", {"nodes": nodes, "mode": "deep"})
print(result["data"]["summary"])
```

```js
let result = sys("sys.v1.flow.run", {
    flow_name: "classify_memory",
    input: {nodes: memory_nodes}
})
```

---

## Events

### `sys.v1.event.emit`

Emit a durable `SystemEvent`. Triggers any registered webhook subscriptions matching the event type.

**Input**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | Yes | Dot-namespaced event type, e.g. `"task.completed"` |
| `payload` | dict | No | Arbitrary metadata (default `{}`) |

**Output** (`data`)

```json
{ "event_id": "ev-abc123" }
```

**Example**

```python
client.events.emit("sprint.completed", {
    "sprint": "N+12",
    "tests":  1420,
})
```

```js
emit("analysis.done", {count: nodes.length})
// shorthand in Nodus — same as sys("sys.v1.event.emit", ...)
```

---

## Introspection

List all available syscalls with their schemas:

```python
registry = client.syscalls.list(version="v1")
for action, spec in registry["syscalls"]["v1"].items():
    print(f"sys.v1.{action} — {spec['description']}")
```

Or via REST:

```bash
GET /platform/syscalls?version=v1
```

---

## v2 syscalls

`sys.v2.memory.read` extends v1 with an optional `filters` dict:

```python
client.syscalls.call("sys.v2.memory.read", {
    "query": "auth",
    "filters": {"memory_type": "decision", "min_impact": 0.5},
})
```

All v1 payload keys remain valid. The `filters` field is additive.

---

## Error handling

When a syscall fails, `result["status"] == "error"` and `result["error"]` contains the message. Via the SDK, failures surface as typed exceptions:

```python
from AINDY.sdk.aindy_sdk import PermissionDeniedError, ResourceLimitError, ValidationError

try:
    client.memory.read("/memory/other_user/**")
except PermissionDeniedError:
    print("Missing memory.read capability")
except ResourceLimitError:
    print("Quota exceeded")
except ValidationError as e:
    print(f"Bad payload: {e.message}")
```
