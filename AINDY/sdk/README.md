# A.I.N.D.Y. SDK (v1)

Python SDK for the A.I.N.D.Y. platform — memory, flows, syscalls, Nodus scripts, and events.

**Zero external dependencies.** Pure stdlib (`urllib`, `json`). Requires Python 3.10+.

For full API reference, examples, error handling, and the response envelope see
[docs/sdk/index.md](../../docs/sdk/index.md).

---

## Installation

```bash
# From the sdk/ directory
pip install -e .

# Or copy the aindy/ package into your project directly
```

## Quick start

```python
from AINDY.sdk.aindy_sdk import AINDYClient

client = AINDYClient(
    base_url="http://localhost:8000",
    api_key="aindy_your_platform_key",
)

tasks  = client.memory.read("/memory/shawn/tasks/**")
result = client.flow.run("analyze_tasks", {"nodes": tasks["data"]["nodes"]})
client.memory.write("/memory/shawn/insights/outcome", result["data"]["summary"])
```

## Server-side requirement

Run `alembic upgrade head` and restart the server before using the SDK against
a freshly updated backend (requires the `POST /platform/syscall` endpoint).
