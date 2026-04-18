# A.I.N.D.Y. Documentation

**A.I.N.D.Y.** is a language-executing runtime. You write Nodus scripts that read and write memory, trigger flows, and emit events — all through a clean syscall interface.

---

## Start here

| | |
|---|---|
| [Getting Started](getting-started/index.md) | Up and running in 5 minutes |
| [Core Concepts](core-concepts/index.md) | Five things you need to know |
| [Syscall Reference](syscalls/index.md) | Every v1 syscall with examples |
| [Nodus](nodus/index.md) | The control language |
| [SDK](sdk/index.md) | Python SDK for external integrations |
| [Tutorials](tutorials/index.md) | Three end-to-end walkthroughs |

---

## What can I do with A.I.N.D.Y.?

```python
from AINDY.sdk.aindy_sdk import AINDYClient

client = AINDYClient("http://localhost:8000", api_key="aindy_...")

# Read memory, run a flow, write back the result
tasks  = client.memory.read("/memory/shawn/tasks/**")
result = client.flow.run("analyze_tasks", {"nodes": tasks["data"]["nodes"]})
client.memory.write("/memory/shawn/insights", result["data"]["summary"])
```

That's the whole pattern. Three lines. Everything else is detail.
