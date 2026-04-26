---
title: "Nodus"
last_verified: "2026-04-01"
api_version: "1.0"
status: current
owner: "platform-team"
---
# Nodus

Nodus is the control language for A.I.N.D.Y. Scripts run inside a sandbox — no imports, no filesystem, no network. The only way to do anything useful is through syscalls.

---

## Your first script

```js
// Read tasks from memory
let tasks = sys("sys.v1.memory.read", {path: "/memory/demo/tasks/*", limit: 10})

// Run a flow with those tasks
let result = sys("sys.v1.flow.run", {
    flow_name: "analyze_tasks",
    input: {nodes: tasks.data.nodes}
})

// Write the insight back to memory
sys("sys.v1.memory.write", {
    path:     "/memory/demo/insights/outcome",
    content:  result.data.summary,
    tags:     ["auto", "sprint"],
    node_type: "insight"
})

// Surface the result and emit an event
set_state("summary", result.data.summary)
emit("analysis.done", {count: tasks.data.nodes.length})
```

Run it:

```python
result = client.nodus.run_script(script=source, input={})
print(result["output_state"]["summary"])
```

---

## Built-in functions

These are the only things a Nodus script can call. Everything else goes through `sys()`.

### `sys(name, payload)`

Dispatch a syscall. Returns the full response envelope.

```js
let r = sys("sys.v1.memory.read", {query: "auth flow", limit: 5})
if r.status == "success" {
    let nodes = r.data.nodes
}
```

### `set_state(key, value)`

Write a value into the output state. Callers see it in `result["output_state"]`.

```js
set_state("result", 42)
set_state("nodes", filtered_nodes)
```

### `get_state(key)`

Read a value previously set by `set_state`.

```js
let current = get_state("counter")
set_state("counter", current + 1)
```

### `emit(event_type, payload)`

Shorthand for `sys("sys.v1.event.emit", ...)`. Emits a durable event.

```js
emit("task.processed", {task_id: "abc", duration_ms: 120})
```

---

## Language basics

Nodus is dynamically typed and expression-oriented. It looks like a stripped-down JavaScript.

### Variables

```js
let x = 10
let name = "sprint"
let items = [1, 2, 3]
let config = {key: "value", limit: 5}
```

### Conditionals

```js
if r.status == "success" {
    set_state("ok", true)
} else {
    set_state("ok", false)
    emit("error.occurred", {msg: r.error})
}
```

### Loops

```js
let nodes = r.data.nodes
let i = 0
while i < nodes.length {
    emit("node.seen", {id: nodes[i].id})
    i = i + 1
}
```

### Property access

```js
let n = r.data.nodes[0]
let content = n.content
let first_tag = n.tags[0]
```

---

## Sandbox rules

| Allowed | Not allowed |
|---------|-------------|
| `sys()`, `set_state()`, `get_state()`, `emit()` | `import`, `require` |
| Variables, loops, conditionals | Filesystem access |
| Arithmetic and string ops | Network calls |
| Accessing syscall response data | `eval`, `exec` |

Violations are rejected with HTTP 422 before the VM starts — the script is never executed.

---

## Running scripts

### Inline (one-off)

```python
result = client.nodus.run_script(
    script="""
let r = sys("sys.v1.memory.read", {query: "goals", limit: 3})
set_state("count", r.data.nodes.length)
""",
    input={"context": "weekly review"},
)
print(result["output_state"]["count"])
```

### Named (upload once, run many times)

```python
# Upload
client.nodus.upload_script("weekly_review", open("scripts/weekly_review.nodus").read())

# Run
result = client.nodus.run_script(script_name="weekly_review", input={"week": 14})
```

### Via REST

```bash
POST /platform/nodus/run
{
  "script": "set_state(\"x\", 1)",
  "input":  {},
  "error_policy": "fail"
}
```

---

## Response shape

```json
{
    "status":              "SUCCESS",
    "trace_id":            "run-abc123",
    "run_id":              "run-abc123",
    "nodus_status":        "success",
    "output_state":        {"count": 3},
    "events":              [{"event_type": "analysis.done", "payload": {"count": 3}}],
    "memory_writes":       [],
    "events_emitted":      1,
    "memory_writes_count": 0,
    "error":               null
}
```

---

## Tracing

Every host-function call during a Nodus execution produces a `NodusTraceEvent` row. Retrieve the full trace after a run:

```python
trace = client.get("/platform/nodus/trace/run-abc123")
for event in trace["events"]:
    print(f"{event['node_name']} → {event['event_type']} ({event['duration_ms']}ms)")
```

Or use the CLI:

```bash
nodus trace run-abc123
```

---

## Scheduling

Run a Nodus script on a cron schedule:

```bash
POST /platform/nodus/schedule
{
  "name":      "weekly_review",
  "flow_name": "weekly_review",
  "cron_expr": "0 9 * * MON",
  "state":     {"week": "auto"}
}
```

List and cancel:

```bash
GET    /platform/nodus/schedule
DELETE /platform/nodus/schedule/{name}
```

---

## Error policy

| Policy | Behaviour |
|--------|-----------|
| `"fail"` (default) | First error halts the script |
| `"continue"` | Errors are recorded but execution continues |

```python
client.nodus.run_script(script=source, error_policy="continue")
```

---

## Full example: process and archive tasks

```js
// 1. Load open tasks
let open = sys("sys.v1.memory.read", {
    path: "/memory/demo/tasks/*",
    query: "open",
    limit: 50
})

// 2. Analyse them
let analysis = sys("sys.v1.flow.run", {
    flow_name: "classify_tasks",
    input: {nodes: open.data.nodes}
})

// 3. Write the classification back
let i = 0
while i < analysis.data.classified.length {
    let item = analysis.data.classified[i]
    sys("sys.v1.memory.write", {
        path:      "/memory/demo/archive/outcome",
        content:   item.summary,
        tags:      ["archived", item.priority],
        node_type: "outcome"
    })
    i = i + 1
}

// 4. Report
set_state("archived", analysis.data.classified.length)
emit("tasks.archived", {count: analysis.data.classified.length})
```
