# Memory Analyzer

Loads a set of tasks from sample data, writes them into A.I.N.D.Y. memory, runs a pattern analysis flow, and writes structured insights back — all in one script.

---

## What it does

```
data/tasks.json
      │
      │  client.memory.write() × N
      ▼
/memory/examples/tasks/*          ← task nodes in MAS
      │
      │  client.flow.run("analyze_tasks")
      ▼
Pattern analysis
  • completion rate
  • tag frequency
  • bottleneck detection
      │
      │  client.memory.write()
      ▼
/memory/examples/insights/*       ← structured insight nodes
      │
      │  client.events.emit("analysis.complete")
      ▼
Console summary + memory tree
```

---

## Run

```bash
pip install -r requirements.txt
python main.py
```

**Expected output:**

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  A.I.N.D.Y. Memory Analyzer
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[1/5] Loading sample data...
  Loaded 8 tasks from data/tasks.json

[2/5] Writing tasks to memory...
  ✓ Implement auth middleware            → 3f8a...
  ✓ Write unit tests for syscall layer   → 7c2b...
  ✓ Deploy to staging                    → 1e9d...
  ✓ Fix memory leak in flow engine       → 4a6f...
  ✓ Update API contracts doc             → 8b3c...
  ✓ Add rate limiting to platform routes → 2d7e...
  ✓ Refactor DAO layer                   → 9f1a...
  ✓ Publish SDK to package index         → 5c4b...

[3/5] Running analysis flow...
  Flow:     analyze_tasks
  Status:   success
  Duration: 18ms

[4/5] Writing insights to memory...
  ✓ Completion rate insight   → ab2f...
  ✓ Tag frequency insight     → cd8e...
  ✓ Bottleneck insight        → ef3a...

[5/5] Summary
  ┌─────────────────────────────────┐
  │  Tasks loaded:       8          │
  │  Completed:          5 (62.5%)  │
  │  In progress:        2 (25.0%)  │
  │  Blocked:            1 (12.5%)  │
  │  Top tags:           engineering, sprint-12, docs  │
  │  Bottleneck:         deploy     │
  │  Insights written:   3          │
  └─────────────────────────────────┘

  Memory path: /memory/examples/
  Event emitted: analysis.complete

Done in 0.34s
```

---

## Sample data

`data/tasks.json` — 8 tasks across three statuses and four tag categories. Edit freely.

---

## Files

```
memory-analyzer/
  main.py           ← entry point
  analyzer.py       ← pattern detection logic
  data/
    tasks.json      ← sample tasks (edit to use your own)
  nodus/
    analyze.nodus   ← Nodus script version of the analysis
  requirements.txt
```

---

## Customise

- Change `MEMORY_NAMESPACE` in `main.py` to use a different path prefix.
- Edit `data/tasks.json` to add your own tasks.
- Swap `analyze_tasks` for any registered flow that accepts `{nodes: [...]}`.
