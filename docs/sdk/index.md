# SDK Reference

The A.I.N.D.Y. Python SDK gives you a clean client for everything the platform exposes — memory, flows, events, syscalls, and Nodus scripts. Zero external dependencies. Requires Python 3.10+.

---

## Install

```bash
pip install -e path/to/sdk
```

Or drop the `aindy/` package directly into your project — it's pure stdlib.

---

## Connect

```python
from aindy import AINDYClient

client = AINDYClient(
    base_url="http://localhost:8000",
    api_key="aindy_your_platform_key",
)
```

Two auth methods work transparently:

| Key format | Header sent |
|------------|-------------|
| `aindy_...` | `X-Platform-Key: aindy_...` |
| Anything else | `Authorization: Bearer ...` |

Use Platform API keys for production integrations. Get one:

```bash
POST /platform/keys
{"name": "my-integration", "scopes": ["memory.read", "memory.write", "flow.run", "event.emit"]}
```

---

## Memory

```python
# Read by path (exact, one-level wildcard, recursive)
client.memory.read("/memory/shawn/tasks/*")
client.memory.read("/memory/shawn/**", query="sprint goals", limit=20)

# Semantic search
client.memory.search("authentication design", limit=5, min_similarity=0.75)

# Write
client.memory.write(
    "/memory/shawn/insights/outcome",
    "Completed SDK sprint",
    tags=["sprint", "done"],
    node_type="outcome",
)

# Tree view
client.memory.tree("/memory/shawn/sprint-12")

# One-level listing
client.memory.list("/memory/shawn/tasks")

# Causal trace
client.memory.trace("/memory/shawn/decisions/decision/4f9a...", depth=3)
```

All methods return the standard syscall envelope. The data you care about is in `result["data"]`.

---

## Flow

```python
result = client.flow.run("analyze_tasks", {"nodes": nodes})
summary = result["data"]["summary"]
```

The flow must be registered. Register one:

```python
client.post("/platform/flows", {
    "name":  "analyze_tasks",
    "nodes": ["recall_memory", "run_planner", "write_insight"],
    "edges": {
        "recall_memory": ["run_planner"],
        "run_planner":   ["write_insight"],
    },
    "start": "recall_memory",
    "end":   ["write_insight"],
})
```

---

## Events

```python
client.events.emit("sprint.completed", {
    "sprint": "N+12",
    "tests": 1420,
})
```

Any webhook subscription matching the event type receives a POST. Subscriptions support exact match (`"sprint.completed"`), prefix wildcard (`"sprint.*"`), and global wildcard (`"*"`).

---

## Execution

```python
info = client.execution.get("run-abc123")
print(info["data"]["status"])        # "success" | "running" | "waiting" | "failed"
print(info["data"]["syscall_count"]) # total syscalls dispatched
```

---

## Nodus

```python
# Inline script
result = client.nodus.run_script(
    script="""
let r = sys("sys.v1.memory.read", {query: "goals", limit: 5})
set_state("count", r.data.nodes.length)
emit("goals.loaded", {n: r.data.nodes.length})
""",
    input={"context": "weekly"},
)
print(result["output_state"]["count"])
print(result["events_emitted"])

# Named script
client.nodus.upload_script("weekly_review", open("weekly_review.nodus").read())
result = client.nodus.run_script(script_name="weekly_review", input={"week": 14})

# List uploaded scripts
scripts = client.nodus.list_scripts()
```

---

## Raw syscalls

Call any syscall directly — useful for v2 or custom-registered syscalls:

```python
# v2 memory read with filters
result = client.syscalls.call("sys.v2.memory.read", {
    "query":   "auth decisions",
    "filters": {"memory_type": "decision", "min_impact": 0.5},
})

# Introspect the registry
registry = client.syscalls.list(version="v1")
for action, spec in registry["syscalls"]["v1"].items():
    status = "[deprecated]" if spec["deprecated"] else ""
    print(f"sys.v1.{action} {status}")
```

---

## Error handling

Every error from the server maps to a typed exception.

```python
from aindy import (
    AINDYClient,
    AuthenticationError,    # 401 — invalid or expired key
    PermissionDeniedError,  # 403 — missing capability scope
    NotFoundError,          # 404 — resource does not exist
    ValidationError,        # 422 — bad payload or schema violation
    ResourceLimitError,     # 429 — quota exceeded
    ServerError,            # 5xx — unexpected server error
    NetworkError,           # connection refused / timeout / DNS failure
    AINDYError,             # base class — catch-all
)

try:
    result = client.memory.read("/memory/shawn/**")
except AuthenticationError:
    print("Renew your API key")
except PermissionDeniedError as e:
    print(f"Missing scope: {e.response}")
except ResourceLimitError:
    print("Quota hit — back off and retry")
except ValidationError as e:
    print(f"Fix the request: {e.message}")
except NetworkError as e:
    print(f"Server unreachable: {e.cause}")
except AINDYError as e:
    print(f"[{e.status_code}] {e.message}")
```

All exceptions expose `.status_code`, `.message`, and `.response` (raw server body).

---

## Complete example

```python
from aindy import AINDYClient, AINDYError

client = AINDYClient("http://localhost:8000", api_key="aindy_...")

# 1. Load tasks
tasks = client.memory.read("/memory/shawn/tasks/**", limit=50)
nodes = tasks["data"]["nodes"]
print(f"{len(nodes)} tasks loaded")

# 2. Analyse them
if nodes:
    analysis = client.flow.run("analyze_tasks", {"nodes": nodes})
    summary = analysis["data"].get("summary", "no summary")

    # 3. Write the insight
    client.memory.write(
        "/memory/shawn/insights/outcome",
        summary,
        tags=["auto", "sprint"],
        node_type="outcome",
    )

    # 4. Emit completion event
    client.events.emit("tasks.analyzed", {"count": len(nodes), "summary": summary})
    print("Done:", summary)
```

---

## Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `base_url` | — | Server URL, e.g. `"http://localhost:8000"` |
| `api_key` | — | Platform API key or JWT bearer token |
| `timeout` | `30` | Per-request timeout in seconds |

```python
client = AINDYClient(
    base_url="https://your-server.com",
    api_key="aindy_prod_key",
    timeout=60,
)
```

---

## Sub-API quick reference

| Sub-API | Methods |
|---------|---------|
| `client.memory` | `read`, `write`, `search`, `list`, `tree`, `trace` |
| `client.flow` | `run` |
| `client.events` | `emit` |
| `client.execution` | `get` |
| `client.nodus` | `run_script`, `upload_script`, `list_scripts` |
| `client.syscalls` | `call`, `list` |
