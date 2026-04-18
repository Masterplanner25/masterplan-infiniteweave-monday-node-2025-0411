# Tutorial 2 — Event-Driven Automation

**Time:** ~8 minutes  
**Difficulty:** Intermediate  
**What you'll build:** A Nodus script that pauses mid-execution waiting for an external signal, then automatically resumes and processes the data when the signal arrives.

---

## Goal

You'll see A.I.N.D.Y.'s WAIT/RESUME pattern — the execution unit suspends itself, and a second process wakes it up with new data. No polling. No threads. The script just stops and picks up exactly where it left off.

```
Script starts → reads tasks → WAITS for "review.approved" →
  (you emit the event) →
Script resumes → writes approved insight → emits confirmation
```

---

## How WAIT/RESUME works

```
Nodus script                    External system (you)
      │
      │  sys("sys.v1.event.wait",
      │      {event_type: "review.approved"})
      │
      ▼ ← execution unit status: WAITING
      ·
      ·  (suspended — no threads blocked)
      ·
      ▼ ← you emit "review.approved"
      │
      │  resumes with event payload injected
      │  into script state as "event_payload"
      ▼
   continues...
```

---

## Step 1 — Write the Nodus script

Create `wait_resume.nodus`:

```js
// Phase 1 — runs immediately on start
let tasks = sys("sys.v1.memory.read", {
    path: "/memory/demo/tasks/*",
    limit: 20
})

let task_count = tasks.data.nodes.length

// Persist what we found so Phase 2 can use it
sys("sys.v1.memory.write", {
    path:      "/memory/demo/pending/decision",
    content:   "Pending review: " + task_count + " tasks loaded for sprint-12",
    tags:      ["pending", "awaiting-approval"],
    node_type: "decision",
    extra:     {task_count: task_count}
})

// ── PAUSE HERE ────────────────────────────────────────────────────────────
// Execution unit suspends. Status → WAITING.
// Script resumes when "review.approved" is emitted.
// The emitted event's payload is injected as `event_payload`.
let approval = sys("sys.v1.event.wait", {
    event_type: "review.approved",
    timeout_seconds: 300
})
// ── RESUMED ───────────────────────────────────────────────────────────────

// Phase 2 — runs only after approval arrives
let reviewer  = approval.data.payload.reviewer
let approved  = approval.data.payload.approved
let note      = approval.data.payload.note

if approved {
    // Write the approved insight
    sys("sys.v1.memory.write", {
        path:      "/memory/demo/insights/decision",
        content:   "Sprint-12 tasks approved by " + reviewer + ". Note: " + note,
        tags:      ["approved", "sprint-12", reviewer],
        node_type: "decision",
        extra:     {reviewer: reviewer, task_count: task_count}
    })

    // Confirm via event
    emit("sprint.review.completed", {
        reviewer:    reviewer,
        task_count:  task_count,
        approved:    true
    })

    set_state("outcome", "approved")
    set_state("reviewer", reviewer)
} else {
    // Write a rejection note
    sys("sys.v1.memory.write", {
        path:      "/memory/demo/insights/decision",
        content:   "Sprint-12 tasks rejected by " + reviewer + ". Reason: " + note,
        tags:      ["rejected", "sprint-12"],
        node_type: "decision"
    })

    emit("sprint.review.rejected", {reviewer: reviewer, reason: note})
    set_state("outcome", "rejected")
}
```

---

## Step 2 — Upload and start the script

Create `tutorial_02.py`:

```python
import os
import time
from AINDY.sdk.aindy_sdk import AINDYClient

client = AINDYClient(
    base_url=os.environ.get("AINDY_BASE_URL", "http://localhost:8000"),
    api_key=os.environ.get("AINDY_API_KEY", "aindy_replace_me"),
)

# Make sure there are tasks to find (from Tutorial 1, or seed them now)
print("Seeding tasks...")
for content, tags in [
    ("Implement syscall versioning",             ["engineering", "sprint-12"]),
    ("Write SDK unit tests",                     ["engineering", "sprint-12"]),
    ("Publish documentation site",               ["docs",        "sprint-12"]),
]:
    client.memory.write("/memory/demo/tasks/outcome", content,
                        tags=tags, node_type="outcome")

# Upload the script
print("Uploading script...")
with open("wait_resume.nodus") as f:
    source = f.read()

client.nodus.upload_script("wait_resume", source, overwrite=True)
print("  ✓ Script uploaded.")

# Start it — it will immediately WAIT for "review.approved"
print("\nStarting script (will pause at event.wait)...")
result = client.nodus.run_script(
    script_name="wait_resume",
    input={"sprint": "sprint-12"},
)

run_id = result.get("run_id") or result.get("trace_id")
print(f"  Run ID:     {run_id}")
print(f"  Status:     {result.get('nodus_status', result.get('status'))}")
```

**Expected output:**

```
Seeding tasks...
Uploading script...
  ✓ Script uploaded.

Starting script (will pause at event.wait)...
  Run ID:     run-9f3c...
  Status:     waiting
```

The script is suspended. It has written the pending node to memory but is not yet processing anything. Nothing is blocked on the server — the execution unit is simply parked.

---

## Step 3 — Verify the script is waiting

```python
# Confirm the WAITING state
print("\nChecking execution state...")
info = client.execution.get(run_id)
print(f"  Execution status: {info['data']['status']}")   # "waiting"
print(f"  Syscalls so far:  {info['data']['syscall_count']}")

# Verify the pending node was written
print("\nPending memory nodes:")
pending = client.memory.read("/memory/demo/pending/*")
for node in pending["data"]["nodes"]:
    print(f"  • {node['content']}")
    print(f"    tags: {', '.join(node.get('tags', []))}")
```

**Expected output:**

```
Checking execution state...
  Execution status: waiting
  Syscalls so far:  2

Pending memory nodes:
  • Pending review: 3 tasks loaded for sprint-12
    tags: pending, awaiting-approval
```

---

## Step 4 — Subscribe to the completion event (optional but satisfying)

Before sending the approval signal, set up a webhook to watch for the result:

```python
print("\nSubscribing to completion events...")

# This posts to a local endpoint you control.
# For the tutorial, we just print the payload we'd receive.
try:
    sub = client.post("/platform/webhooks", {
        "event_type":   "sprint.review.*",     # prefix wildcard
        "callback_url": "http://localhost:9999/hook",
        "secret":       "tutorial-secret",
    })
    sub_id = sub.get("id", "sub-created")
    print(f"  ✓ Webhook subscribed — id: {sub_id}")
    print("  Listening for: sprint.review.completed, sprint.review.rejected")
except Exception as e:
    print(f"  (Webhook skipped: {e})")
    sub_id = None
```

---

## Step 5 — Send the approval signal

This is the moment. Emit the `review.approved` event and watch the script wake up.

```python
print("\nSending approval signal...")
time.sleep(1)  # tiny pause so the WAIT state is fully committed

approval_event = client.events.emit("review.approved", {
    "reviewer": "shawn",
    "approved": True,
    "note":     "All tasks meet the sprint exit criteria. Ship it.",
})

print(f"  ✓ Event emitted — id: {approval_event['data'].get('event_id', 'ok')}")
print("  Script should now resume...")
time.sleep(2)  # give the server a moment to process the resume
```

**Expected output:**

```
Sending approval signal...
  ✓ Event emitted — id: ev-8b2d...
  Script should now resume...
```

---

## Step 6 — Check the outcome

```python
print("\nChecking final state...")

# The execution unit should now be complete
info = client.execution.get(run_id)
print(f"  Execution status: {info['data']['status']}")  # "success"
print(f"  Total syscalls:   {info['data']['syscall_count']}")

# The approved insight should be in memory
print("\nApproved insights:")
insights = client.memory.read("/memory/demo/insights/*")
for node in insights["data"]["nodes"]:
    print(f"  • {node['content']}")
    print(f"    tags: {', '.join(node.get('tags', []))}")
```

**Expected output:**

```
Checking final state...
  Execution status: success
  Total syscalls:   4

Approved insights:
  • Sprint-12 tasks approved by shawn. Note: All tasks meet the sprint exit criteria. Ship it.
    tags: approved, sprint-12, shawn
```

---

## Step 7 — Read the execution trace

Every syscall during the run produced a trace event. Read the full timeline:

```python
print("\nExecution trace:")
trace = client.get(f"/platform/nodus/trace/{run_id}")
for event in trace.get("events", []):
    node   = event.get("node_name", "?")
    etype  = event.get("event_type", "?")
    dur    = event.get("duration_ms", 0)
    print(f"  {node:25s} {etype:30s} {dur}ms")
```

**Expected output:**

```
Execution trace:
  memory.read               sys.v1.memory.read             4ms
  memory.write              sys.v1.memory.write            3ms
  event.wait                sys.v1.event.wait              0ms   ← suspended here
  event.wait (resumed)      sys.v1.event.wait (resume)     0ms   ← woke up here
  memory.write              sys.v1.memory.write            2ms
  event.emit                sys.v1.event.emit              1ms
```

The trace shows exactly where the script paused and when it resumed — with the approval payload injected as if it was a normal return value.

---

## Complete script

```python
import os, time
from AINDY.sdk.aindy_sdk import AINDYClient

client = AINDYClient(
    base_url=os.environ.get("AINDY_BASE_URL", "http://localhost:8000"),
    api_key=os.environ.get("AINDY_API_KEY", "aindy_replace_me"),
)

# Seed tasks
for content in ["Syscall versioning", "SDK tests", "Docs site"]:
    client.memory.write("/memory/demo/tasks/outcome", content,
                        tags=["sprint-12"], node_type="outcome")

# Upload and start (will WAIT)
with open("wait_resume.nodus") as f:
    client.nodus.upload_script("wait_resume", f.read(), overwrite=True)

result = client.nodus.run_script(script_name="wait_resume", input={})
run_id = result.get("run_id") or result.get("trace_id")
print(f"Script waiting — run_id: {run_id}")

# Let it settle, then send the approval
time.sleep(1)
client.events.emit("review.approved", {
    "reviewer": "shawn",
    "approved": True,
    "note":     "Ship it.",
})
print("Approval sent — script resuming...")

# Check the result
time.sleep(2)
insights = client.memory.read("/memory/demo/insights/*")
for node in insights["data"]["nodes"]:
    print(f"Insight: {node['content']}")
```

**Final output:**

```
Script waiting — run_id: run-9f3c...
Approval sent — script resuming...
Insight: Sprint-12 tasks approved by shawn. Note: Ship it.
```

---

## What you just built

```
tutorial_02.py                  Nodus script (wait_resume.nodus)
      │                                    │
      │  run_script()                      │  reads memory
      │ ──────────────────────────────►    │  writes pending node
      │                                    │
      │                                    ▼ WAIT ("review.approved")
      │  events.emit("review.approved")    ·
      │ ──────────────────────────────►    · suspended
      │                                    ·
      │                                    ▼ RESUMED
      │                                    │  writes approved insight
      │  memory.read → sees result         │  emits "sprint.review.completed"
      │ ◄──────────────────────────────    │
```

Key insight: **the script has no polling loop, no callback, no thread**. It pauses as a database row and resumes as a scheduler event. This pattern scales to hundreds of concurrent waiting executions with zero resource cost while waiting.

---

## What happens if the event never arrives?

The `timeout_seconds: 300` parameter in the script means the execution fails with a timeout error after 5 minutes. Without a timeout it waits indefinitely. Both are valid depending on your use case.

---

## Next

→ **[Tutorial 3: Scheduled Intelligence](03-scheduled-execution.md)** — make this analysis run automatically every morning without you touching a keyboard.
