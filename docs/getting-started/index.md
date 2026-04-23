# Getting Started

## What is A.I.N.D.Y.?

A.I.N.D.Y. is a language-executing runtime where you write Nodus scripts that interact with memory, flows, and events through syscalls. Think of it as an operating system for AI-driven workflows: your scripts run in a sandbox, every cross-boundary call goes through a typed, versioned interface, and everything is observable and traceable.

---

## 5-Minute Quickstart

### 1. Start the server

```bash
cd AINDY
alembic upgrade head
uvicorn main:app --reload
```

Server is running at `http://localhost:8000`.

---

### 2. Get an API key

```bash
# Log in and grab a JWT first
TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"you@example.com","password":"yourpass"}' \
  | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Create a scoped Platform API key
curl -s -X POST http://localhost:8000/platform/keys \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"quickstart","scopes":["memory.read","memory.write","memory.search","event.emit"]}' \
  | python -m json.tool
```

Copy the `key` value — it starts with `aindy_`. You only see it once.

---

### 3. Install the SDK

```bash
pip install -e path/to/sdk   # or copy the sdk/aindy/ package
```

---

### 4. Write memory, run a flow, read it back

```python
from AINDY.sdk.aindy_sdk import AINDYClient

client = AINDYClient(
    base_url="http://localhost:8000",
    api_key="aindy_your_key_here",
)

# Write a memory node
client.memory.write(
    "/memory/demo/tasks/outcome",
    "Launch the SDK by end of sprint",
    tags=["task", "sprint"],
)

# Read it back
result = client.memory.read("/memory/demo/tasks/*")
nodes = result["data"]["nodes"]
print(f"Found {len(nodes)} node(s): {nodes[0]['content']}")

# Run a flow
analysis = client.flow.run("analyze_tasks", {"nodes": nodes})
print(analysis["data"])

# Emit an event
client.events.emit("quickstart.completed", {"node_count": len(nodes)})
```

That's it. You've written to memory, queried it, executed a flow, and emitted an event.

---

### 5. Run a Nodus script inline

```python
result = client.nodus.run_script(
    script="""
let tasks = sys("sys.v1.memory.read", {path: "/memory/demo/tasks/*", limit: 10})
set_state("count", tasks.data.nodes.length)
emit("tasks.counted", {n: tasks.data.nodes.length})
""",
    input={},
)
print(result["output_state"])   # {"count": 1}
print(result["events_emitted"]) # 1
```

---

## What just happened?

| Step | What it did |
|------|-------------|
| `memory.write` | Persisted a node at a path-addressable address in the Memory Address Space |
| `memory.read` | Queried the path with a wildcard — returned all direct children |
| `flow.run` | Executed a registered Nodus flow with your data as input state |
| `events.emit` | Wrote a durable `SystemEvent` and triggered any webhook subscriptions |
| `nodus.run_script` | Ran sandboxed Nodus code inline — same syscall pipeline, same memory |

---

## Next steps

- [Core Concepts](../core-concepts/index.md) — understand the five building blocks
- [Syscall Reference](../syscalls/index.md) — every available syscall
- [Nodus](../nodus/index.md) — writing scripts directly
- [SDK](../sdk/index.md) — full SDK reference
- [Deployment Model](../deployment/DEPLOYMENT_MODEL.md) — supported production topology and infrastructure requirements
