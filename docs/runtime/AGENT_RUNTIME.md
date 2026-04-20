# Agent Runtime

This document describes the agent runtime subsystem in `AINDY/agents/`. It
covers the execution contract, public API surface, capability enforcement model,
and recovery behavior. For the app-layer Agentics feature (gap analysis,
completion roadmap, Nodus integration plan) see
[docs/apps/AGENTICS.md](../apps/AGENTICS.md).

---

## 1. What the Agent Runtime Is

The agent runtime is a domain-agnostic execution subsystem in `AINDY/agents/`.
It owns:

- plan generation (GPT-4o structured planner)
- the approval trust gate
- per-run capability token minting
- deterministic step execution via `PersistentFlowRunner`
- per-step retry with configurable high-risk no-retry policy
- run lifecycle persistence (`AgentRun`, `AgentStep`, `AgentEvent`)
- stuck-run recovery at startup
- replay from a prior run's plan

The runtime does not own domain logic. Tool implementations that call tasks,
memory, ARM, or the Infinity Loop live in `apps/` and are invoked through the
registered tool registry.

---

## 2. Execution Lifecycle

```
POST /agent/run  (create)
│
├─ agent_runtime.create_agent_run()
│   └─ GPT-4o structured plan generation
│
├─ POST /agent/run/{id}/approve  (trust gate)
│   └─ agent_runtime.approve_agent_run()
│       └─ capability tokens minted for this run
│
├─ agent_runtime.execute_agent_run()
│   ├─ NodusAgentAdapter wraps PersistentFlowRunner
│   ├─ per-step: check capability token, execute tool, persist AgentStep
│   ├─ per-step retry: transient failures retry; high-risk steps do not retry
│   └─ emit AgentEvent for each step outcome
│
└─ post-execution
    ├─ memory capture (memory_capture_engine)
    └─ infinity_orchestrator.execute() (score recalculation)
```

A run that is rejected at the trust gate writes a `REJECTED` AgentRun record
and stops. It does not execute any steps.

---

## 3. Public API Surface

All public functions are in `AINDY/agents/agent_runtime.py`. Functions prefixed
`_` are private — do not call them from outside this module.

| Function | Description |
|---|---|
| `create_agent_run(user_id, goal, db)` | Generate plan, persist AgentRun with PENDING status |
| `approve_agent_run(run_id, db)` | Validate plan, mint capability tokens, transition to APPROVED |
| `reject_agent_run(run_id, reason, db)` | Persist rejection reason, transition to REJECTED |
| `execute_agent_run(run_id, db)` | Execute the approved plan through NodusAgentAdapter |
| `recover_agent_run(run_id, db)` | Restart a STUCK run from the last completed step |
| `replay_agent_run(run_id, db)` | Create a new run from a prior run's plan |
| `run_to_dict(run)` | Serialize an AgentRun to dict for API responses |

`run_to_dict` is the canonical serializer for `AgentRun` objects. It is used by
`agent_router.py` and `automation_flows.py`. Do not call `_run_to_dict` directly
— use `run_to_dict`.

---

## 4. Capability Enforcement

Each approved run receives a scoped `CapabilityToken` listing the tools it is
allowed to call. Enforcement happens at two points:

1. **Before flow execution** — `capability_service.validate_run_scope()` checks
   that the plan's required tools are all within the approved token.
2. **Before each tool call** — `capability_service.check_tool_permission()` is
   called inside each node function before the tool executes.

A tool call that fails either check raises `CapabilityViolation`. This is
treated as a non-retryable `FAILURE` step — the run halts immediately.

The capability token is stored on the `AgentRun` record and does not change
after approval. Modifying the token post-approval is not permitted.

---

## 5. Per-Step Retry Policy

The runtime uses `AINDY/runtime/RETRY_POLICY.md` for all retry decisions.
The agent-specific rules are:

- **Transient failures** (network timeout, downstream 5xx): retry up to 3 times
  with exponential backoff.
- **High-risk steps** (tool metadata `high_risk: true`): no retry regardless of
  failure type. The step fails immediately and the run halts.
- **Capability violations**: no retry. Treated as a fatal configuration error.
- **Plan exhausted**: if all steps complete successfully the run transitions to
  `COMPLETED`.

Each step outcome is persisted as an `AgentStep` row before the retry decision
is made, so the full attempt history is always visible.

---

## 6. Recovery and Replay

### Startup recovery

`scan_and_recover_stuck_runs()` is called in `main.py lifespan()` after
`load_plugins()`. It queries for any `AgentRun` rows in `RUNNING` state and
calls `recover_agent_run()` on each. This handles server crashes during
execution.

A recovered run resumes from the last persisted `AgentStep` — it does not
re-execute completed steps.

### Manual recovery

`POST /agent/run/{id}/recover` calls `recover_agent_run()` directly. Returns
`409 Conflict` if the run is already in a terminal state.

### Replay

`POST /agent/run/{id}/replay` calls `replay_agent_run()`. This creates a new
`AgentRun` with status `PENDING` using the original run's plan verbatim. The
new run must go through the normal approve → execute path. The new run stores
`replayed_from_run_id` pointing to the source run.

---

## 7. AgentRun State Machine

```
PENDING → APPROVED → RUNNING → COMPLETED
                             → FAILED
       → REJECTED
RUNNING → STUCK  (detected at startup or via /recover endpoint)
STUCK   → RUNNING (via recover)
COMPLETED → (new PENDING via replay)
```

The only terminal states are `COMPLETED`, `FAILED`, and `REJECTED`. Runs in
these states cannot be transitioned further — create a new run or replay.

---

## 8. Event Persistence

Every state transition emits an `AgentEvent` row via `emit_event()`. Events
are also broadcast to Redis pub/sub for cross-instance observability.

Key event types:

| Event | Trigger |
|---|---|
| `agent.run.created` | `create_agent_run()` completes |
| `agent.run.approved` | `approve_agent_run()` completes |
| `agent.run.rejected` | `reject_agent_run()` completes |
| `agent.step.completed` | each step finishes successfully |
| `agent.step.failed` | each step fails (all retry attempts exhausted) |
| `agent.run.completed` | final step succeeds |
| `agent.run.failed` | a non-retryable failure halts the run |
| `agent.run.recovered` | `recover_agent_run()` transitions STUCK → RUNNING |

The `AgentEvent` timeline is accessible at
`GET /agent/run/{id}/timeline`.

---

## 9. Boundary Rules

The agent runtime must not import from `apps.*` at module level. All
cross-domain calls (to tasks, masterplan, analytics, social) are made through
registered tool functions or through the syscall dispatcher. This keeps the
runtime importable at startup independent of any domain app's health.

See [PLUGIN_REGISTRY_PATTERN.md](../architecture/PLUGIN_REGISTRY_PATTERN.md)
for the registration model and
[CROSS_DOMAIN_COUPLING.md](../architecture/CROSS_DOMAIN_COUPLING.md) for the
coupling rules that apply to the Infinity Loop post-execution integration.
