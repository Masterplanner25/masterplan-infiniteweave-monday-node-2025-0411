---
title: "Retry Policy"
last_verified: "2026-04-18"
api_version: "1.0"
status: current
owner: "platform-team"
---
# Retry Policy

## Purpose

`core/retry_policy.py` is the single source of truth for all retry semantics across
every execution type in A.I.N.D.Y.  Before this layer existed, retry limits were
scattered as hardcoded integers across three files:

| File | Hardcoded value | Replaced by |
|---|---|---|
| `runtime/flow_engine.py` | `POLICY["max_retries"] = 3` | `_FLOW_RETRY_POLICY.max_attempts` |
| `runtime/nodus_adapter.py` | `1 if risk_level == "high" else MAX_STEP_RETRIES` | `resolve_retry_policy(execution_type="agent", risk_level=...)` |
| `platform_layer/async_job_service.py` | implicit always-fail | `log.attempt_count < log.max_attempts` |

---

## Data model

```python
@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int          # total tries (1 = no retry)
    backoff_ms: int = 0        # delay between attempts; 0 = no sleep (current default everywhere)
    exponential_backoff: bool = False
    high_risk_immediate_fail: bool = False  # stop on first error regardless of max_attempts
```

---

## Named constants

| Constant | max_attempts | high_risk_immediate_fail | Maps to |
|---|---|---|---|
| `FLOW_NODE_DEFAULT` | 3 | False | `flow_engine.POLICY["max_retries"]` (old) |
| `AGENT_LOW_MEDIUM` | 3 | False | `nodus_adapter.MAX_STEP_RETRIES` (old) |
| `AGENT_HIGH_RISK` | 1 | True | `if risk_level == "high": break` (old) |
| `ASYNC_JOB_DEFAULT` | 1 | False | `max_attempts=1` default in async_job_service |
| `NODUS_SCHEDULED_DEFAULT` | 3 | False | `NodusScheduledJob.max_retries` default |
| `NO_RETRY` | 1 | False | `task_orchestrate` RETRY→FAILURE mapping |

---

## Resolver

```python
resolve_retry_policy(
    *,
    execution_type: str,           # "flow" | "agent" | "job" | "nodus"
    risk_level: str | None,        # agent only: "low" | "medium" | "high"
    node_max_retries: int | None,  # per-node flow override
    job_max_retries: int | None,   # per-job nodus scheduled override
) -> RetryPolicy
```

Resolution order per execution type:

- `"flow"` — `FLOW_NODE_DEFAULT`; overridden by `node_max_retries` when provided
- `"agent"` — `AGENT_LOW_MEDIUM` for low/medium; `AGENT_HIGH_RISK` for high (default when risk_level is absent)
- `"job"` — `ASYNC_JOB_DEFAULT`
- `"nodus"` — `NODUS_SCHEDULED_DEFAULT`; overridden by `job_max_retries` when provided; also triggered by `workflow_type.startswith("nodus")` on `"job"` EU type
- unknown — `NO_RETRY` (safe default)

---

## Execution paths and where the policy is read

### Flow nodes (`runtime/flow_engine.py`)

```text
PersistentFlowRunner.resume()
  node returns "RETRY" status
    → _node_cfg = self.flow.get("node_configs", {}).get(current_node, {})
    → _run_policy = resolve_retry_policy(
          execution_type="flow",
          node_max_retries=_node_cfg.get("max_retries"),  # None → default
      )
    → if attempts < _run_policy.max_attempts → continue (retry)
    → else → _fail_execution(...)
```

When `node_configs` is absent (every flow except a per-run override), `_node_cfg` is `{}`
and `get("max_retries")` returns `None`, so `resolve_retry_policy` returns `FLOW_NODE_DEFAULT`
(max_attempts=3) — identical to the old hardcoded behavior.

### Agent steps (`runtime/nodus_adapter.py`)

```text
_execute_agent_step(step, ...)
  → _step_policy = resolve_retry_policy(
        execution_type="agent",
        risk_level=step.get("risk_level", "high"),
    )
  → max_attempts = _step_policy.max_attempts
  → for attempt in range(1, max_attempts + 1):
        execute_tool(...)
        if success: break
        if _step_policy.high_risk_immediate_fail: break   # was: if risk_level == "high"
        if attempt < max_attempts: log warning
```

### Async jobs (`platform_layer/async_job_service.py`)

```text
_execute_job_inline(log_id, task_name, payload)
  log.attempt_count += 1          ← incremented BEFORE handler call
  handler(payload, db)
    success → log.status = "success"
    exception →
      if log.attempt_count < log.max_attempts:   ← retry check
          log.status = "pending"
          db.commit()
          _get_executor().submit(_execute_job, log_id, ...)   ← reschedule
          return
      else:
          log.status = "failed"   ← terminal
```

`log.max_attempts` is set at submission time (`submit_async_job(max_attempts=1)` default).
With the current default of 1, `attempt_count >= max_attempts` after the first try — no
behavior change. When a caller passes `max_attempts > 1`, retries fire automatically.

### Nodus scheduled jobs — full data flow

This path previously had a gap: `NodusScheduledJob.max_retries` was stored correctly in
`AutomationLog.max_attempts` but the flow engine always defaulted to 3 retries.

```text
NodusScheduledJob  (DB row, max_retries=1)
  └── _run_scheduled_job(job_id)
        AutomationLog.max_attempts = job.max_retries   ← correct audit trail

        run_nodus_script_via_flow(
            script          = job.script,
            error_policy    = job.error_policy,
            node_max_retries = job.max_retries,        ← NEW: threads the value in
            ...
        )
          if node_max_retries is not None:
              flow = {
                  **FLOW_REGISTRY["nodus_execute"],
                  "node_configs": {
                      "nodus.execute": {"max_retries": node_max_retries}
                                     ↑
                              max_retries ENTERS node_config HERE
                  },
              }
          PersistentFlowRunner(flow=flow, ...)
            └── resume()
                  nodus.execute returns "RETRY"
                    → _node_cfg = flow["node_configs"]["nodus.execute"]
                                  = {"max_retries": 1}
                    → _run_policy = resolve_retry_policy(
                          execution_type="flow",
                          node_max_retries=1,
                      )  → RetryPolicy(max_attempts=1)
                    → if 0 < 1 → retry  (attempt 1)
                    → if 1 < 1 → False  → _fail_execution()
```

The shared `NODUS_SCRIPT_FLOW` module-level dict is never mutated.
Each call to `run_nodus_script_via_flow` with `node_max_retries` gets its own
shallow-copied flow dict with the per-run `node_configs` key.

### ExecutionUnit metadata

`require_execution_unit()` in `core/execution_gate.py` resolves and persists
`retry_policy` into `ExecutionUnit.extra` (JSONB) for every execution:

```text
require_execution_unit(eu_type="job", extra={"workflow_type": "nodus_schedule", ...})
  → _resolve_policy_for_eu("job", {"workflow_type": "nodus_schedule", ...})
       workflow_type.startswith("nodus") → exec_type = "nodus"
       resolve_retry_policy(execution_type="nodus")
       → {"max_attempts": 3, "backoff_ms": 0,
          "exponential_backoff": False, "high_risk_immediate_fail": False}
  → extra["retry_policy"] = <above dict>
  → ExecutionUnit.extra = extra   (JSONB persisted)
```

Any code holding the EU can read `eu.extra["retry_policy"]` without importing `RetryPolicy`.

---

## Backoff

`backoff_ms=0` in all current policy constants — no sleep between retries anywhere in
the execution layer.  The field is present so callers can introduce delay without a
schema change:

```python
# Future: per-job backoff for Nodus scheduled
resolve_retry_policy(execution_type="nodus")
# → currently RetryPolicy(max_attempts=3, backoff_ms=0, ...)
```

When a caller wants backoff it should update the relevant policy constant in
`core/retry_policy.py` so the intent remains central.

---

## Error classification

`is_retryable_error(error: str | None) -> bool` returns `False` for error strings
containing: `permission`, `unauthorized`, `forbidden`, `not found`, `404`, `401`,
`403`, `invalid`, `blocked by policy`.

Current execution loops do not call this function yet.  It is the central place
to add the check when a caller wants to short-circuit retries on non-transient errors.

---

## Adding a new execution type

1. Add a named constant to `core/retry_policy.py`.
2. Add the `execution_type` string to `resolve_retry_policy()`.
3. Add the mapping in `_EU_TYPE_TO_EXEC_TYPE` in `core/execution_gate.py` if it needs
   a new EU type.
4. Replace any inline retry integer in the new caller with a call to `resolve_retry_policy`.
