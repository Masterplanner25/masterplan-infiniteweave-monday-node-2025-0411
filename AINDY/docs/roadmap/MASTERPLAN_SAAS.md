# Masterplan SaaS - Canonical Definition & Evolution Plan

---

## 1. System Definition (Canonical)

The Masterplan SaaS layer is A.I.N.D.Y.'s execution-strategy surface. It is not a
general automation SaaS. It is a **Masterplan trajectory engine** that:

- captures a strategic plan (Genesis -> MasterPlan)
- enforces lifecycle (draft -> lock -> activate)
- measures execution as time-compression against a declared target state
- prioritizes dependency resolution to compress downstream timelines

---

## 2. Core Lifecycle (Canonical Pipeline)

```text
Genesis -> MasterPlan -> Lock -> Activate -> Execute -> Measure -> Reproject
```

---

## 3. Core Components

### 3.1 Genesis (Plan Formation)

**Implementation:**
- `routes/genesis_router.py`
- `services/genesis_ai.py`
- `services/masterplan_factory.py`

**Current Capabilities:**
- guided strategic draft
- synthesis + audit
- lock into MasterPlan

---

### 3.2 MasterPlan Artifact

**Implementation:**
- `routes/masterplan_router.py`
- `db/models/masterplan.py`

**Current Capabilities:**
- versioned plan records
- posture classification
- activation state

---

### 3.3 Execution Tracking

**Implementation:**
- `routes/task_router.py`
- `services/task_services.py`
- `routes/analytics_router.py`

**Current Capabilities:**
- task tracking
- analytics ingestion
- basic dashboard overview

---

## 4. Current Implementation (Reality)

**Implemented:**
- Genesis session lifecycle (create -> message -> synthesize -> audit -> lock)
- MasterPlan creation and activation
- MasterPlan anchor fields and update endpoint
- ETA projection endpoint and dashboard panel
- Task CRUD + analytics ingestion
- dependency persistence and DAG-based blocking/unlock behavior
- MasterPlan-linked task generation and automation dispatch
- basic dashboards

**Missing or Drifted vs Masterplan Module docs:**
- full dependency-aware projection/compression modeling is still partial
- external automation connectors remain partial beyond the internal automation layer

---

## 5. Doc -> Code Parity Table

| Documented Capability | Evidence in Docs | Implementation Reality | Status | Primary Files |
| --- | --- | --- | --- | --- |
| Genesis -> MasterPlan lifecycle | Masterplan Genesis Module | Implemented | Implemented | `routes/genesis_router.py`, `services/masterplan_factory.py` |
| MasterPlan activation | Genesis Module | Implemented | Implemented | `routes/masterplan_router.py`, `client/src/components/MasterPlanDashboard.jsx` |
| Masterplan anchor / target state | Masterplan Plans doc | Anchor fields, endpoint, and UI are implemented | Implemented | `db/models/masterplan.py`, `routes/masterplan_router.py`, `client/src/components/MasterPlanDashboard.jsx` |
| ETA projection / timeline compression | Masterplan Plans doc | ETA projection exists, but only as task-velocity projection rather than full compression modeling | Partial | `services/eta_service.py`, `routes/masterplan_router.py`, `client/src/components/MasterPlanDashboard.jsx` |
| Dependency cascade model | Masterplan Plans doc | Dependency metadata, DAG construction, blocked-task enforcement, and downstream unlock behavior exist | Implemented | `db/models/task.py`, `services/task_services.py` |
| Execution automation layer | Masterplan SaaS docs | MasterPlan can generate tasks and dispatch bound automation through the execution layer; external connectors remain partial | Partial | `routes/masterplan_router.py`, `services/masterplan_execution_service.py`, `routes/automation_router.py` |
| Execution analytics dashboard | SaaS docs | Partial (MasterPlan dashboard + analytics summary exist, but no dedicated execution/compression dashboard) | Partial | `routes/analytics_router.py`, `routes/dashboard_router.py`, `client/src/components/MasterPlanDashboard.jsx` |

---

## 6. Gap -> File Mapping

| Gap | Impact | Files to Update |
| --- | --- | --- |
| ETA projection is flat velocity-based only | Masterplan can show ETA, but not dependency-aware compression or cascade effects | `services/eta_service.py`, `db/models/masterplan.py`, `services/infinity_service.py` |
| External automation connectors are still partial | Internal automation exists, but external social/CRM/payment surfaces are not fully connected | `routes/automation_router.py`, related automation services |

---

## 7. Risk Register

| Risk | Type | Failure Mode | Impact | Likely? |
| --- | --- | --- | --- | --- |
| Masterplan drift | Product | Plans exist without dependency-aware trajectory signal | Core value missing | High |
| Docs vs runtime mismatch | Product | SaaS docs understate implemented anchor/ETA features and overstate execution depth | Expectation gap | High |
| Projection still under-models dependency cascade | Technical | Blocking-task impact is only partially reflected in ETA/compression output | Weak projection quality | Medium |
| External automation connectors are partial | Business | Execution SaaS promise is only partly fulfilled | Revenue risk | High |

---

## 8. System Classification

The Masterplan SaaS layer is currently:

> A strategic planning + activation system with dependency-aware task execution
> and internal automation binding, but still partial compression modeling and
> incomplete external automation surfaces.

---

## 9. Evolution Plan (System Roadmap)

### Phase v1 - Persist Dependency Structure
**Goal:** make execution order real  
**Actions:**
- persist task dependencies in the task model ✅
- carry dependencies through task creation and retrieval ✅

### Phase v2 - Timeline Compression Output
**Goal:** make TWR actionable  
**Actions:**
- compute dependency-aware ETA shift per task batch
- return updated projection from execution endpoints

### Phase v3 - Dependency Awareness
**Goal:** encode upstream constraint removal  
**Actions:**
- add dependency-aware task ordering ✅
- include cascade impact in projection and execution feedback

### Phase v4 - Automation Surface
**Goal:** convert planning into execution  
**Actions:**
- add automation integration layer (social, CRM, payments) — partial

---

## 10. Next Steps

### Step 1 - Deepen cascade impact in projection
**Files:** `services/eta_service.py`, `db/models/masterplan.py`, `services/infinity_service.py`  
**Outcome:** completing a blocking task shifts projection with richer critical-path and compression impact than flat task velocity.

### Step 2 - Expose MasterPlan execution metrics directly
**Files:** `routes/masterplan_router.py`, `routes/analytics_router.py`, `client/src/components/MasterPlanDashboard.jsx`  
**Outcome:** the MasterPlan surface shows execution metrics tied to the active plan rather than relying on generic dashboard views.

### Step 3 - Return MasterPlan reprojection from task completion flows
**Files:** `services/task_services.py`, `services/flow_definitions.py`, `routes/task_router.py`  
**Outcome:** task completion visibly updates the MasterPlan execution surface with refreshed projection data.

### Step 4 - Extend external automation connectors
**Files:** `routes/automation_router.py`, related automation services/models  
**Outcome:** the existing MasterPlan-linked automation layer reaches external social/CRM/payment surfaces rather than remaining mostly internal.

---

## 11. Technical Debt

Masterplan layer debt is tracked in:
- `docs/roadmap/TECH_DEBT.md`

---

## 12. Governance Notes

- This document is the canonical reference for the Masterplan SaaS layer.
- Any changes must also update:
  - `docs/architecture/SYSTEM_SPEC.md`
  - `docs/interfaces/API_CONTRACTS.md`
  - `docs/roadmap/EVOLUTION_PLAN.md`

---

## 13. Summary (Operational Truth)

The Masterplan SaaS layer currently implements **planning, locking, activation,
anchor setting, dependency-aware task execution, and internal automation
binding**, but still does not implement **full cascade-based compression
modeling** or complete external automation coverage. The system's core promise
(execution as timeline compression) is now represented more concretely, but it
is still not operational in full.
