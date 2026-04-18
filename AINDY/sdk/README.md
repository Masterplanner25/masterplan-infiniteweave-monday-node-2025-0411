# A.I.N.D.Y. SDK (v1)

Python SDK for the A.I.N.D.Y. platform — memory, flows, syscalls, Nodus scripts, and events.

**Zero external dependencies.** Pure stdlib (`urllib`, `json`). Requires Python 3.10+.

---

## Installation

```bash
# From the sdk/ directory
pip install -e .

# Or copy the aindy/ package into your project directly
```

---

## Quick Start

```python
from AINDY.sdk.aindy_sdk import AINDYClient

client = AINDYClient(
    base_url="http://localhost:8000",
    api_key="aindy_your_platform_key",   # or a JWT bearer token
)

# Read memory nodes by path
result = client.memory.read("/memory/shawn/entities/**", limit=20)
nodes = result["data"]["nodes"]
print(f"Found {len(nodes)} nodes")

# Run a flow with the nodes as input
analysis = client.flow.run("analyze_entities", {"nodes": nodes})

# Write back the insight
client.memory.write(
    "/memory/shawn/insights/outcome",
    analysis["data"]["summary"],
    tags=["auto-generated"],
)

# Emit a completion event
client.events.emit("sprint.analyzed", {"node_count": len(nodes)})
```

---

## Memory API

```python
# Read (exact path, one-level wildcard, or recursive)
client.memory.read("/memory/shawn/entities/*")      # one level
client.memory.read("/memory/shawn/**", query="auth") # recursive + text filter

# Write
client.memory.write(
    "/memory/shawn/decisions/outcome",
    "Decided to use path-addressable memory",
    tags=["architecture"],
    node_type="decision",
)

# Semantic search
client.memory.search("authentication flow", limit=5, min_similarity=0.7)

# Tree view
client.memory.tree("/memory/shawn/sprint-n12")

# Causal trace
client.memory.trace("/memory/shawn/decisions/outcome/abc-123", depth=3)
```

---

## Flow API

```python
result = client.flow.run("my_flow", {"key": "value"})
print(result["data"])
```

---

## Events API

```python
client.events.emit("entity.updated", {"entity_id": "42", "duration_ms": 300})
```

---

## Execution API

```python
info = client.execution.get("run-abc123")
print(info["data"]["status"])       # "success" | "running" | "waiting" | "failed"
print(info["data"]["syscall_count"])
```

---

## Nodus API

```python
# Inline script
result = client.nodus.run_script(
    '''
    let mem = sys("sys.v1.memory.read", {query: "sprint goals", limit: 5})
    set_state("nodes", mem.data.nodes)
    emit("goals.loaded", {count: mem.data.nodes.length})
    ''',
    input={"context": "weekly review"},
)
print(result["output_state"]["nodes"])

# Named script (upload once, run many times)
client.nodus.upload_script("weekly_review", open("scripts/weekly_review.nodus").read())
result = client.nodus.run_script(script_name="weekly_review", input={"week": 14})

# List uploaded scripts
scripts = client.nodus.list_scripts()
```

---

## Raw Syscalls

```python
# Call any syscall directly
result = client.syscalls.call(
    "sys.v2.memory.read",
    {"query": "auth", "filters": {"memory_type": "decision"}},
)

# Introspect available syscalls
registry = client.syscalls.list(version="v1")
for action, spec in registry["syscalls"]["v1"].items():
    print(f"sys.v1.{action} — {spec['description']}")
```

---

## Error Handling

```python
from AINDY.sdk.aindy_sdk import (
    AINDYClient,
    AINDYError,
    AuthenticationError,
    PermissionDeniedError,
    ResourceLimitError,
    ValidationError,
    NetworkError,
)

try:
    result = client.memory.read("/memory/shawn/**")
except AuthenticationError:
    print("API key invalid or expired")
except PermissionDeniedError as e:
    print(f"Missing capability: {e.response}")
except ResourceLimitError:
    print("Quota exceeded — wait before retrying")
except ValidationError as e:
    print(f"Bad request: {e.message}")
except NetworkError as e:
    print(f"Server unreachable: {e.cause}")
except AINDYError as e:
    print(f"Unexpected error [{e.status_code}]: {e.message}")
```

---

## Authentication

Two auth methods are supported:

| Method | Header | How to obtain |
|--------|--------|---------------|
| Platform API key | `X-Platform-Key: aindy_...` | `POST /platform/keys` |
| JWT bearer token | `Authorization: Bearer ...` | `POST /auth/login` |

Platform API keys are recommended for SDK use — they carry explicit capability
scopes and can be revoked without affecting user sessions.

---

## Response Envelope

All syscall-backed methods return the standard envelope:

```json
{
    "status":            "success",
    "data":              {},
    "version":           "v1",
    "warning":           null,
    "trace_id":          "run-abc123",
    "execution_unit_id": "run-abc123",
    "syscall":           "sys.v1.memory.read",
    "duration_ms":       12,
    "error":             null
}
```

`nodus.run_script()` returns a different shape — see the Nodus API section above.

---

## Server-Side Requirement

The SDK requires the `POST /platform/syscall` endpoint (added in the SDK sprint).
Run `alembic upgrade head` and restart the server before using the SDK against a
freshly updated backend.
