# Autonomous Reasoning Module (ARM) — Canonical Definition & Evolution Plan

---

## 1. System Definition (Canonical)

The Autonomous Reasoning Module (ARM) is A.I.N.D.Y.'s internal reasoning engine for
code analysis and code generation. It is an API-exposed subsystem that:

- validates inputs (security + size)
- executes structured analysis or generation via LLM
- persists full audit records
- feeds Memory Bridge with outcomes
- produces Infinity Algorithm performance metrics

ARM is not a memory system. It is a reasoning + audit engine with metrics feedback.

---

## 2. Core Lifecycle (Canonical Pipeline)

```
Request → Validate → Analyze/Generate → Persist → Metrics → Memory Feedback
```

---

## 3. Core Components

### 3.1 API Layer

**Implementation:**
- `routes/arm_router.py`

**Current Capabilities:**
- `/arm/analyze`
- `/arm/generate`
- `/arm/logs`
- `/arm/config` (GET/PUT)
- `/arm/metrics`
- `/arm/config/suggest`

---

### 3.2 Reasoning Engine

**Implementation:**
- `modules/deepseek/deepseek_code_analyzer.py`

**Current Capabilities:**
- OpenAI GPT-4o analysis + generation
- structured JSON responses
- retry handling
- audit persistence

---

### 3.3 Governance + Security

**Implementation:**
- `modules/deepseek/security_deepseek.py`
- `modules/deepseek/file_processor_deepseek.py`
- `modules/deepseek/config_manager_deepseek.py`

**Current Capabilities:**
- path/content validation
- chunking for large files
- config management + task priority formula

---

### 3.4 Persistence Layer

**Implementation:**
- `db/models/arm_models.py`

**Current Capabilities:**
- `analysis_results`
- `code_generations`

**Legacy Models (unused by router):**
- `ARMRun`, `ARMLog`, `ARMConfig`

---

### 3.5 Metrics + Self-Tuning Suggestions

**Implementation:**
- `services/arm_metrics_service.py`

**Current Capabilities:**
- Thinking KPI system
- config suggestion engine

---

### 3.6 Memory Bridge Feedback

**Implementation:**
- `modules/deepseek/deepseek_code_analyzer.py`
- `services/memory_capture_engine.py`

**Current Capabilities:**
- recall hooks before analysis
- capture hooks after analysis and generation

---

## 4. Current Implementation (Reality)

**Implemented:**
- analysis/generation API endpoints
- validation + chunking + config
- full DB persistence (analysis_results + code_generations)
- Thinking KPI metrics + suggestions
- Memory Bridge recall + write hooks
- frontend ARM pages (Analyze, Generate, Logs, Config, Metrics, Suggestions)

**Missing or Drifted:**
- DeepSeek engine is not used (OpenAI GPT-4o used under "DeepSeek" namespace)
- DeepSeek SQLite and blockchain ledger are not implemented
- legacy `services/deepseek_arm_service.py` is dead and incompatible
- docs still reference legacy data models and service layer

---

## 5. Doc → Code Parity Table

| Documented Capability | Evidence in Docs | Implementation Reality | Status | Primary Files |
| --- | --- | --- | --- | --- |
| ARM analyze endpoint | ARM docs | Implemented | Implemented | `routes/arm_router.py`, `modules/deepseek/deepseek_code_analyzer.py` |
| ARM generate endpoint | ARM docs | Implemented but payload differs | Partial | `routes/arm_router.py`, `client/src/api.js` |
| ARM logs endpoint | ARM docs | Returns analysis + generation history (not ARMLog) | Partial | `routes/arm_router.py` |
| Config GET/PUT | ARM docs | Implemented (JSON file storage only) | Partial | `modules/deepseek/config_manager_deepseek.py` |
| Security validation | ARM docs | Implemented | Implemented | `modules/deepseek/security_deepseek.py` |
| Task priority formula | ARM docs | Implemented | Implemented | `modules/deepseek/config_manager_deepseek.py` |
| Thinking KPI metrics | ARM docs | Implemented | Implemented | `services/arm_metrics_service.py` |
| Memory Bridge feedback | ARM docs | Implemented | Implemented | `modules/deepseek/deepseek_code_analyzer.py` |
| DeepSeek SQLite ledger | ARM docs | Not present | Missing | N/A |
| Blockchain logging | ARM docs | Not present | Missing | N/A |

---

## 6. Gap → File Mapping

| Gap | Impact | Files to Update |
| --- | --- | --- |
| Docs assume DeepSeek engine | Conceptual mismatch with GPT-4o runtime | `Autonomus Reasoning Module/Autonomous Reasoning Module.md` |
| Legacy service layer referenced | Dead code path + broken assumptions | `services/deepseek_arm_service.py`, `Autonomus Reasoning Module/STEP*.txt` |
| `/arm/generate` payload mismatch | Client drift risk | `client/src/api.js`, `Autonomus Reasoning Module/ARM frontend module.txt` |
| Config persistence not audited | No DB history of config changes | `modules/deepseek/config_manager_deepseek.py`, `db/models/arm_models.py` |
| SQLite + blockchain ledger missing | Audit/traceability drift | `Autonomus Reasoning Module/Autonomous Reasoning Module.md` |

---

## 7. Risk Register

| Risk | Type | Failure Mode | Impact | Likely? |
| --- | --- | --- | --- | --- |
| Legacy service usage | Runtime | `deepseek_arm_service.py` calls incompatible analyzer | Hard error | Medium |
| Generate endpoint mismatch | Contract | Older client payloads fail validation | User-visible failures | Medium |
| DeepSeek naming drift | Product | Stakeholders believe DeepSeek model is active | Expectation mismatch | High |
| Missing ledger | Audit | No unified ledger or hash trail | Governance gap | Medium |
| Metrics skew | Analytics | KPI ignores generation success/failure | Misleading performance signals | Medium |

---

## 8. System Classification

ARM is currently:

> A live reasoning engine with LLM analysis + generation, DB audit trails,
> Memory Bridge hooks, and Infinity Algorithm metrics.

It is not:
- a DeepSeek-backed runtime in practice
- a ledgered reasoning system

---

## 9. Evolution Plan (System Roadmap)

### Phase v1 — Stabilize Contracts
**Goal:** remove payload drift and dead paths  
**Actions:**
- align `/arm/generate` input across docs + frontend + API
- deprecate or remove `services/deepseek_arm_service.py`

### Phase v2 — Audit Consistency
**Goal:** unify audit schema  
**Actions:**
- consolidate ARMRun/ARMLog legacy tables into analysis_results/code_generations
- update docs and architecture references

### Phase v3 — Ledger + Persistence
**Goal:** decide on ledger model  
**Actions:**
- implement or remove DeepSeek SQLite + blockchain ledger references

---

## 10. Technical Debt

See:
- `docs/roadmap/TECH_DEBT.md` → ARM Phase 3 (memory feedback loop and config auto-apply)
- `docs/roadmap/TECH_DEBT.md` → deepseek_arm_service.py dead path

---

## 11. Governance Notes

- This document is the canonical reference for ARM.
- Any changes must also update:
  - `docs/architecture/SYSTEM_SPEC.md`
  - `docs/interfaces/API_CONTRACTS.md`
  - `docs/roadmap/TECH_DEBT.md`

---

## 12. Summary (Operational Truth)

ARM is live and integrated, but its documentation still reflects an earlier
DeepSeek-based design and legacy service layer. The runtime is GPT-4o based,
API-driven, and fully instrumented for metrics and Memory Bridge feedback.
