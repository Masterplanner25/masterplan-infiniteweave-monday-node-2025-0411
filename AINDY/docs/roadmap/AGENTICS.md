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

**Implemented in A.I.N.D.Y.:**
- Memory Bridge (persistence + recall + feedback)
- JWT/API‑key auth gates
- Task tracking + analytics ingestion
- Genesis + MasterPlan lifecycle
- ARM (analysis + generation)

**Implemented in Nodus (external runtime):**
- Workflow/goal DSL → task graphs
- Persistent graph snapshots + checkpoints
- Scheduler + worker dispatch
- Runtime event bus + tracing
- HTTP runtime service

**Missing from A.I.N.D.Y.:**
- Agent plan/dry‑run/approve/execute loop
- Capability issuance + enforcement
- Approval inbox + audit viewer
- Deterministic execution substrate wired into core flows

---

## 5. Doc → Code Parity Table

| Documented Capability | Implementation Reality | Status | Primary Files |
| --- | --- | --- | --- |
| Plan → Dry‑Run → Approve → Execute → Verify | Concept only | Missing | N/A |
| Capability descriptors + scoped tokens | Concept only | Missing | N/A |
| Approval gates (risk policy) | Concept only | Missing | N/A |
| Deterministic workflow engine | Exists in Nodus, not wired | Partial | `C:\dev\Coding Language\src\nodus\*` |
| Audit/event log for agents | Not implemented | Missing | N/A |
| Sandbox + egress control | Concept only | Missing | N/A |
| LLM planner/executor/verifier separation | Concept only | Missing | N/A |
| Memory integration | Implemented (Memory Bridge) | Implemented | `AINDY/bridge`, `AINDY/db/dao/memory_node_dao.py` |

---

## 6. Gap → File Mapping

| Gap | Impact | Files to Update |
| --- | --- | --- |
| No agent runtime loop | No deterministic execution | N/A (new layer required) |
| No capability issuance/enforcement | Unsafe execution | N/A |
| No approvals UI | No human‑in‑the‑loop control | `client/src/components/*` |
| Nodus not integrated | Execution remains ad‑hoc | N/A |
| No audit/event stream | No replay or traceability | `db/models/*`, `routes/*` |

---

## 7. Risk Register

| Risk | Type | Failure Mode | Impact | Likely? |
| --- | --- | --- | --- | --- |
| Agentics assumed implemented | Docs drift | Team expects agent runtime | High | High |
| No deterministic execution | Runtime | Actions remain brittle/manual | High | High |
| No capability enforcement | Security | Over‑privileged execution risk | High | Medium |
| No approvals layer | Governance | No human control for risky steps | High | Medium |
| Nodus integration not wired | Architecture | Orchestration remains ad‑hoc | Medium | High |

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

Agentics is currently **conceptual only** within A.I.N.D.Y. The execution
substrate exists in Nodus, but the runtime loop, policy gates, and approvals
are not integrated into the A.I.N.D.Y. stack.



## 10. Roadmap to Completion

### Phase 1 ? Minimal Runtime
**Goal:** one end-to-end agent loop  
**Build:**
- `services/agent_runtime.py` wrapper (accept request ? call planner ? structured plan ? execute)
- Basic plan schema (`goal`, `steps`, `risk_level`)
- Tool registry (wrap: task.create/update, memory.write/recall, arm.analyze)
**Output:** User ? Plan ? Execute (tools) ? Memory updated  
**Not yet:** approvals, Nodus, policies

### Phase 2 ? Dry-Run + Approval
**Goal:** control + visibility  
**Build:**
- Dry-run preview ("Here?s what I will do")
- Approval gate for high-risk plans
- `POST /agent/approve`
**Output:** Plan ? Preview ? Approve ? Execute

### Phase 3 ? Nodus Integration (Determinism)
**Goal:** deterministic execution  
**Build:**
- `services/nodus_adapter.py` mapping A.I.N.D.Y. tools ? Nodus tasks
- Replace Python loop with Nodus workflow graph
- Use `plan ? nodus.plan`, `execute ? nodus.run`, `resume ? nodus.resume`
**Output:** retries + checkpoints + replay

### Phase 4 ? Policy + Capability System
**Goal:** safe, controlled execution  
**Build:**
- Capability model (e.g., `task.create` allowed, `external.api.call` restricted)
- Policy engine enforcing approvals on restricted tools
- Token model (scoped execution tokens, expiry)
**Output:** bounded authority

### Phase 5 ? Observability + Audit
**Goal:** full traceability  
**Build:**
- Agent execution tables (`agent_runs`, `agent_steps`, `agent_events`)
- Event logging: PLAN_CREATED, STEP_EXECUTED, STEP_FAILED, APPROVED, COMPLETED
- Correlation IDs for every run
**Output:** replayable execution history

### Phase 6 ? Full Loop Integration
**Goal:** connect all systems  
**Connect:**
- Memory Bridge (recall before plan, write after execution)
- Infinity Algorithm (scoring influences plan decisions)
- Support System (signals feed plans)
- RippleTrace (external impact tracking)
**Output:** signal ? plan ? execute ? feedback ? memory ? better plan

### Phase 7 ? UI Layer (Optional)
**Goal:** usable interface  
**Build:**
- Approval inbox
- Execution timeline viewer
- Agent run inspector

### Final State (Agentics Complete)
User/Trigger  
? Agent Runtime (Agentics)  
? Plan ? Dry-Run ? Approve ? Execute (Nodus)  
? Verify ? Observe ? Memory Bridge  
? Feedback ? Next Plan

---

## 11. Summary (Operational Truth)

Agentics is currently **conceptual only** within A.I.N.D.Y. The execution
substrate exists in Nodus, but the runtime loop, policy gates, and approvals
are not integrated into the A.I.N.D.Y. stack.
