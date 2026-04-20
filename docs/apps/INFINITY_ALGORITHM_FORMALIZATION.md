# Infinity Algorithm Formalization
Support system (inputs, observation, feedback): docs/apps/INFINITY_ALGORITHM_SUPPORT_SYSTEM.md.\r\n\r\n
This document describes implemented execution behavior and algorithmic logic from the current codebase.

**Core Computational Cycle**
Execution is request/endpoint-driven for API routes and service calls. There is no single global orchestrator loop that runs a unified deterministic -> model-based pipeline across the system.

**Input Set**
External inputs:
- User requests and messages
- Content payloads for analysis
- Telemetry and engagement signals
- Administrative actions

Persisted state inputs:
- Stored plans and sessions
- Historical metrics
- Memory nodes and links
- Configuration values

Model-generated inputs:
- Structured model responses
- Model-derived scores and summaries

**Transformation Functions**
Scoring functions:
- Compute scalar metrics from observed signals using weighted or normalized formulas.
- Example form: `Score = f(Signals)`.

State transition functions:
- Update state based on current state and action.
- Example form: `State' = g(State, Action)` with conditional branches.

Time delta calculations:
- Compute elapsed time in seconds: `delta_t = t_now - t_start`.
- Use `delta_t` to update durations and time-based metrics.

Projection logic:
- Derive future estimates using historical rates and compression factors.
- Example form: `t_est = t_now + (d_rem / r_eff)` with `r_eff = r / C`.

Optimization logic:
- Select conservative, aggressive, or optimal outcomes by percentile or extrema of rates.

**Constraint Enforcement Layer**
Lock conditions:
- Once a session or plan is locked, further changes are rejected.

Single active state enforcement:
- Only one plan may be active at any time; activating one deactivates others.

Uniqueness constraints:
- Link relations must be unique across source, target, and type.

Permission validation:
- Mutations require JWT validation; legacy permission signatures are ignored.

**Recurrence / Background Loops**
Implemented background loops exist in `AINDY/services/task_services.py`:
- `check_reminders()`: infinite loop, scans tasks, clears triggered reminders, sleeps 60 seconds.
- `handle_recurrence()`: infinite loop, queries completed tasks, sleeps 60 seconds.

Outside these functions, execution is triggered by endpoint calls and direct function invocation.

**Output Set**
Persisted updates:
- Updated tasks, plans, sessions, and memory links.

Structured responses:
- Deterministic responses for API requests and queries.

Derived metrics:
- Calculated scores, rates, and summaries.

Next-state decisions:
- Activation, locking, completion, or suspension outcomes.

**Execution Model (Pseudocode)**
```text
on endpoint request or service call:
  validate request/context as implemented by that handler
  run handler-specific computations
  persist updates when implemented
  return handler-specific response

in task_services background workers:
  check_reminders() loops forever with 60s sleep
  handle_recurrence() loops forever with 60s sleep
```

**Mathematical Notation**
Scoring:
- `S = f(X)` where `X` is a vector of observed signals.
- Denominator guards are included only where explicitly implemented by individual functions.

Time-based updates:
- `delta_t = t_now - t_start`
- `duration' = duration + delta_t`

Projection:
- `r_eff = r / C`
- `d_adj = d_rem / r_eff`
- `t_est = t_now + d_adj`
- For projection ETA only: if `r <= 0` or `r_eff <= 0`, return `target_date`.

Selection:
- `r_conservative = P_30(R)`
- `r_aggressive = P_70(R)`
- `r_optimal = max(R)`

**Invocation Pattern**
```text
No universal global pipeline is implemented.
Each endpoint/service applies only the logic it invokes.
Ordering between deterministic and model-based steps is handler-specific.
```

**State Transition Diagram (Text)**
```text
Pending
  -> In Progress (start action, only when start_time is not set)
Completed
  -> In Progress (start action, when start_time is not set; no completed-state guard)
In Progress
  -> Paused (pause action)
Pending
  -> Completed (complete action)
In Progress
  -> Completed (complete action)
Paused
  -> Completed (complete action)
Completed
  -> Completed (complete action; repeated completion is allowed by implementation)
```

`complete_task` in `AINDY/services/task_services.py` sets `status = "completed"` without checking prior status, so repeated completion requests can keep the task in `completed` state and re-run completion-side effects.

**Logic Separation**
Deterministic logic:
- Rule-based state transitions
- Arithmetic scoring
- Projection calculations (percentiles, extrema, and ETA arithmetic)
- Constraint enforcement

Probabilistic or model-based logic:
- Model-derived summaries
- Model-derived scores

Time-based logic:
- Elapsed time calculations
- Periodic evaluations
- ETA offsets from deterministic projection arithmetic

Constraint-based logic:
- Lock enforcement
- Single active state enforcement
- Uniqueness validation
- Permission validation
