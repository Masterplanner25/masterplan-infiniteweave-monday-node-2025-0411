# Masterplan SaaS — Canonical Definition & Evolution Plan

---

## 1. System Definition (Canonical)

The Masterplan SaaS layer is A.I.N.D.Y.'s execution-strategy surface. It is not a
general automation SaaS. It is a **Masterplan trajectory engine** that:

- captures a strategic plan (Genesis → MasterPlan)
- enforces lifecycle (draft → lock → activate)
- measures execution as time-compression against a declared target state
- prioritizes dependency resolution to compress downstream timelines

---

## 2. Core Lifecycle (Canonical Pipeline)

```
Genesis → MasterPlan → Lock → Activate → Execute → Measure → Reproject
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
- Genesis session lifecycle (create → message → synthesize → audit → lock)
- MasterPlan creation and activation
- Task CRUD + analytics ingestion
- Basic dashboards

**Missing or Drifted vs Masterplan Module docs:**
- no masterplan anchor (goal value or target completion date)
- no ETA projection or time compression feedback
- no dependency cascade model
- no explicit execution ordering guidance
- no automation layer (social/CRM/payments)

---

## 5. Doc → Code Parity Table

| Documented Capability | Evidence in Docs | Implementation Reality | Status | Primary Files |
| --- | --- | --- | --- | --- |
| Genesis → MasterPlan lifecycle | Masterplan Genesis Module | Implemented | Implemented | `routes/genesis_router.py`, `services/masterplan_factory.py` |
| MasterPlan activation | Genesis Module | Implemented | Implemented | `routes/masterplan_router.py`, `client/src/components/MasterPlanDashboard.jsx` |
| Masterplan anchor / target state | Masterplan Plans doc | Not implemented | Missing | N/A |
| ETA projection / timeline compression | Masterplan Plans doc | Not implemented | Missing | N/A |
| Dependency cascade model | Masterplan Plans doc | Not implemented | Missing | N/A |
| Execution automation layer | Masterplan SaaS docs | Not implemented | Missing | N/A |
| Execution analytics dashboard | SaaS docs | Partial (basic dashboard only) | Partial | `routes/dashboard_router.py`, `client/src/components/Dashboard.jsx` |

---

## 6. Gap → File Mapping

| Gap | Impact | Files to Update |
| --- | --- | --- |
| No masterplan anchor | TWR has no reference frame | `db/models/masterplan.py`, `routes/genesis_router.py`, `services/masterplan_factory.py` |
| No ETA projection | Masterplan cannot show trajectory compression | `services/calculation_services.py`, `routes/main_router.py` |
| No dependency cascade model | Execution order not encoded | `schemas/task_schemas.py`, `services/task_services.py` |
| No automation layer | SaaS execution claims unfulfilled | N/A |

---

## 7. Risk Register

| Risk | Type | Failure Mode | Impact | Likely? |
| --- | --- | --- | --- | --- |
| Masterplan drift | Product | Plans exist without trajectory signal | Core value missing | High |
| Docs vs runtime mismatch | Product | SaaS claims automation; system is planning + tracking | Expectation gap | High |
| No anchor state | Technical | TWR remains abstract | Low user clarity | High |
| No dependency weighting | Technical | Execution order guidance missing | Weak compression model | Medium |
| No automation | Business | Execution SaaS promise not met | Revenue risk | High |

---

## 8. System Classification

The Masterplan SaaS layer is currently:

> A strategic planning + activation system with task tracking, but without
> trajectory compression modeling or automation.

---

## 9. Evolution Plan (System Roadmap)

### Phase v1 — Anchor the MasterPlan
**Goal:** add a declared target state  
**Actions:**
- add masterplan anchor field (goal value or target date)
- update lock flow to persist anchor

### Phase v2 — Timeline Compression Output
**Goal:** make TWR actionable  
**Actions:**
- compute ETA shift per task batch
- return updated projection from execution endpoints

### Phase v3 — Dependency Awareness
**Goal:** encode upstream constraint removal  
**Actions:**
- add dependency weighting in tasks
- include cascade impact in TWR breakdown

### Phase v4 — Automation Surface
**Goal:** convert planning into execution  
**Actions:**
- add automation integration layer (social, CRM, payments)

---

## 10. Technical Debt

Masterplan layer debt is tracked in:
- `docs/roadmap/TECH_DEBT.md`

---

## 11. Governance Notes

- This document is the canonical reference for the Masterplan SaaS layer.
- Any changes must also update:
  - `docs/architecture/SYSTEM_SPEC.md`
  - `docs/interfaces/API_CONTRACTS.md`
  - `docs/roadmap/EVOLUTION_PLAN.md`

---

## 12. Summary (Operational Truth)

The Masterplan SaaS layer currently implements **planning and activation** but
does not implement **time-compression projection** or **dependency-aware execution**.
The system's core promise (execution as timeline compression) is documented,
but not yet operational.
