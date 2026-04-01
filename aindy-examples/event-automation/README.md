# Event-Driven Automation

A two-process example that demonstrates A.I.N.D.Y.'s WAIT/RESUME pattern.
One process starts a workflow that suspends itself waiting for an approval signal.
A second process sends that signal. The workflow resumes automatically.

---

## What it does

```
python main.py start          python main.py approve
      │                               │
      │  Writes pending tasks         │
      │  to memory                    │
      │                               │
      │  WAITS for                    │
      │  "task.review.requested"      │
      ·                               │
      · (suspended — zero threads)    │  Reads the pending
      ·                               │  tasks from memory
      ·                               │
      ·                               │  Emits "task.review.requested"
      ·                               │  with {approved: true, reviewer: "..."}
      ·  ◄────────────────────────────┘
      │
      │  RESUMES with event payload
      │
      │  If approved → writes approved insights + emits confirmation
      │  If rejected → writes rejection note  + emits rejection event
      ▼
   Done
```

---

## Run

Terminal 1 — start the workflow (it will hang waiting):

```bash
python main.py start
```

Terminal 2 — send the approval:

```bash
python main.py approve
```

Or send a rejection:

```bash
python main.py reject --reason "Needs more test coverage"
```

**Terminal 1 expected output (after approval):**

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Event-Driven Automation
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[start] Loading triggers...
  Loaded 3 trigger(s) from data/triggers.json

[start] Writing pending tasks to memory...
  ✓ Deploy syscall versioning to staging  →  4f9a...
  ✓ Publish SDK to package index          →  7c3b...
  ✓ Update API contracts doc              →  2a1f...

[start] Starting approval workflow...
  Script:  approval_flow
  Run ID:  run-9f3c1a...
  Status:  waiting          ← suspended here

Waiting for review signal...
(run `python main.py approve` in another terminal)

──── RESUMED ────────────────────────────────
  Signal received from: shawn
  Decision: APPROVED
  Note: "All items verified. Ship it."

[resume] Writing approved insights...
  ✓ Insight written  →  ab3d...

[resume] Emitting confirmation...
  ✓ task.review.completed emitted

Done.
```

---

## Sample data

`data/triggers.json` — 3 tasks that require approval before processing. Add your own.

---

## Files

```
event-automation/
  main.py             ← entry point (start / approve / reject commands)
  workflow.py         ← workflow state machine helpers
  data/
    triggers.json     ← tasks that need review
  nodus/
    approval_flow.nodus  ← the suspending Nodus script
  requirements.txt
```

---

## How WAIT/RESUME works

The Nodus script calls `sys("sys.v1.event.wait", {event_type: "task.review.requested"})`.
This suspends the execution unit as a database row — no threads, no polling.

When any caller emits `task.review.requested`, A.I.N.D.Y. resumes the script with the event payload injected as the return value of `event.wait`. The script continues from exactly where it left off.

Timeout: scripts can specify `timeout_seconds`. Expired waiting executions transition to `failed` state with an error message.
