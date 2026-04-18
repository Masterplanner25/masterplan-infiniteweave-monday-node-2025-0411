# Tutorial 1 — Memory-Driven Task Analyzer

**Time:** ~8 minutes  
**Difficulty:** Beginner  
**What you'll build:** A pipeline that reads tasks from memory, runs an analysis flow, and writes structured insights back — all through the syscall layer.

---

## Goal

You'll see the core A.I.N.D.Y. loop working end-to-end:

```
Write tasks → Read them back → Analyze → Write insights → Verify
```

By the end you'll have a populated memory namespace you can build on in later tutorials.

---

## Step 1 — Connect

Create `tutorial_01.py`:

```python
import os
from AINDY.sdk.aindy_sdk import AINDYClient

client = AINDYClient(
    base_url=os.environ.get("AINDY_BASE_URL", "http://localhost:8000"),
    api_key=os.environ.get("AINDY_API_KEY", "aindy_replace_me"),
)

print("Connected.")
```

Run it:

```bash
python tutorial_01.py
# Connected.
```

If you see `NetworkError`, check that `uvicorn main:app --reload` is running.  
If you see `AuthenticationError`, check your API key.

---

## Step 2 — Write three tasks to memory

Add this to `tutorial_01.py`:

```python
tasks = [
    {
        "path":      "/memory/demo/tasks/outcome",
        "content":   "Implement the syscall versioning layer",
        "tags":      ["engineering", "sprint-12", "completed"],
        "node_type": "outcome",
    },
    {
        "path":      "/memory/demo/tasks/outcome",
        "content":   "Write SDK unit tests — 47 passing, zero deps",
        "tags":      ["engineering", "sprint-12", "completed"],
        "node_type": "outcome",
    },
    {
        "path":      "/memory/demo/tasks/outcome",
        "content":   "Publish documentation site structure",
        "tags":      ["docs", "sprint-12", "in-progress"],
        "node_type": "outcome",
    },
]

print("Writing tasks...")
written_ids = []

for task in tasks:
    result = client.memory.write(
        path=task["path"],
        content=task["content"],
        tags=task["tags"],
        node_type=task["node_type"],
    )
    node_id = result["data"]["node"]["id"]
    written_ids.append(node_id)
    print(f"  ✓ {task['content'][:50]}  →  {node_id[:8]}...")

print(f"\nWrote {len(written_ids)} tasks.")
```

**Expected output:**

```
Writing tasks...
  ✓ Implement the syscall versioning layer          →  4f9a1b2c...
  ✓ Write SDK unit tests — 47 passing, zero deps    →  7c3b8d4e...
  ✓ Publish documentation site structure            →  2a1f9e7d...

Wrote 3 tasks.
```

---

## Step 3 — Read them back

```python
print("\nReading tasks from memory...")

read_result = client.memory.read(
    path="/memory/demo/tasks/*",
    limit=20,
)

nodes = read_result["data"]["nodes"]
print(f"Found {len(nodes)} node(s) — took {read_result['duration_ms']}ms\n")

for node in nodes:
    tags_str = ", ".join(node.get("tags", []))
    print(f"  [{node['node_type']}] {node['content']}")
    print(f"           tags: {tags_str}")
    print()
```

**Expected output:**

```
Reading tasks from memory...
Found 3 node(s) — took 4ms

  [outcome] Implement the syscall versioning layer
           tags: engineering, sprint-12, completed

  [outcome] Write SDK unit tests — 47 passing, zero deps
           tags: engineering, sprint-12, completed

  [outcome] Publish documentation site structure
           tags: docs, sprint-12, in-progress
```

---

## Step 4 — Register the analysis flow

A.I.N.D.Y. needs the flow to exist before you can run it. Add this block — it's idempotent (safe to re-run):

```python
import json
from AINDY.sdk.aindy_sdk import AINDYError

print("Registering analysis flow...")

try:
    client.post("/platform/flows", {
        "name":      "analyze_tasks",
        "nodes":     ["summarize_tasks"],
        "edges":     {},
        "start":     "summarize_tasks",
        "end":       ["summarize_tasks"],
        "overwrite": True,
    })
    print("  ✓ Flow registered.")
except AINDYError as e:
    print(f"  Flow registration skipped: {e.message}")
```

> **Note:** `summarize_tasks` must be a registered node on your server. For this tutorial, any registered terminal node works — the flow demonstrates the routing, not the node logic. See the [Node Registration guide](../sdk/index.md) to add custom nodes.

---

## Step 5 — Run the analysis flow

```python
print("\nRunning analysis flow...")

analysis = client.flow.run(
    "analyze_tasks",
    {
        "tasks":   nodes,
        "context": "sprint-12 retrospective",
    },
)

print(f"  Status:      {analysis['status']}")
print(f"  Version:     {analysis['version']}")
print(f"  Duration:    {analysis['duration_ms']}ms")
print(f"  Output keys: {list(analysis['data'].keys())}")
```

**Expected output:**

```
Running analysis flow...
  Status:      success
  Version:     v1
  Duration:    23ms
  Output keys: ['summary', 'completed_count', 'in_progress_count']
```

---

## Step 6 — Write the insight back to memory

```python
flow_data = analysis["data"]
summary = flow_data.get("summary", f"Analyzed {len(nodes)} tasks from sprint-12.")

print("\nWriting insight to memory...")

insight = client.memory.write(
    path="/memory/demo/insights/decision",
    content=summary,
    tags=["sprint-12", "retrospective", "auto-generated"],
    node_type="decision",
    extra={
        "source_flow":       "analyze_tasks",
        "task_count":        len(nodes),
        "completed_count":   flow_data.get("completed_count", 0),
        "in_progress_count": flow_data.get("in_progress_count", 0),
    },
)

insight_id = insight["data"]["node"]["id"]
insight_path = insight["data"]["node"].get("path", "/memory/demo/insights/decision/...")
print(f"  ✓ Insight written")
print(f"    id:   {insight_id[:8]}...")
print(f"    path: {insight_path}")
```

**Expected output:**

```
Writing insight to memory...
  ✓ Insight written
    id:   9e2c4f1a...
    path: /memory/demo/insights/decision/9e2c4f1a...
```

---

## Step 7 — Verify the full namespace

```python
print("\nVerifying namespace tree...")

tree = client.memory.tree("/memory/demo")
flat = tree["data"]["flat"]

print(f"  {len(flat)} node(s) under /memory/demo\n")

for node in flat:
    depth = node.get("path", "").count("/") - 2
    indent = "  " * depth
    print(f"{indent}• [{node['node_type']}] {node['content'][:55]}")
```

**Expected output:**

```
Verifying namespace tree...
  4 node(s) under /memory/demo

  • [outcome] Implement the syscall versioning layer
  • [outcome] Write SDK unit tests — 47 passing, zero deps
  • [outcome] Publish documentation site structure
      • [decision] Analyzed 3 tasks from sprint-12.
```

---

## Step 8 — Emit a completion event

```python
print("\nEmitting completion event...")

ev = client.events.emit("sprint.analyzed", {
    "sprint":       "sprint-12",
    "task_count":   len(nodes),
    "insight_id":   insight_id,
})

print(f"  ✓ Event emitted — id: {ev['data'].get('event_id', 'ok')}")
print("\nDone. The memory-driven loop is working.")
```

**Expected output:**

```
Emitting completion event...
  ✓ Event emitted — id: ev-3f8a...

Done. The memory-driven loop is working.
```

---

## Complete script

```python
import os
from AINDY.sdk.aindy_sdk import AINDYClient, AINDYError

client = AINDYClient(
    base_url=os.environ.get("AINDY_BASE_URL", "http://localhost:8000"),
    api_key=os.environ.get("AINDY_API_KEY", "aindy_replace_me"),
)

# ── Write tasks ──────────────────────────────────────────────────────────────
tasks_to_write = [
    ("Implement the syscall versioning layer",     ["engineering", "sprint-12", "completed"]),
    ("Write SDK unit tests — 47 passing, zero deps", ["engineering", "sprint-12", "completed"]),
    ("Publish documentation site structure",       ["docs",        "sprint-12", "in-progress"]),
]

for content, tags in tasks_to_write:
    client.memory.write("/memory/demo/tasks/outcome", content, tags=tags, node_type="outcome")

# ── Read back ────────────────────────────────────────────────────────────────
read = client.memory.read("/memory/demo/tasks/*", limit=20)
nodes = read["data"]["nodes"]

# ── Run analysis ─────────────────────────────────────────────────────────────
analysis = client.flow.run("analyze_tasks", {"tasks": nodes, "context": "sprint-12"})
summary = analysis["data"].get("summary", f"Analyzed {len(nodes)} tasks.")

# ── Write insight ────────────────────────────────────────────────────────────
client.memory.write(
    "/memory/demo/insights/decision",
    summary,
    tags=["sprint-12", "auto-generated"],
    node_type="decision",
)

# ── Emit completion ───────────────────────────────────────────────────────────
client.events.emit("sprint.analyzed", {"sprint": "sprint-12", "task_count": len(nodes)})

print(f"Loop complete: {len(nodes)} tasks → 1 insight → 1 event")
```

**Final output:**

```
Loop complete: 3 tasks → 1 insight → 1 event
```

---

## What you just built

```
/memory/demo/tasks/outcome/4f9a...    ← task 1
/memory/demo/tasks/outcome/7c3b...    ← task 2
/memory/demo/tasks/outcome/2a1f...    ← task 3
         │
         │  client.flow.run("analyze_tasks", ...)
         ▼
/memory/demo/insights/decision/9e2c... ← synthesized insight
         │
         │  client.events.emit("sprint.analyzed", ...)
         ▼
    SystemEvent row + any webhook deliveries
```

---

## Next

→ **[Tutorial 2: Event-Driven Automation](02-event-driven-automation.md)** — make that `sprint.analyzed` event trigger a follow-up workflow automatically.
