# Nodus Memory Integration

Nodus has first-class memory primitives backed by A.I.N.D.Y.'s Memory Bridge.

---

## Core primitives (always available)

These four functions are injected into every Nodus script without any import.

### `recall(query, tags, limit)`

Retrieve relevant memories before executing a task.

```js
let past = recall("authentication JWT implementation", ["auth", "decision"], 3)
```

### `remember(content, type, tags)`

Store a memory after task execution. Returns the new node ID.

```js
let node_id = remember(
    "Implemented JWT auth with refresh tokens. 1h expiry + 7d refresh.",
    "outcome",
    ["auth", "jwt", "security"]
)
```

### `suggest(query, tags)`

Get suggestions derived from past successful outcomes.

```js
let hints = suggest("implement secure authentication", ["auth"])
```

### `record_outcome(node_id, outcome)`

Record whether a recalled memory was helpful (`"success"` or `"failure"`). Feeds the self-improvement loop.

```js
if (past != nil) {
    if (collection_len(past) > 0) {
        record_outcome(past[0]["id"], "success")
    }
}
```

---

## stdlib module (`import memory`)

For extended memory operations, import the `memory` stdlib at the top of your script.

```js
import memory
```

This enables the full federation API described below.

---

## The execution loop

```
recall → execute → remember → record_outcome
```

Each execution makes future executions smarter — recalled memories provide context, and `record_outcome` feeds reinforcement back into the scoring layer so the most useful memories surface first.

---

## Federation (multi-agent memory)

Agent memory is namespaced (e.g. `"arm"`, `"genesis"`, `"nodus"`). Each agent has private memory and can share nodes across agents for the same user.

### Shared vs private

| Scope | Visibility |
|-------|-----------|
| Private | Only the source agent |
| Shared | All agents for the same user |

Genesis and ARM automatically share insights by default.

### Cross-agent queries

Use the federation helpers after `import memory`:

```js
import memory

// Query another agent's shared memory
let arm_insights = memory.recall_from("arm", "code quality patterns", ["review"], 5)

// Query across all agents
let all_insights = memory.recall_all("authentication patterns", ["auth"], 10)

// Promote a private node to shared
memory.share(node_id)
```

| Function | Description |
|----------|-------------|
| `memory.recall_from(agent, query, tags, limit)` | Query shared memory from a specific agent namespace |
| `memory.recall_all(query, tags, limit)` | Query shared memory across all agent namespaces |
| `memory.share(node_id)` | Promote a private memory node to shared visibility |

---

## Full example

See [`aindy-examples/nodus-flows/memory_task.nodus`](../../aindy-examples/nodus-flows/memory_task.nodus) for a complete working script demonstrating the full recall → execute → remember → feedback loop.
