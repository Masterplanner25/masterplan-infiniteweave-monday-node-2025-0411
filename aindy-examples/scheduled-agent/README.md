# Scheduled Execution Agent

A self-running intelligence agent that wakes up on a cron schedule, scans memory for recent activity, produces a structured daily briefing, and delivers it via event — without any human involvement after setup.

---

## What it does

```
Cron: "0 9 * * *" (or every minute for demo mode)
        │
        ▼  fires automatically — no human involvement
    daily_briefing.nodus
        │
        ├─ sys.v1.memory.read   scan /memory/examples/** for recent nodes
        ├─ sys.v1.flow.run      analyze_tasks (optional deep analysis)
        ├─ sys.v1.memory.write  /memory/examples/briefings/  ← today's briefing
        └─ sys.v1.event.emit    daily.briefing.ready
                │
                ▼
        webhook → POST https://your-system.com/hook
        {node_count, decisions, outcomes, summary, ...}
```

---

## Run

### One-time setup

```bash
pip install -r requirements.txt
python main.py setup
```

Output:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Scheduled Execution Agent
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[setup] Uploading Nodus script...
  ✓ daily_briefing uploaded

[setup] Seeding sample memory data...
  ✓ 6 nodes written to /memory/examples/

[setup] Creating cron schedule...
  ✓ Schedule created
    name:     daily_briefing
    cron:     0 9 * * *
    next run: 2026-04-02T09:00:00Z

[setup] Subscribing webhook...
  ✓ Webhook registered for daily.briefing.ready
    delivery: https://webhook.site/your-token

Done. The agent will run every morning at 09:00.
Run `python main.py run-now` to test immediately.
```

### Force a run immediately

```bash
python main.py run-now
```

Output:

```
[run-now] Triggering daily briefing...
  Status:    success
  Duration:  31ms

  Briefing written to memory:
  ┌──────────────────────────────────────────────┐
  │  Daily briefing: 6 node(s) — 2 decisions,   │
  │  3 outcomes, 1 insight. Top tags:             │
  │  engineering, sprint-12, docs.                │
  │  No blockers detected.                        │
  └──────────────────────────────────────────────┘

  Event emitted: daily.briefing.ready
  Webhook queued: 1 subscription(s)
```

### Check status and history

```bash
python main.py status
```

Output:

```
Schedule:   daily_briefing
Cron:       0 9 * * *
Next run:   2026-04-02T09:00:00Z
Last run:   2026-04-01T09:00:02Z
Runs today: 1

Recent briefings:
  • 2026-04-01T09:00:02Z  6 nodes  "Daily briefing: 6 node(s)..."
  • 2026-03-31T09:00:01Z  4 nodes  "Daily briefing: 4 node(s)..."
```

### Cancel the schedule

```bash
python main.py cancel
```

---

## Demo mode (every minute)

For testing without waiting until 09:00:

```bash
python main.py setup --cron "* * * * *"
python main.py status   # watch it tick
```

---

## Sample data

`data/schedule_config.json` — cron expression, namespace, webhook URL, and seed data. Edit to point at your webhook endpoint.

---

## Files

```
scheduled-agent/
  main.py                  ← entry point (setup / run-now / status / cancel)
  briefing.py              ← briefing formatter helpers
  data/
    schedule_config.json   ← cron, namespace, webhook config + seed nodes
  nodus/
    daily_briefing.nodus   ← the agent script that runs on schedule
  requirements.txt
```
