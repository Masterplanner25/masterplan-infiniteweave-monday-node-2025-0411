# Technical Debt Register

**Last triaged:** 2026-04-25  
**Total items:** 34  
**Production-blocking:** 3 (0 Critical, 1 High, 2 Medium)  
**Deferred:** 21  
**Resolved this triage:** 10

This register replaces the prior audit-history format with one canonical entry per distinct debt item. Repeated historical references from earlier sprint notes were collapsed into the single item they described so the list is actionable again.

---

## Production-Blocking

### Critical
Items in this section MUST be resolved before production traffic.

No currently verified critical item remains from the prior register.

### High
Items in this section should be resolved before sustained production load.

#### Genesis Session Locking Is Only Enforced In Application Logic
**Area:** runtime  
**Severity:** High  
**Effort:** M  
**Description:** `create_masterplan_from_genesis()` prevents double-locking by reading `GenesisSessionDB.status` in application code, but the schema does not enforce a database-level uniqueness or lock invariant for the lock/plan creation transition.  
**Risk:** Concurrent lock requests can create duplicate or inconsistent masterplan state from the same genesis session. That is a correctness bug in a primary planning workflow.  
**File(s):** `apps/masterplan/services/masterplan_factory.py`, `apps/masterplan/masterplan.py`  
**Resolution path:** Move the session-lock/masterplan-creation invariant into the database transaction boundary with an explicit constraint or row-locking pattern.

### Medium
Items in this section should be resolved in the first production sprint.

#### Multi-Instance Cache Correctness Still Depends On Explicit Redis Configuration
**Area:** infrastructure  
**Severity:** Medium  
**Effort:** S  
**Description:** The platform can run with an in-memory cache backend, and correctness across instances depends on operators explicitly setting Redis-backed cache configuration.  
**Risk:** In a horizontally scaled deployment, instances can diverge on cached state and readiness assumptions even though the application appears healthy.  
**File(s):** `AINDY/config.py`, `AINDY/main.py`, `AINDY/routes/health_router.py`  
**Resolution path:** Make the required deployment mode explicit and fail fast when a multi-instance deployment is attempted without Redis.

#### Relational Integrity Is Still Uneven Across Core Models
**Area:** infrastructure  
**Severity:** Medium  
**Effort:** L  
**Description:** The prior debt note about missing foreign keys was overstated in places, but the broader concern is still real: some lifecycle and cascade behavior still depends on application code rather than uniformly declared relational constraints.  
**Risk:** Deletes, ownership changes, and partial writes can leave orphaned rows or inconsistent graph state that the database does not fully prevent.  
**File(s):** `AINDY/db/models/`, `apps/masterplan/masterplan.py`, `AINDY/db/models/flow_run.py`  
**Resolution path:** Audit the remaining high-value ownership and lifecycle relationships and add the missing database constraints/cascade rules where runtime invariants currently rely on service code.

---

## Deferred

Items in this section are acceptable for a production deployment. They should be revisited before the system reaches significant scale or before significant new features are added to the affected area.

| Item | Area | Effort | Description | When to Revisit |
|------|------|--------|-------------|-----------------|
| Search orchestration is not fully unified | apps | M | `apps/search/services/search_service.py` is now the durable shared layer, but LeadGen full-generation persistence, SEO meta generation, and richer provider-backed ranking are still split. | Before expanding search-heavy user workflows or adding new search providers |
| Freelance commercial workflow remains incomplete | apps | M | The old note is narrower now: payments, refunds, webhooks, and idempotency exist, but broader fulfillment and subscription automation still is not end-to-end. | Before exposing the freelance app as a primary revenue path |
| RippleTrace productization is still incomplete | apps | L | Execution-causality, graph edges, and UI exist, but deeper insight generation, scenario coverage, and operational hardening are still incomplete. | Before using RippleTrace as an incident-response or audit primary surface |
| Masterplan dependency cascade and execution automation remain incomplete | apps | L | Anchor/ETA debt is closed, but dependency cascade modeling and execution automation on top of planning/activation are still unfinished. | Before treating Masterplan as an autonomous planner |
| Test coverage remains uneven outside the recently hardened paths | runtime | L | The older "minimal coverage" wording is stale, but broad scenario coverage is still uneven outside the currently verified execution, memory, and health flows. | Before major refactors in unverified route or runtime surfaces |
| Logging standardization is incomplete | infrastructure | S | Core routes mostly use `logger`, but standardized structured logging is not universal and the old DB-path claim is stale. | Next time affected bootstrap/runtime files are touched |
| Main-process execution is still in-process and not externally supervised | infrastructure | L | Lifespan shutdown is now explicit, but the main web process still executes meaningful work in-process rather than through a separately supervised worker topology. | Before scaling sustained background or long-running workloads |
| Centralized tracing and log aggregation are still absent | infrastructure | M | Local observability improved, but there is still no system-wide OpenTelemetry or external log aggregation pipeline. | Before multi-instance or multi-environment operations |
| ARM low-risk config suggestions still require manual apply | apps | S | Suggestion generation exists, but `auto_apply_safe` remains advisory rather than automatically applied. | Before positioning ARM as a self-tuning service |
| Legacy `VALID_NODE_TYPES` compatibility cleanup is still pending | runtime | S | Existing legacy node types are safe unless updated, but the one-time normalization migration still has not been done. | Before bulk-updating old memory rows or tightening validators further |
| Native memory scorer hardening is incomplete | runtime | M | The hot path uses the native bridge with Python fallback, but release packaging, release benchmarks, and traversal-side acceleration remain unfinished. | Before relying on native scoring in production performance targets |
| Automatic behavioral-feedback scenario coverage is incomplete | runtime | M | Dedicated coverage exists for one failure-to-Infinity path, but retries, latency spikes, abandonment, and repeated-failure signals still lack end-to-end proof. | Before using behavioral feedback for autonomous optimization |
| Agent/runtime orchestration still spans multiple semantic layers | runtime | L | Canonical Nodus execution exists, but flow orchestration, async-job lifecycle, and runtime execution still do not read as one end-to-end model. | Before major agent-runtime or VM-surface expansion |
| Infinity loop autonomy is still shallow | apps | M | Infinity is now memory-weighted and feedback-aware, but it does not yet learn thresholds/weights deeply or act as a bounded autonomous controller. | Before enabling autonomous optimization decisions |
| Multi-agent runtime delegation remains absent | runtime | XL | Registry, coordinator, and message-bus primitives exist, but there is no real delegation model, parent/child run structure, or conflict-handling runtime. | Before shipping collaborative agent workflows |
| Pattern detection across memory traces is not implemented | runtime | M | The memory system still lacks recurring motif detection across time windows. | Before depending on long-horizon memory analytics |
| Identity inference remains rules-only | apps | M | Identity observation exists, but probabilistic or model-driven inference is still not implemented. | Before expanding identity-driven personalization |
| SYLVA remains an inactive reserved agent namespace | apps | S | Reserved system-agent scaffolding exists, but the agent is still not implemented. | When the reserved agent is activated or removed |
| Embedding-based deduplication is still not implemented | runtime | M | `MemoryCaptureEngine._is_duplicate()` still uses exact-content style checks rather than semantic deduplication. | Before memory volume grows enough for duplicate pressure to matter materially |
| Agent trust-level and access-policy tiers are still future work | runtime | M | Scoped capability enforcement exists, but richer trust tiers and policy strata are still not implemented. | Before broadening unattended agent execution |
| Compatibility aliases remain for `goal`, `objective`, `task_name`, and legacy operation labels | runtime | M | The system vocabulary was normalized, but compatibility aliases remain in storage and API payloads to protect old clients. | After an explicit API and DB migration window is scheduled |

---

## Resolved (This Triage)

Items verified as no longer present in the codebase.

| Item | Area | How Resolved |
|------|------|-------------|
| Startup invariant for `STUCK_RUN_THRESHOLD_MINUTES` vs `FLOW_WAIT_TIMEOUT_MINUTES` | runtime | Resolved by Prompt 1: `AINDY/config.py` now enforces the invariant with a settings validator and startup fails on invalid config. |
| Memory embeddings in the ingest hot path | runtime | Resolved by Prompt 2: memory writes persist immediately and embeddings are handled asynchronously in the background. |
| Bare internal import-path violations across app boundaries | runtime | Resolved by Prompt 3: canonical `AINDY.*` imports are in place and CI now guards the pattern. |
| ARM config propagation was process-local | apps | Resolved in current code: ARM config is DB-backed, re-read on use, and emits update events. |
| Mongo startup was late-bound and could affect platform startup semantics | infrastructure | Resolved by Prompt 12: Mongo now has explicit health/timeout handling and social degrades without taking the PostgreSQL-backed platform down. |
| Readiness gating was absent | infrastructure | Resolved in current code: readiness and liveness reporting now exist in the platform health service and worker health server. |
| Async AI worker default concurrency was too small for the intended workload | runtime | Resolved in current code: `AINDY_ASYNC_JOB_WORKERS` is configurable and no longer defaults to the undersized earlier value. |
| Mixed `cpython-311` / `cpython-314` pycache concern in ARM deepseek services | infrastructure | Concern closed during verification: the cited mixed-bytecode state is no longer present in `apps/arm/services/deepseek/__pycache__/`. |
| Observability, execution console, and RippleTrace frontend visibility gaps | client | Resolved in current code: `ObservabilityDashboard.jsx`, `FlowEngineConsole.jsx`, and `RippleTraceViewer.jsx` are all present and routed. |
| The debt register itself had drifted away from live system state | docs | Resolved by this triage: stale open items were verified, reclassified, and the document was rewritten into a canonical register. |

---

## Adding New Items
New debt items should be added during code review or post-incident. Required fields:
- Title (concise, searchable)
- Area
- Description (what is the problem, not what would be nice)
- Risk (what breaks if this is not fixed)
- File(s) (where the debt lives)

Classify as production-blocking only if it meets the criteria in the Classification section above. When in doubt, classify as deferred.

---

## Discovered During Triage - Needs Classification

These were observed while verifying the old register, but they were not in the original debt list and were not classified in this cycle:

- Raw `print(...)` calls still exist outside the database/bootstrap paths cited by the old note, including `apps/authorship/services/authorship.py`, `AINDY/runtime/nodus_worker.py`, and `AINDY/cli.py`.
- The old Mongo note was directionally stale: the current platform treats MongoDB failure as a degraded social-app dependency rather than a hard startup dependency for the whole platform.
