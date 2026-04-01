# Tutorial 3 — Scheduled Intelligence

**Time:** ~7 minutes  
**Difficulty:** Intermediate  
**What you'll build:** A Nodus script that runs on a cron schedule, analyzes memory, writes a daily briefing, and emails (emits) the summary — without you doing anything after setup.

---

## Goal

You'll see A.I.N.D.Y. running autonomously. You set it up once, and every morning it:

1. Reads everything written to memory in the last 24 hours
2. Analyzes it with a flow
3. Writes a daily briefing node
4. Emits a `daily.briefing.ready` event

```
09:00 every day
      │
      ▼
  Nodus script fires (no human involved)
      │
      ├─ reads recent memory nodes
      ├─ runs analysis flow
      ├─ writes briefing to memory
      └─ emits event → triggers webhooks
```

---

## Step 1 — Write the briefing script

Create `daily_briefing.nodus`:

```js
// Read everything written since yesterday
let recent = sys("sys.v1.memory.read", {
    path:  "/memory/demo/**",
    query: "sprint insight decision outcome",
    limit: 50
})

let nodes     = recent.data.nodes
let node_count = nodes.length

// Nothing to brief today? Exit cleanly.
if node_count == 0 {
    set_state("briefing", "No new memory nodes since last briefing.")
    set_state("node_count", 0)
    emit("daily.briefing.ready", {node_count: 0, summary: "Nothing new."})
    set_state("done", true)
}

// Count by type
let decisions = 0
let outcomes  = 0
let insights  = 0
let i = 0

while i < node_count {
    let t = nodes[i].node_type
    if t == "decision" { decisions = decisions + 1 }
    if t == "outcome"  { outcomes  = outcomes  + 1 }
    if t == "insight"  { insights  = insights  + 1 }
    i = i + 1
}

// Build a summary line
let summary = "Daily briefing: " + node_count + " node(s) — "
            + decisions + " decisions, "
            + outcomes  + " outcomes, "
            + insights  + " insights."

// Run a deeper analysis if we have enough signal
let analysis_summary = summary
if node_count >= 3 {
    let analysis = sys("sys.v1.flow.run", {
        flow_name: "analyze_tasks",
        input: {
            nodes:   nodes,
            context: "daily briefing"
        }
    })
    if analysis.status == "success" {
        analysis_summary = analysis.data.summary
    }
}

// Write the briefing to a well-known path so downstream
// consumers can always find today's briefing at the same address.
sys("sys.v1.memory.write", {
    path:      "/memory/demo/briefings/decision",
    content:   analysis_summary,
    tags:      ["daily-briefing", "auto-generated"],
    node_type: "decision",
    extra: {
        node_count: node_count,
        decisions:  decisions,
        outcomes:   outcomes,
        insights:   insights
    }
})

// Emit for webhooks / downstream automations
emit("daily.briefing.ready", {
    node_count:       node_count,
    decisions:        decisions,
    outcomes:         outcomes,
    insights:         insights,
    summary:          analysis_summary
})

// Surface for callers who inspect output_state directly
set_state("briefing",    analysis_summary)
set_state("node_count",  node_count)
set_state("done",        true)
```

---

## Step 2 — Test it manually first

Always verify the script runs correctly before scheduling it. Create `tutorial_03.py`:

```python
import os, json
from aindy import AINDYClient

client = AINDYClient(
    base_url=os.environ.get("AINDY_BASE_URL", "http://localhost:8000"),
    api_key=os.environ.get("AINDY_API_KEY", "aindy_replace_me"),
)

# Upload the script
print("Uploading daily_briefing script...")
with open("daily_briefing.nodus") as f:
    source = f.read()

client.nodus.upload_script("daily_briefing", source, overwrite=True)
print("  ✓ Uploaded.")

# Run it once manually to verify
print("\nRunning manually...")
result = client.nodus.run_script(
    script_name="daily_briefing",
    input={},
)

print(f"  Status:        {result['nodus_status']}")
print(f"  Events emitted: {result['events_emitted']}")
print(f"  Memory writes:  {result['memory_writes_count']}")
print()
print("  Output state:")
for key, val in result.get("output_state", {}).items():
    print(f"    {key}: {val}")
```

**Expected output:**

```
Uploading daily_briefing script...
  ✓ Uploaded.

Running manually...
  Status:         success
  Events emitted: 1
  Memory writes:  1

  Output state:
    briefing:   Daily briefing: 3 node(s) — 1 decisions, 2 outcomes, 0 insights.
    node_count: 3
    done:       True
```

The script works. Now schedule it.

---

## Step 3 — Schedule it

```python
print("\nScheduling daily briefing (09:00 every day)...")

schedule = client.post("/platform/nodus/schedule", {
    "name":      "daily_briefing",
    "flow_name": "daily_briefing",
    "cron_expr": "0 9 * * *",       # 09:00 every day
    "state":     {}
})

print(f"  ✓ Job created")
print(f"    name:      {schedule.get('name')}")
print(f"    cron:      {schedule.get('cron_expr')}")
print(f"    next run:  {schedule.get('next_run_at', 'calculated at next tick')}")
```

**Expected output:**

```
Scheduling daily briefing (09:00 every day)...
  ✓ Job created
    name:      daily_briefing
    cron:      0 9 * * *
    next run:  2026-04-02T09:00:00+00:00
```

---

## Step 4 — Verify the schedule

```python
print("\nActive scheduled jobs:")
jobs = client.get("/platform/nodus/schedule")
for job in jobs.get("jobs", []):
    status = "✓ active" if job.get("is_active") else "✗ inactive"
    print(f"  [{status}] {job['name']}")
    print(f"             cron:     {job['cron_expr']}")
    print(f"             next run: {job.get('next_run_at', '—')}")
    print(f"             last run: {job.get('last_run_at', 'never')}")
```

**Expected output:**

```
Active scheduled jobs:
  [✓ active] daily_briefing
             cron:     0 9 * * *
             next run: 2026-04-02T09:00:00+00:00
             last run: never
```

---

## Step 5 — Subscribe a webhook to the briefing event

When the briefing runs, fire a webhook to your downstream system:

```python
print("\nSubscribing to briefing events...")
try:
    sub = client.post("/platform/webhooks", {
        "event_type":   "daily.briefing.ready",
        "callback_url": "https://your-system.com/hooks/aindy-briefing",
        "secret":       "your-webhook-secret",
    })
    print(f"  ✓ Webhook registered — id: {sub.get('id')}")
    print("  Payload you'll receive each morning:")
    print("""  {
    "event_type": "daily.briefing.ready",
    "payload": {
        "node_count": 12,
        "decisions": 3,
        "outcomes": 7,
        "insights": 2,
        "summary": "Daily briefing: 12 node(s)..."
    },
    "trace_id": "run-...",
    "timestamp": "2026-04-02T09:00:04Z"
  }""")
except Exception as e:
    print(f"  (Skipped: {e})")
```

---

## Step 6 — Force a test run right now

Don't want to wait until 09:00? Trigger it immediately:

```python
print("\nForcing a run now (manual trigger)...")

immediate = client.nodus.run_script(
    script_name="daily_briefing",
    input={"triggered_by": "manual"},
)

print(f"  Status:    {immediate['nodus_status']}")
print(f"  Briefing:  {immediate['output_state'].get('briefing', '—')}")
print(f"  Nodes:     {immediate['output_state'].get('node_count', 0)}")
```

**Expected output:**

```
Forcing a run now (manual trigger)...
  Status:    success
  Briefing:  Daily briefing: 3 node(s) — 1 decisions, 2 outcomes, 0 insights.
  Nodes:     3
```

---

## Step 7 — Read the briefing from memory

The briefing is always at the same well-known path. Any script, flow, or external system can read today's briefing without knowing the run ID:

```python
print("\nReading today's briefing from memory...")

briefings = client.memory.read("/memory/demo/briefings/*", limit=5)
for node in briefings["data"]["nodes"]:
    print(f"  Content: {node['content']}")
    print(f"  Written: {node.get('created_at', '—')}")
    print(f"  Tags:    {', '.join(node.get('tags', []))}")
    if node.get("extra"):
        extra = node["extra"]
        print(f"  Stats:   {extra.get('node_count', 0)} nodes, "
              f"{extra.get('decisions', 0)} decisions, "
              f"{extra.get('outcomes', 0)} outcomes")
```

**Expected output:**

```
Reading today's briefing from memory...
  Content: Daily briefing: 3 node(s) — 1 decisions, 2 outcomes, 0 insights.
  Written: 2026-04-01T10:32:14Z
  Tags:    daily-briefing, auto-generated
  Stats:   3 nodes, 1 decisions, 2 outcomes
```

---

## Step 8 — Update and cancel

Change the schedule:

```python
# Update to run twice a day (09:00 and 18:00)
client.delete("/platform/nodus/schedule/daily_briefing")
client.post("/platform/nodus/schedule", {
    "name":      "daily_briefing",
    "flow_name": "daily_briefing",
    "cron_expr": "0 9,18 * * *",
    "state":     {}
})
print("Updated: now runs at 09:00 and 18:00.")

# Cancel entirely
# client.delete("/platform/nodus/schedule/daily_briefing")
# print("Cancelled.")
```

---

## Complete script

```python
import os
from aindy import AINDYClient

client = AINDYClient(
    base_url=os.environ.get("AINDY_BASE_URL", "http://localhost:8000"),
    api_key=os.environ.get("AINDY_API_KEY", "aindy_replace_me"),
)

# Upload
with open("daily_briefing.nodus") as f:
    client.nodus.upload_script("daily_briefing", f.read(), overwrite=True)

# Test once manually
result = client.nodus.run_script(script_name="daily_briefing", input={})
print(f"Manual run: {result['output_state'].get('briefing')}")

# Schedule for every morning
client.post("/platform/nodus/schedule", {
    "name":      "daily_briefing",
    "flow_name": "daily_briefing",
    "cron_expr": "0 9 * * *",
    "state":     {},
})

# Subscribe for delivery
client.post("/platform/webhooks", {
    "event_type":   "daily.briefing.ready",
    "callback_url": "https://your-system.com/hooks/aindy",
})

# Confirm
jobs = client.get("/platform/nodus/schedule")
print(f"Active jobs: {len(jobs.get('jobs', []))}")
print("Done — briefing will run every morning at 09:00.")
```

**Final output:**

```
Manual run: Daily briefing: 3 node(s) — 1 decisions, 2 outcomes, 0 insights.
Active jobs: 1
Done — briefing will run every morning at 09:00.
```

---

## What you just built

```
Cron: "0 9 * * *"
      │
      ▼  09:00 every day (server-side, no client needed)
  daily_briefing.nodus
      │
      ├─ sys.v1.memory.read  ← scans /memory/demo/**
      │
      ├─ sys.v1.flow.run     ← analyze_tasks (if enough signal)
      │
      ├─ sys.v1.memory.write ← /memory/demo/briefings/decision
      │
      └─ sys.v1.event.emit   ─────────────────────────────────►  Webhook
                                                                  POST /hooks/aindy
                                                                  {node_count, summary, ...}
```

The server handles the schedule. You handle nothing — it runs while you sleep.

---

## Cron reference

| Expression | Meaning |
|------------|---------|
| `0 9 * * *` | 09:00 every day |
| `0 9,18 * * *` | 09:00 and 18:00 every day |
| `0 9 * * MON` | 09:00 every Monday |
| `*/30 * * * *` | Every 30 minutes |
| `0 0 1 * *` | Midnight on the 1st of each month |

Leader-election ensures only one server instance runs each job even in a multi-process deployment.

---

## All three tutorials — what you now have

| Tutorial | Pattern | What it gives you |
|----------|---------|-------------------|
| 1 — Memory-Driven Workflow | Read → Process → Write | Persistent, queryable intelligence |
| 2 — Event-Driven Automation | Emit → Wait → Resume | Reactive, pauseable workflows |
| 3 — Scheduled Intelligence | Cron → Script → Event | Autonomous, hands-off execution |

Combine them: write your tasks (T1), have a flow wait for approval before acting on them (T2), and run the whole loop on a schedule automatically (T3). That's the full A.I.N.D.Y. execution model.

---

## Next steps

- [Syscall Reference](../syscalls/index.md) — all v1 syscalls with schemas
- [Nodus Language Guide](../nodus/index.md) — full language reference
- [SDK Reference](../sdk/index.md) — all client methods
