# Tutorials

Three tutorials. Each takes under 10 minutes and ends with something running.

| # | Tutorial | What you'll see |
|---|----------|-----------------|
| 1 | [Memory-Driven Task Analyzer](01-memory-driven-workflow.md) | Memory → execution → insight loop |
| 2 | [Event-Driven Automation](02-event-driven-automation.md) | Flow pauses, waits for a signal, resumes |
| 3 | [Scheduled Intelligence](03-scheduled-execution.md) | System runs without you |

**Prerequisites for all three:**

```bash
# Server running
cd AINDY && uvicorn main:app --reload

# SDK available
pip install -e path/to/sdk

# API key in your environment
export AINDY_API_KEY="aindy_your_key"
export AINDY_BASE_URL="http://localhost:8000"
```
