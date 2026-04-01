# aindy-examples

Three self-contained example projects for the [A.I.N.D.Y.](../AINDY/README.md) platform.

Each runs against a local server in under 5 minutes.

---

## Examples

| Project | What it does | Key patterns |
|---------|-------------|--------------|
| [memory-analyzer](memory-analyzer/) | Loads tasks, detects patterns, writes structured insights | `memory.read` → flow → `memory.write` |
| [event-automation](event-automation/) | Waits for approval before processing, rejects on timeout | `event.wait` · WAIT/RESUME · webhook delivery |
| [scheduled-agent](scheduled-agent/) | Runs a daily briefing autonomously, posts a summary | cron schedule · `event.emit` · `memory.tree` |

---

## Prerequisites

```bash
# 1. A.I.N.D.Y. server running locally
cd /path/to/AINDY
alembic upgrade head
uvicorn main:app --reload   # http://localhost:8000

# 2. SDK installed
pip install -e /path/to/sdk

# 3. A Platform API key
#    Create one after logging in:
curl -s -X POST http://localhost:8000/platform/keys \
  -H "Authorization: Bearer <your-jwt>" \
  -H "Content-Type: application/json" \
  -d '{"name":"examples","scopes":["memory.read","memory.write","flow.run","event.emit"]}' \
  | python -m json.tool
# Copy the "key" value — starts with aindy_

# 4. Set environment variables
export AINDY_BASE_URL="http://localhost:8000"
export AINDY_API_KEY="aindy_your_key_here"
```

---

## Run any example

```bash
cd memory-analyzer   # or event-automation / scheduled-agent
pip install -r requirements.txt
python main.py
```

---

## Shared Nodus scripts

[nodus-flows/](nodus-flows/) contains standalone `.nodus` scripts used across examples.
Upload any of them with:

```bash
python upload_scripts.py   # inside nodus-flows/
```
