# Agentics — Canonical Definition & Feasibility Audit

---

## 1. System Definition (Canonical)

Agentics is the conceptual **agent runtime layer** for A.I.N.D.Y. It is not
implemented yet. It is the execution control plane that:

- plans actions with explicit tools
- produces a dry‑run preview
- enforces approvals based on risk/capability
- executes deterministically via a workflow engine
- verifies outcomes and logs audit trails

This layer is the bridge from **decision** to **reliable execution**.

---

## 2. Core Lifecycle (Canonical Pipeline)

```
Plan → Dry‑Run → Approve → Execute → Verify → Observe → Memory
```

---

## 3. Conceptual Components (From Agentics Docs)

- **Runtime**: supervision, scheduling, sandboxing, logs
- **Capabilities**: scoped permissions + tokens
- **Policy engine**: risk scoring + approvals
- **LLM orchestration**: planner/executor/verifier separation
- **Memory system**: vector + structured + event log
- **Integrations hub**: API/CLI adapters with schemas
- **Observability**: audit + replay + traces
- **Human interfaces**: approvals inbox, audit viewer

Primary source docs:
- `AINDY/Agentics/Plan.txt`
- `AINDY/Agentics/A.I.N.D.Y. Plan.txt`
- `AINDY/Agentics/Real Agent Framework.txt`
- `AINDY/Agentics/Definition of DONE.txt`
- `AINDY/Agentics/API Strategy_*`
- `AINDY/Agentics/Deployment Strategy.txt`

---

## 4. Current Implementation (Reality)

**Implemented in A.I.N.D.Y. (Sprints N+4 through N+8):**
- ✅ Agent plan/dry‑run/approve/execute loop (`services/agent_runtime.py`)
- ✅ GPT-4o planner with JSON mode + overall_risk enforcement
- ✅ 9-tool registry with risk levels (`services/agent_tools.py`)
- ✅ Trust gate: high-risk always approval-gated; low/medium configurable via `AgentTrustSettings`
- ✅ `AgentRun` / `AgentStep` / `AgentTrustSettings` ORM models + migrations
- ✅ Deterministic execution via `PersistentFlowRunner` (`services/nodus_adapter.py`)
  - `AGENT_FLOW`: validate → execute_step (self-loop) → finalize
  - Per-step retry: low/medium 3x; high-risk 1 attempt (no silent replay)
  - DB checkpointing after each node via `PersistentFlowRunner`
  - `FlowHistory → Memory Bridge` capture on completion
- ✅ `flow_run_id` on `AgentRun` — audit trail to `FlowRun`
- ✅ KPI-aware planner injection (Infinity Score snapshot in system prompt)
- ✅ `suggest_tools()` — KPI-driven tool recommendations
- ✅ Stuck-run recovery: startup scan + `POST /recover` + `POST /replay`
- ✅ `replayed_from_run_id` lineage tracking on `AgentRun`
- ✅ `AgentConsole.jsx` — goal input, plan preview, approve/reject, step timeline, suggestion chips, Timeline tab, pending-approval badge
- ✅ 13 agent API endpoints (added `GET /agent/runs/{run_id}/events`)
- ✅ Structured event log (`AgentEvent` table) — PLAN_CREATED, APPROVED, REJECTED, EXECUTION_STARTED, COMPLETED, EXECUTION_FAILED, RECOVERED, REPLAY_CREATED
- ✅ `correlation_id` (`run_<uuid4>`) on `AgentRun` + `AgentStep` + `AgentEvent` — propagated through full lifecycle
- ✅ `emit_event()` — non-fatal lifecycle event emitter (`services/agent_event_service.py`)
- ✅ `GET /agent/runs/{run_id}/events` — unified timeline: lifecycle events + synthesised step events
- ✅ `new_plan` replay mode in `replay_run()` — re-calls GPT-4o for fresh plan on same goal

**Implemented in A.I.N.D.Y. (pre-N+4):**
- Memory Bridge (persistence + recall + feedback)
- JWT/API‑key auth gates
- Task tracking + analytics ingestion
- Genesis + MasterPlan lifecycle
- ARM (analysis + generation)

**Note on Nodus pip package:**
The installed `nodus` pip package is a separate scripting-language VM (`.nd` files, filesystem JSON checkpoints, requires Nodus VM closures). It has zero integration path with AINDY's PostgreSQL stack and is NOT used. `PersistentFlowRunner` in `services/flow_engine.py` is the deterministic execution substrate.

**Still Missing from A.I.N.D.Y.:**
- Capability issuance + enforcement (scoped tokens, egress control) — Agentics Phase 4
- Full audit viewer UI (dedicated approval inbox, execution trace browser)

---

## 5. Doc → Code Parity Table

| Documented Capability | Implementation Reality | Status | Primary Files |
| --- | --- | --- | --- |
| Plan → Dry‑Run → Approve → Execute | Fully implemented | ✅ Done (N+4) | `services/agent_runtime.py`, `routes/agent_router.py` |
| Approval gates (risk policy) | Trust gate + high-risk invariant | ✅ Done (N+4) | `services/agent_runtime.py::_requires_approval()` |
| Deterministic workflow engine | PersistentFlowRunner wired | ✅ Done (N+6) | `services/nodus_adapter.py`, `services/flow_engine.py` |
| Audit/event log for agents | `AgentRun` + `AgentStep` tables | ✅ Done (N+4) | `db/models/agent_run.py` |
| Replay + traceability | `/recover` + `/replay` + `flow_run_id` | ✅ Done (N+7) | `services/stuck_run_service.py`, `services/agent_runtime.py` |
| Memory integration | FlowHistory → Memory Bridge | ✅ Done (N+6) | `services/flow_engine.py::_capture_flow_completion()` |
| KPI → plan adaptation | Infinity Score injected into planner | ✅ Done (N+5) | `services/agent_runtime.py::_build_kpi_context_block()` |
| Capability descriptors + scoped tokens | Concept only | ❌ Missing | N/A — Agentics Phase 4 |
| Sandbox + egress control | Concept only | ❌ Missing | N/A — Agentics Phase 4 |
| LLM verifier separation | Concept only | ❌ Missing | N/A — Agentics Phase 4+ |

---

## 6. Gap → File Mapping

| Gap | Impact | Files to Update |
| --- | --- | --- |
| No capability issuance/enforcement | Unsafe execution for high-privilege tools | New: `services/capability_service.py`, `db/models/capability.py` |
| No dedicated approval inbox UI | Pending runs badge added (N+8) but no standalone inbox view | New: `client/src/components/AgentApprovalInbox.jsx` |
| ~~No `new_plan` replay mode~~  | ✅ RESOLVED (N+8) — `replay_run(mode="new_plan")` re-calls GPT-4o for fresh plan | `services/agent_runtime.py::replay_run()` |
| No egress/sandbox control | Tools can call external APIs without constraint | New policy layer |

---

## 7. Risk Register

| Risk | Type | Failure Mode | Impact | Likely? |
| --- | --- | --- | --- | --- |
| ~~Agentics assumed implemented~~ | ~~Docs drift~~ | ~~Team expects agent runtime~~ | ~~High~~ | ✅ Resolved N+4 |
| ~~No deterministic execution~~ | ~~Runtime~~ | ~~Actions remain brittle/manual~~ | ~~High~~ | ✅ Resolved N+6 |
| No capability enforcement | Security | Over‑privileged execution risk | High | Medium |
| No approvals layer (UI) | Governance | Pending runs not surfaced proactively | Low | Low (badge added N+8) |
| ~~Nodus integration not wired~~ | ~~Architecture~~ | ~~Orchestration remains ad‑hoc~~ | ~~Medium~~ | ✅ Resolved N+6 (PersistentFlowRunner) |

---

## 8. Feasibility Summary

Feasibility is **high** because:
- Nodus already provides deterministic workflows + checkpoints.
- A.I.N.D.Y. already provides memory + policy surfaces.

The missing elements are **integration glue + policy enforcement**, not
fundamental execution primitives.

---

## 9. Nodus Integration Feasibility Memo (Concise)

### What Nodus already provides (usable now)
- Workflow/goal DSL that compiles to task graphs with retries + checkpoints.
- Persistent graph snapshots for resume/replay.
- Scheduler + worker dispatch with capability matching.
- Runtime event bus for traceability.
- HTTP runtime service mode (plan/run/resume endpoints).

### What A.I.N.D.Y. already provides (ready to leverage)
- Memory Bridge (recall/write/feedback) as the memory substrate.
- JWT/API‑key auth for gating calls.
- Task/Genesis/ARM services that can be wrapped as tools.

### What is missing (integration glue)
- A thin adapter to register A.I.N.D.Y. services as Nodus tools/agents.
- Policy enforcement layer for capability issuance + approvals.
- A.I.N.D.Y. audit table or event stream for PLAN/EXECUTE/VERIFY phases.

### Feasibility verdict
High. Nodus already supplies the deterministic execution substrate that Agentics
requires. A.I.N.D.Y. can embed Nodus with a minimal runtime adapter and route
plans through it. No major rewrites required.

---

## 10. Summary (Operational Truth)

As of 2026-03-25 (Sprint N+8), Agentics Phases 1–3, Phase 5, and the core of Phase 6 are
**live and tested**. The full lifecycle is operational: a user submits a goal, GPT-4o
generates a KPI-aware plan, the trust gate applies, the plan executes deterministically via
`PersistentFlowRunner`, per-step retries are enforced, the full run is checkpointed and
linked to Memory Bridge, and every lifecycle transition emits a structured `AgentEvent`
with `correlation_id` threading through `AgentRun`, `AgentStep`, and `AgentEvent`.
A `new_plan` replay mode re-calls GPT-4o for a fresh plan on the same goal.
The `AgentConsole.jsx` Timeline tab renders the full event history with colored badges,
and a pending-approval badge surfaces runs awaiting review.

The core **authority layer** is now live: scoped capability tokens gate
run-level execution and tool-level access, and agent execution fails closed when
the token is missing, invalid, or does not grant `execute_flow` / the required
tool capability. What remains is tighter egress standardization across every
non-agent executor surface and a **dedicated approval inbox UI** (Phase 7 —
standalone `AgentApprovalInbox.jsx`).

---

## 10. Roadmap to Completion

### ✅ Phase 1 — Minimal Runtime — DONE (Sprint N+4, 2026-03-24)
- `services/agent_runtime.py` — goal → GPT-4o plan → execute → memory
- 9-tool registry (`services/agent_tools.py`)
- `AgentRun` / `AgentStep` ORM models + migrations
- `POST /agent/run`, `GET /agent/runs`, `GET /agent/runs/{id}/steps`

### ✅ Phase 2 — Dry-Run + Approval — DONE (Sprint N+4, 2026-03-24)
- Plan returned as preview before execution
- Trust gate: high-risk always gates; low/medium configurable via `AgentTrustSettings`
- `POST /agent/runs/{id}/approve`, `POST /agent/runs/{id}/reject`
- `AgentConsole.jsx` — plan preview, risk badge, approve/reject controls

### ✅ Phase 3 — Deterministic Execution — DONE (Sprint N+6, 2026-03-25)
- `services/nodus_adapter.py` — `NodusAgentAdapter` + `AGENT_FLOW`
- `PersistentFlowRunner` replaces N+4 for-loop
- Per-step retry (low/medium: 3x; high: halt immediately, no silent replay)
- DB checkpointing after each node; `FlowHistory → Memory Bridge` on completion
- `flow_run_id` on `AgentRun` for audit trail

### Phase 4 — Policy + Capability System — TODO
- Capability model (scoped tool permissions)
- Policy engine enforcing approval on restricted tools
- Token model (scoped execution tokens, expiry)
- **Output:** bounded authority per agent run

### ✅ Phase 5 — Observability + Audit — DONE (Sprint N+7 + N+8, 2026-03-25)
- `agent_runs` + `agent_steps` tables with full audit data ✅ (N+4)
- `flow_run_id` correlation: every run links to its `FlowRun` ✅ (N+6)
- Stuck-run startup scan + manual `/recover` endpoint ✅ (N+7)
- `/replay` endpoint with `replayed_from_run_id` lineage ✅ (N+7)
- Unified serializer: all 13 endpoints return consistent run shape ✅ (N+7)
- `AgentEvent` table — 8 lifecycle event types, `correlation_id` threading ✅ (N+8)
- `emit_event()` — always non-fatal lifecycle event emitter ✅ (N+8)
- `GET /agent/runs/{run_id}/events` — merged timeline: lifecycle + step events ✅ (N+8)
- `new_plan` replay mode — re-calls GPT-4o for fresh plan on same goal ✅ (N+8)

### ✅ Phase 6 (partial) — System Integration — DONE (Sprint N+5, 2026-03-24)
- Memory Bridge: `FlowHistory → Memory Bridge` capture on run completion ✅
- Infinity Algorithm: live KPI snapshot injected into planner system prompt ✅
- `suggest_tools()`: KPI-driven tool suggestions surfaced in `AgentConsole.jsx` ✅
- Remaining: RippleTrace signal → plan trigger (deferred)

### Phase 7 — UI Layer — Partial
- ✅ `AgentConsole.jsx` — goal input, plan preview, approve/reject, step timeline, suggestion chips, Timeline tab, pending-approval badge (N+8)
- ❌ Dedicated approval inbox (`AgentApprovalInbox.jsx`) — pending runs not surfaced in a standalone view
- ❌ Execution trace browser / visual FlowRun inspector

### Current State (Sprint N+9, 2026-03-25)
```
User/Trigger
→ AgentConsole.jsx (goal input + suggestion chips + pending-approval badge)
→ POST /agent/run → generate_plan() [GPT-4o, KPI-aware]
→ emit_event(PLAN_CREATED, correlation_id=run_<uuid4>)
→ Trust gate → pending_approval | approved
→ POST /agent/runs/{id}/approve → emit_event(APPROVED)
→ emit_event(EXECUTION_STARTED)
→ NodusAgentAdapter.execute_with_flow(correlation_id=...)
   └─ PersistentFlowRunner(AGENT_FLOW)
        ├─ agent_validate_steps
        ├─ agent_execute_step (loop, per-step retry, correlation_id on AgentStep)
        └─ agent_finalize_run → Memory Bridge capture → emit_event(COMPLETED)
→ AgentRun.status = "completed" | "failed"
→ POST /agent/runs/{id}/recover  (stuck recovery → emit_event(RECOVERED))
→ POST /agent/runs/{id}/replay   (lineage-tracked → emit_event(REPLAY_CREATED))
→ GET  /agent/runs/{id}/events   (merged lifecycle + step timeline)
```
