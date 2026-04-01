# Nodus Flows

Standalone `.nodus` scripts used across all examples. Upload any of them once and reference by name.

---

## Upload all scripts

```bash
python upload_scripts.py
```

Output:

```
Uploading Nodus scripts...
  ✓ memory_analyze     (analyze.nodus)
  ✓ approval_flow      (approval_flow.nodus)
  ✓ daily_briefing     (daily_briefing.nodus)
  ✓ task_processor     (task_processor.nodus)

4 script(s) uploaded.
```

## Scripts

| File | Name | Used in |
|------|------|---------|
| `analyze.nodus` | `memory_analyze` | memory-analyzer |
| `approval_flow.nodus` | `approval_flow` | event-automation |
| `daily_briefing.nodus` | `daily_briefing` | scheduled-agent |
| `task_processor.nodus` | `task_processor` | general purpose |

## Use any script

```python
result = client.nodus.run_script(
    script_name="memory_analyze",
    input={"namespace": "/memory/your/namespace", "limit": 50},
)
print(result["output_state"]["summary"])
```
