# Execution Contract

## Purpose

This document defines the single canonical execution contract for all user-driven and system-driven execution in A.I.N.Y.D.

It replaces the current fragmented execution patterns across:

- Agent
- Task
- Memory
- Genesis
- Watcher
- ARM

The required shape is:

`Input -> Execution -> Persist -> Orchestrator -> Observability`

`Observability` includes durable `SystemEvent` emission for both internal execution lifecycle and outbound external interactions.

Anything outside that shape is legacy behavior and should be treated as non-canonical.

## Current Entry Points

### Agent

- `POST /agent/run`
- `POST /agent/runs/{run_id}/approve`
- `POST /agent/runs/{run_id}/replay`
- Runtime: `services.agent_runtime`
- Executor: `services.nodus_adapter.NodusAgentAdapter.execute_with_flow()`

Current behavior:

- Closest subsystem to a canonical contract
- Has explicit run records, approval, step persistence, lifecycle events, and flow-backed execution

### Task

- `POST /tasks/`
- `POST /tasks/start`
- `POST /tasks/pause`
- `POST /tasks/complete`
- Runtime: `services.task_services`

Current behavior:

- Direct service mutation path
- Persistence happens first
- Memory capture, social sync, ETA, and Infinity orchestration are follow-on side effects
- No first-class execution envelope or execution event record

### Memory

- `POST /memory/execute`
- `POST /memory/nodus/execute`
- `POST /memory/recall`
- `POST /memory/recall/v3`
- Runtime: canonical flow-backed execution for `/memory/execute`; separate Nodus execution surface for `/memory/nodus/execute`

Current behavior:

- Has recall, execution, writeback, metrics, and optional trace
- `/memory/execute` is the active memory execution path
- `/memory/execute/complete` is deprecated compatibility surface and not the canonical pattern
- `/memory/nodus/execute` is still a separate execution surface, but it is now restricted by source validation, allowed-operation registration, and optional scoped capability tokens for write operations

### Genesis

- `POST /genesis/message`
- `POST /genesis/synthesize`
- `POST /genesis/lock`
- `POST /genesis/{plan_id}/activate`
- Runtime: `services.genesis_ai`, `services.masterplan_factory`

Current behavior:

- Main work is done directly in route/service code
- Flow engine is only mirrored opportunistically for observability during message handling
- Lock and activate perform side effects after the primary write

### Watcher

- `POST /watcher/signals`
- Runtime: `routes.watcher_router.receive_signals`

Current behavior:

- Ingest path is persist-first batch storage
- ETA and Infinity updates are fire-and-forget follow-ons
- No explicit execution envelope, no durable outcome record beyond stored signals

### ARM

- `POST /arm/analyze`
- `POST /arm/generate`
- Runtime: `modules.deepseek.deepseek_code_analyzer.DeepSeekCodeAnalyzer`

Current behavior:

- Execution is direct
- Domain persistence exists in `analysis_results` and `code_generations`
- No explicit shared orchestration contract around analyze/generate calls

## Canonical Pipeline

Every execution, regardless of domain, must obey this sequence:

### 1. Input

The system accepts a typed execution request with:

- `execution_id`
- `execution_type`
- `user_id`
- `trigger`
- `payload`
- `requested_by`
- `created_at`

Minimum contract:

```text
ExecutionRequest {
  execution_id
  execution_type
  user_id
  trigger
  payload
  requested_by
  correlation_id
}
```

Rules:

- Input must be validated before work starts
- Input must resolve to one domain execution type
- Every request must have a traceable owner or explicit system actor

### 2. Execution

Execution must happen through one runtime abstraction:

`ExecutionRunner.run(request) -> ExecutionResult`

The runner may delegate to a domain-specific executor, but only after the execution record exists.

Allowed domain executors:

- `agent`
- `task`
- `memory`
- `genesis`
- `watcher`
- `arm`

Rules:

- No domain executes directly from a route without going through the execution contract
- Execution must return structured output, not implicit success
- Execution must emit a terminal result: `success`, `failed`, `waiting`, or `rejected`

### 3. Persist

Before orchestration, the system must durably persist:

- execution record
- status
- normalized domain output
- error payload if failed
- timestamps

Minimum persisted shape:

```text
ExecutionRecord {
  execution_id
  execution_type
  user_id
  status
  input_payload
  output_payload
  error_payload
  started_at
  completed_at
  correlation_id
}
```

Rules:

- Persistence is not optional
- Domain tables are not enough by themselves
- A domain write without an execution record is not canonical execution

### 4. Orchestrator

After persistence, the orchestrator runs exactly once per execution result.

Responsibilities:

- score recalculation
- loop adjustment generation
- next action production
- secondary domain updates
- policy checks for follow-up work

Canonical interface:

`ExecutionOrchestrator.after_execution(record) -> OrchestrationResult`

Minimum orchestration result:

```text
OrchestrationResult {
  execution_id
  score_snapshot
  adjustment
  next_action
}
```

Rules:

- Orchestration is not best-effort glue
- If orchestration fails, the execution is not complete
- Every successful execution must produce a persisted orchestration outcome
- Every orchestrated execution must produce either:
  - `next_action`, or
  - explicit terminal marker `no_next_action_required`

### 5. Observability

Observability must be written last, but it must represent the entire lifecycle.

Required observability outputs:

- execution lifecycle event
- timing
- status transition history
- domain-specific metadata
- orchestration result reference
- outbound external-call lifecycle when execution touches third-party systems

Canonical event sequence:

```text
EXECUTION_ACCEPTED
EXECUTION_STARTED
EXECUTION_PERSISTED
EXECUTION_ORCHESTRATED
EXECUTION_COMPLETED
```

Failure sequence:

```text
EXECUTION_ACCEPTED
EXECUTION_STARTED
EXECUTION_FAILED
```

Required outbound event sequence:

```text
external.call.started
external.call.completed
```

Required outbound failure sequence:

```text
external.call.started
external.call.failed
error.external_call
```

Rules:

- No silent execution
- No untracked state mutation
- No route should return success before the lifecycle is observable
- No external interaction is allowed to occur without required outbound lifecycle events
- Failure to persist required external-call events is execution-fatal for that interaction

## Text Diagram

```text
Client or System Trigger
  -> ExecutionRequest validation
  -> ExecutionRecord created (status=accepted)
  -> Domain Executor runs
  -> Domain Result persisted to execution record
  -> ExecutionOrchestrator runs
  -> LoopAdjustment / next_action persisted
  -> Lifecycle events + metrics emitted
  -> Response returns execution_id, status, output, next_action
```

## Required Invariants

### Invariant 1: No silent execution

Every execution must create a durable execution record before domain work starts.

Disallowed:

- route directly calling service logic and returning output
- fire-and-forget domain actions without a persisted execution envelope

### Invariant 2: No side-effect-only flows

A flow is invalid if it only mutates side systems and has no canonical result object.

Disallowed:

- memory capture only
- score update only
- logging only
- watcher-triggered recalculation without an execution result

### Invariant 3: All execution produces traceable output

Every execution must return and persist:

- status
- domain output or error
- orchestration result
- next action or explicit terminal marker
- required outbound event metadata for third-party calls when present

### Invariant 4: Orchestrator is mandatory

Execution is incomplete until orchestration runs.

Disallowed:

- domain success with no score snapshot
- domain success with no loop output
- domain success with only optional best-effort orchestration

### Invariant 5: One terminal state per execution

An execution must end in one of:

- `success`
- `failed`
- `waiting`
- `rejected`

No other terminal semantics should exist in domain-specific code.

### Invariant 6: Domain persistence is separate from execution persistence

Writing `Task`, `AgentRun`, `AnalysisResult`, `GenesisSessionDB`, or `WatcherSignal` is not sufficient.

There must also be a canonical execution record.

### Invariant 7: External interactions are first-class execution facts

Any OpenAI, HTTP, watcher delivery, or other outbound third-party call triggered by execution must emit:

- `external.call.started`
- `external.call.completed` or `external.call.failed`
- `error.external_call` on failure

Minimum outbound metadata:

- `service_name`
- `endpoint`
- `model` when applicable
- `method`
- `status`
- `latency_ms`
- `error` when applicable

## Domain Examples

### Agent

Canonical path:

```text
POST /agent/run
  -> ExecutionRequest(type=agent)
  -> persist execution envelope
  -> generate plan / approval gate / execute flow
  -> persist AgentRun + steps + execution record
  -> orchestrator computes score + loop adjustment
  -> observability emits lifecycle and step events
```

Expected output:

- run id
- final status
- plan
- result
- next action

### Task

Canonical path:

```text
POST /tasks/complete
  -> ExecutionRequest(type=task.complete)
  -> persist execution envelope
  -> complete task
  -> persist Task mutation + execution result
  -> orchestrator computes score + loop adjustment
  -> observability emits completion event
```

Current gap:

- task completion writes task state first and treats orchestrator, memory, ETA, and social sync as side effects

### Memory

Canonical path:

```text
POST /memory/execute
  -> ExecutionRequest(type=memory.workflow)
  -> persist execution envelope
  -> recall context + execute + write memory + feedback
  -> persist execution result and trace id
  -> orchestrator computes score + loop adjustment
  -> observability emits execution + trace events
```

Current gap:

- `/memory/nodus/execute` is still a separate executor surface rather than a first-class flow/orchestrator path

### Genesis

Canonical path:

```text
POST /genesis/message
  -> ExecutionRequest(type=genesis.message)
  -> persist execution envelope
  -> call genesis model + update session
  -> persist session state + execution result
  -> orchestrator computes score + loop adjustment
  -> observability emits lifecycle event
```

Current gap:

- synthesis and audit flows still remain direct domain executions, even though their outbound model calls are now durably evented

### Watcher

Canonical path:

```text
POST /watcher/signals
  -> ExecutionRequest(type=watcher.ingest)
  -> persist execution envelope
  -> store batch + summarize ingest outcome
  -> orchestrator computes score + loop adjustment if trigger conditions met
  -> observability emits ingest metrics
```

Current gap:

- persistence exists for raw signals, but not for canonical execution lifecycle
- outbound signal delivery is evented, but watcher ingest itself is still not represented by a first-class execution record

### ARM

Canonical path:

```text
POST /arm/analyze
  -> ExecutionRequest(type=arm.analyze)
  -> persist execution envelope
  -> run analysis
  -> persist AnalysisResult + execution result
  -> orchestrator computes score + loop adjustment
  -> observability emits timing and outcome
```

Current gap:

- analyze/generate are domain executions without a shared execution envelope, though outbound model calls are now durably evented

## Canonical Response Shape

Every execution endpoint should eventually converge on:

```text
{
  "execution_id": "...",
  "execution_type": "...",
  "status": "success|failed|waiting|rejected",
  "domain_result": {...},
  "orchestration": {
    "score_snapshot": {...},
    "adjustment": {...},
    "next_action": {...}
  },
  "observability": {
    "correlation_id": "...",
    "trace_id": "...",
    "event_count": 0
  }
}
```

## Migration Guidance

To move the codebase onto this contract:

1. Introduce a first-class `ExecutionRecord` model.
2. Make all execution routes create that record before domain work starts.
3. Move `InfinityOrchestrator.execute()` behind a generic `ExecutionOrchestrator`.
4. Replace best-effort side effects with ordered orchestration steps.
5. Remove operational reliance on `/memory/execute/complete` and keep `/memory/execute` as the sole canonical memory execution path.
6. Make routes return canonical execution payloads instead of domain-only payloads.

## Non-Canonical Paths To Eliminate

These patterns should be considered invalid over time:

- route -> service -> commit -> explicitly logged and observable side effects
- domain execution with no execution envelope
- observability-only flow engine mirrors
- memory loop completion as a separate manual API step
- watcher-triggered orchestration without a canonical execution record
- third-party calls that do work without `SystemEvent` coverage

## Bottom Line

The canonical system model is not "domain-specific route logic plus optional extras."

It is:

`Input -> Execution -> Persist -> Orchestrator -> Observability`

If a path does not satisfy all five stages, it is legacy and should be refactored until it does.

## Identity Boot Activation

Authentication is not the whole activation path anymore.

After `POST /auth/login` returns a JWT, the frontend immediately calls:

`GET /identity/boot`

This boot path is now the canonical identity activation contract:

`Auth -> Identity Boot -> Hydrated State -> User Execution`

Signup now uses the same activation path:

`Register -> Seed Identity State -> JWT Issued -> Identity Boot -> User Execution`

On successful `POST /auth/register`, the backend seeds the first system anchor:

- `User`
- initial `Memory` node
- initialized `Execution` placeholder
- baseline `Metrics`
- required lifecycle `SystemEvent`

Current implementation guarantees:

- JWT remains the auth gate; boot does not bypass auth.
- successful register returns a usable JWT immediately; no second auth call is required
- boot returns a DB-backed user execution snapshot:
  - recent Memory Bridge nodes
  - recent AgentRun rows
  - current score metrics
  - active FlowRun rows
  - derived `system_state`
- returned memory is tagged with `context = "identity_boot"` for explicit boot provenance
- boot emits required `SystemEvent(type="identity.boot")`
- signup initialization emits required `SystemEvent(type="identity.created")`
- Infinity orchestration now injects loop context derived from the same boot primitives:
  - `user_id`
  - recent memory
  - current metrics

Implication:

- the frontend should hydrate from identity boot first, then refresh domain panels opportunistically
- blank post-login dashboards are non-canonical behavior
