# Templates

Three starter templates. Copy one, fill in the blanks, run it.

| Template | File | When to use |
|----------|------|-------------|
| Memory Loop | `memory-loop/` | Read data → process → write results back |
| Event Listener | `event-listener/` | Wait for a signal → react → repeat |
| Scheduled Agent | `scheduled-agent/` | Run on a cron schedule, no human required |

Each template comes in two flavours:
- **`template.py`** — Python SDK version
- **`template.nodus`** — Nodus script version (runs inside the sandbox)

---

## Setup (one-time)

```bash
export AINDY_BASE_URL="http://localhost:8000"
export AINDY_API_KEY="aindy_your_key"
```

---

## Use a template

```bash
cp -r templates/memory-loop my-app
cd my-app
# edit template.py — fill in the 4 marked lines
python template.py
```

Every line you need to change is marked with `# ← CHANGE THIS`.
