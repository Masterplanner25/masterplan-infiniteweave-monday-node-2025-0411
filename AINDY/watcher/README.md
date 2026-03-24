# A.I.N.D.Y. Watcher

OS-level attention monitoring agent for the A.I.N.D.Y. system.

The Watcher is a standalone Python process that runs alongside your work session. It monitors active window focus, tracks session state, detects distractions, and sends structured signals to the A.I.N.D.Y. API — closing the observation gap in the Infinity Algorithm Support System.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     watcher.py (main loop)               │
│  poll every N seconds                                    │
│                                                          │
│  window_detector.get_active_window()                     │
│       │                                                  │
│       ▼                                                  │
│  classifier.classify(window)  →  ClassificationResult   │
│       │                                                  │
│       ▼                                                  │
│  session_tracker.update(result)  →  [SessionEvent, ...]  │
│       │                                                  │
│       ▼                                                  │
│  signal_emitter.emit_many(events)                        │
│       │  (background thread, batched HTTP POST)          │
│       ▼                                                  │
│  POST /watcher/signals  (A.I.N.D.Y. API)                │
└─────────────────────────────────────────────────────────┘
```

---

## Files

| File | Purpose |
|------|---------|
| `window_detector.py` | Cross-platform active window detection (Windows/macOS/Linux/fallback) |
| `classifier.py` | Maps (app_name, window_title) → ActivityType |
| `session_tracker.py` | State machine: IDLE → WORKING → DISTRACTED → RECOVERING |
| `signal_emitter.py` | Batched HTTP emitter with retry and DRY_RUN mode |
| `config.py` | Environment-variable configuration loader |
| `watcher.py` | Main loop entry point |

---

## Setup

### 1. Install dependencies

```bash
pip install -r watcher/requirements_watcher.txt
```

**Platform-specific (optional, improves window title detection):**
- macOS: `pip install pyobjc-framework-AppKit pyobjc-framework-Quartz`
- Linux: `sudo apt install xdotool`
- Windows: uses `ctypes` (stdlib) — no additional install needed

### 2. Configure environment

Create or update `.env` in the `AINDY/` directory:

```env
AINDY_API_KEY=your-api-key-here
AINDY_WATCHER_API_URL=http://localhost:8000
AINDY_WATCHER_DRY_RUN=false
```

### 3. Run

```bash
# From the AINDY/ directory:
python -m watcher.watcher

# Dry run (logs signals, no HTTP)
python -m watcher.watcher --dry-run

# Custom polling interval
python -m watcher.watcher --poll-interval 10

# Debug logging
python -m watcher.watcher --log-level DEBUG
```

---

## Signal Types

| Signal | Triggered When |
|--------|----------------|
| `session_started` | 30s of confirmed work activity detected |
| `session_ended` | Session closes (idle or distraction > timeout) |
| `distraction_detected` | Non-work activity sustained for > 60s in working state |
| `focus_achieved` | Recovery confirmed after distraction |
| `context_switch` | Active app changes category within same session |
| `heartbeat` | Every 5 minutes while working or distracted |

---

## Configuration Reference

| Environment Variable | Default | Description |
|---|---|---|
| `AINDY_WATCHER_API_URL` | `http://localhost:8000` | A.I.N.D.Y. API base URL |
| `AINDY_API_KEY` | _(required)_ | API key for X-API-Key header |
| `AINDY_WATCHER_POLL_INTERVAL` | `5` | Seconds between window samples |
| `AINDY_WATCHER_FLUSH_INTERVAL` | `10` | Seconds between signal flushes |
| `AINDY_WATCHER_BATCH_SIZE` | `20` | Signals per HTTP POST |
| `AINDY_WATCHER_CONFIRMATION_DELAY` | `30` | Seconds of work before session_started |
| `AINDY_WATCHER_DISTRACTION_TIMEOUT` | `60` | Seconds before WORKING → DISTRACTED |
| `AINDY_WATCHER_RECOVERY_DELAY` | `30` | Seconds of work before recovery confirmed |
| `AINDY_WATCHER_HEARTBEAT_INTERVAL` | `300` | Seconds between heartbeat signals |
| `AINDY_WATCHER_DRY_RUN` | `false` | Log signals instead of HTTP POST |
| `AINDY_WATCHER_LOG_LEVEL` | `INFO` | Logging verbosity |

---

## API Endpoints

Both endpoints require `X-API-Key` header.

### POST /watcher/signals

Receive a batch of signals from the Watcher process.

```json
{
  "signals": [
    {
      "signal_type": "session_started",
      "session_id": "550e8400-e29b-41d4-a716-446655440000",
      "timestamp": "2026-03-24T09:00:00+00:00",
      "app_name": "cursor",
      "window_title": "main.py — AINDY",
      "activity_type": "work",
      "metadata": {}
    }
  ]
}
```

Response: `{"accepted": 1, "session_ended_count": 0}`

### GET /watcher/signals

Query stored signals.

Parameters: `session_id`, `signal_type`, `limit` (1–500, default 50), `offset`.

---

## Session State Machine

```
IDLE
  │ (work detected)
  ▼
CONFIRMING_WORK  ──(30s elapsed)──► WORKING
  │ (non-work before 30s)              │
  ▼                                    │ (distraction > 60s)
IDLE                                   ▼
                                  DISTRACTED
                                       │ (work detected)
                                       ▼
                                  RECOVERING ──(30s elapsed)──► WORKING
                                       │ (distraction)
                                       ▼
                                  DISTRACTED
```

---

## Infinity Algorithm Integration

`session_ended.focus_score` feeds directly into engagement scoring.
`distraction_detected` events reduce TWR efficiency.
`session_started` timestamps correlate with task `start_time` for true `time_on_task`.

See: `docs/roadmap/INFINITY_ALGORITHM_SUPPORT_SYSTEM.md` §3.2 (Observation Layer).
