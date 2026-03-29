# Evolution Plan

This plan defines controlled evolution aligned with current architecture and governance rules. It is phased, non-speculative, and derived from existing technical debt.

## 1. Guiding Principles
- Preserve all invariants in `docs/governance/INVARIANTS.md`.
- Preserve the PostgreSQL requirement (`DATABASE_URL` must be PostgreSQL).
- Preserve SQLAlchemy session isolation per request.
- Avoid architectural rewrites.
- Prioritize hardening and consistency before scaling.
- Memory Bridge evolution is defined in `docs/architecture/MEMORY_BRIDGE.md`.
- Infinity Algorithm Support System evolution is defined in `docs/roadmap/INFINITY_ALGORITHM_SUPPORT_SYSTEM.md`.
- RippleTrace evolution is defined in `docs/roadmap/RIPPLETRACE.md`.
- Search System evolution is defined in `docs/roadmap/SEARCH_SYSTEM.md`.
- Freelancing System evolution is defined in `docs/roadmap/FREELANCING_SYSTEM.md`.
- Social Layer evolution is defined in `docs/roadmap/SOCIAL_LAYER.md`.
- ARM evolution is defined in `docs/roadmap/AUTONOMOUS_REASONING_MODULE.md`.
- Masterplan SaaS evolution is defined in `docs/roadmap/MASTERPLAN_SAAS.md`.
- Implementation docs utility audit is defined in `docs/roadmap/IMPLEMENTATION_DOCS_AUDIT.md`.
- Agentics reality, corrected A.I.N.D.Y. + Nodus architecture, and completion roadmap are defined in `docs/roadmap/AGENTICS.md`.
- Treat the current `PersistentFlowRunner` execution path as transitional infrastructure.
- Treat real Nodus integration as a core infrastructure objective, not a completed milestone and not a deferred nice-to-have.

## Phase Entry Conditions
- A phase may only begin after the prior phase’s exit criteria are met.
- Any unresolved invariant violations block advancement.
- Schema changes require migrations and updated documentation before phase advancement.
- Governance enforcement follows `docs/governance/AGENT_WORKING_RULES.md` for proposal-first requirements and approval gates.

## 2. Phase 1 – Stabilization
Focus areas:
- Improve test coverage for critical routes and services (`docs/engineering/TESTING_STRATEGY.md`).
- Links to debt: `docs/roadmap/TECH_DEBT.md` → Sections 3 (Testing Debt), 4 (Error Handling Debt).
- Normalize error handling per `docs/governance/ERROR_HANDLING_POLICY.md`.
- Links to debt: `docs/roadmap/TECH_DEBT.md` → Section 4 (Error Handling Debt).
- Enforce migration discipline and schema validation (`docs/governance/INVARIANTS.md` checklist).
- Links to debt: `docs/roadmap/TECH_DEBT.md` → Section 2 (Schema / Migration Debt).
- Improve logging consistency (reduce `print(...)` usage where possible).
- Links to debt: `docs/roadmap/TECH_DEBT.md` → Section 4 (Error Handling Debt), Section 7 (Observability Debt).
- Add structured JSON error responses across routes (policy compliance).
- Links to debt: `docs/roadmap/TECH_DEBT.md` → Section 4 (Error Handling Debt).

Exit criteria (policy-aligned):
- `docs/governance/ERROR_HANDLING_POLICY.md` is enforced for primary routes.
- Invariants in `docs/governance/INVARIANTS.md` have test coverage per `docs/engineering/TESTING_STRATEGY.md`.
- Migration validation steps are documented and run before release.
Sign-off required: Human approval of Phase 1 completion and policy compliance.

## 3. Phase 2 – Operational Hardening
Focus areas:
- Introduce a supervised background task mechanism (without changing core runtime model).
- Links to debt: `docs/roadmap/TECH_DEBT.md` → Sections 1 (Structural Debt), 5 (Concurrency Debt).
- Improve health check consistency; align health endpoints with real routes.
- Links to debt: `docs/roadmap/TECH_DEBT.md` → Section 1 (Structural Debt), Section 8 (Known Deployment Risks in `docs/engineering/DEPLOYMENT_MODEL.md`).
- Improve external model failure handling with retry/fallback policy enforcement (without changing provider interfaces).
- Links to debt: `docs/roadmap/TECH_DEBT.md` → Section 4 (Error Handling Debt).
- Retire legacy HMAC handling; enforce JWT-only bridge writes.
- Links to debt: `docs/roadmap/TECH_DEBT.md` → Section 6 (Security Debt).

Exit criteria (policy-aligned):
- Background tasks are supervised or safely gated without changing core runtime model.
- Health check endpoints reflect actual routes and do not report false degradation from mismatched paths.
- External provider failures are consistently mapped to 5xx with structured error responses (per `docs/governance/ERROR_HANDLING_POLICY.md`).
Sign-off required: Human approval of Phase 2 completion and operational readiness.

## 4. Phase 3 – Observability and Resilience

**Status:** Complete (2026-03-22)

Focus areas:
- Implement structured logging consistently across services and routes.
- Links to debt: `docs/roadmap/TECH_DEBT.md` → Section 7 (Observability Debt), Section 4 (Error Handling Debt).
- Add basic metrics instrumentation for core endpoints.
- Links to debt: `docs/roadmap/TECH_DEBT.md` → Section 7 (Observability Debt).
- Add failure monitoring hooks aligned with current deployment model.
- Links to debt: `docs/roadmap/TECH_DEBT.md` → Section 7 (Observability Debt).
- Strengthen deployment safeguards (schema drift detection, health verification before exposure).
- Links to debt: `docs/roadmap/TECH_DEBT.md` → Section 2 (Schema / Migration Debt).

**Status:** Complete (2026-03-22)

Exit criteria (policy-aligned):
- Structured logging is used across core routes and services.
- Basic metrics exist for core endpoints or request outcomes.
- Deployment checks block startup on schema drift (aligned with `docs/governance/INVARIANTS.md`).
Sign-off required: Human approval of Phase 3 completion and observability readiness.

## 5. Phase 4 – Scalability Readiness

**Status:** Complete (2026-03-25, Sprint N+9)

Focus areas:
- Background task isolation to reduce duplicate work in multi-instance deployments.
- Links to debt: `docs/roadmap/TECH_DEBT.md` → Section 5 (Concurrency Debt).
- Horizontal deployment considerations (state isolation, background work gating).
- Links to debt: `docs/roadmap/TECH_DEBT.md` → Sections 1 (Structural Debt), 5 (Concurrency Debt).
- Gateway persistence improvements (remove in-memory-only state).
- Links to debt: `docs/roadmap/TECH_DEBT.md` → Section 1 (Structural Debt).
- Concurrency improvements within current framework constraints.
- Links to debt: `docs/roadmap/TECH_DEBT.md` → Section 5 (Concurrency Debt).

Execution checklist:
1. ✅ Background task lease prevents duplicate runners across instances — `start_background_tasks()` returns `bool`; `scheduler_service.start()` only called on lease-holding instance (Sprint N+9).
2. ✅ Gateway state persistence eliminates in-memory-only user state — completed in Phase 6.
3. ✅ Concurrency guards for shared singletons are in place — completed 2026-03-22.
4. ✅ Startup schema drift guard blocks mismatched DB revisions — `tests/test_migrations.py` added Phase 8.
5. ✅ Lease heartbeat job (`background_lease_heartbeat`, 60s) prevents TTL expiry while leader is running (Sprint N+9).
6. ✅ `GET /observability/scheduler/status` exposes `{scheduler_running, is_leader, lease}` for ops visibility (Sprint N+9).

Exit criteria (policy-aligned):
- ✅ Background task execution is isolated to avoid duplicate work in multi-instance deployments.
- ✅ Gateway no longer relies on in-memory-only state for critical flows.
- ✅ Horizontal deployment does not violate invariants or session isolation (per `docs/governance/INVARIANTS.md`).
Sign-off required: Human approval of Phase 4 completion and scalability readiness.

## 6. Phase 5 – Agentics Completion + Nodus Convergence

**Status:** In progress

Focus areas:
- Complete Agentics as an operational subsystem rather than a partial feature set.
- Converge the current internal flow engine and the installed Nodus runtime toward one execution architecture.
- Preserve the existing internal flow engine as the stable transitional path until real Nodus-backed execution is ready.
- Links to debt: `docs/roadmap/TECH_DEBT.md` → §16.6 through §16.10.

Execution checklist:
1. Stabilize the current agent execution path across `agent_runtime`, `nodus_adapter`, `flow_engine`, async execution, replay, and recovery.
2. Define the canonical Nodus integration contract: workflow source ownership, compile/load path, checkpoint model, and event emission contract.
3. Introduce repo-managed Nodus workflow assets or a verified generation pipeline for agent plans.
4. Make Nodus execution traces land in the same observability and audit surfaces as `FlowRun`, `AgentEvent`, and `SystemEvent`.
5. Extend Agentics beyond single-agent runs by defining delegation, scoped sub-runs, and shared/private memory boundaries.
6. Promote the Infinity loop from post-run suggestion logic to a bounded autonomous controller under explicit policy.

Exit criteria (policy-aligned):
- Agentics has one clearly documented primary execution path.
- The relationship between A.I.N.D.Y. orchestration and Nodus execution is implemented, not implied.
- Agent execution, flow execution, and embedded Nodus execution share a normalized observability model.
- Multi-agent and autonomous execution boundaries are policy-enforced and auditable.

## 7. Phase 6 – Ownership Cleanup + Observability Hardening
Focus areas:
- Backfill legacy `user_id` gaps where possible and confirm ownership consistency.
- Normalize MasterPlan versioning to a single canonical field.
- Provide a queryable observability surface for request metrics.
- Align health check pings with active routes.
- Ensure memory metrics persistence has a single write path.

Execution checklist:
1. `Tools/backfill_user_ids.py` added and executed (dry-run; apply when needed).
2. `master_plans.version` removed; `version_label` is canonical.
3. `GET /observability/requests` added for request metrics queries.
4. `/health` pings align with active endpoints.
5. Memory metrics persistence remains in `ExecutionLoop` only.

Exit criteria (policy-aligned):
- No remaining mixed ownership fields or redundant version columns.
- Observability metrics can be queried without log scraping.
- Health checks reflect active endpoints.

## 8. Phase 7 – Data Integrity + Operational Hygiene
Focus areas:
- Normalize ownership columns to UUID with FK enforcement where feasible.
- Remove dead code paths and legacy service stubs.
- Close testing debt that can mask failures (duplicate names, migration drift guards).

Execution checklist:
1. `user_id` normalized to UUID for `research_results`, `freelance_orders`, `client_feedback`, `drop_points`, `pings` with FK constraints.
2. Backfill script executed (dry-run) to confirm no orphaned user_id rows remain.
3. Dead code removed or moved to `legacy/` (e.g., `deepseek_arm_service.py`).
4. Root test duplicates removed and migration drift test added.

Exit criteria (policy-aligned):
- Ownership tables are enforceable at DB level.
- No dead-path service code remains in core modules.
- CI includes a migration drift guard.

## Phase: Autonomous Intelligence

Focus areas:
* Playbook auto-execution relies on the Strategy → Playbook → Content pipeline with scheduling hooks.
* Recommendation → action loop captures system recommendations, executes or queues them, and feeds the results back into the Learning Engine.
* Feedback is captured as learning records and delta analytics so thresholds improve as we observe outcomes.
* Agentics Phase 5 is a prerequisite for any real autonomous intelligence layer; autonomous execution should build on the completed Agentics/Nodus execution contract rather than bypass it.

Execution checklist:
1. Playbook execution API wiring with scheduling/polling triggers is implemented.
2. Recommendation outcomes automatically mark learning records for evaluation (success/failure).
3. Learning thresholds adjust based on recorded outcomes and the new data pipeline from recommendations.

Exit criteria:
* The Learning Engine receives actionable outcomes from recommendation executions.
* Operating playbooks can be triggered autonomously (with optional human approval).
* Documentation for the Autonomous Intelligence layer is added to `docs/roadmap/RIPPLETRACE.md` (Autonomous Execution Layer section).

## Phase: Productization

Focus areas:
* Production-grade auth system with API key support, org-scoped access controls, and admin tooling.
* Multi-user support for dashboards, strategies, learning records, and playbooks with tenant isolation.
* Billing hooks mapped to usage (API calls, playbook executions, Graph UI sessions).
* Hosted deployment model documented with infrastructure, observability, and compliance guidelines.

Execution checklist:
1. Auth + API key management flows exist, documented via interface contracts and route policies.
2. Multi-tenant isolation is enforced at the DB level and documented in `docs/roadmap/MASTERPLAN_SAAS.md`.
3. Billing integration points for usage-based metering are defined and surfaced through `/billing/*` or similar endpoints.
4. Hosted deployment guide covers security, scaling, and operational runbooks.

Exit criteria:
* Organizations have dedicated data views, recommendation queues, and learning thresholds.
* Billing hooks emit usage events or can be connected to a pricing engine.
* Hosted deployment instructions cover prerequisites, secrets, scaling, and monitoring.

## Phase: Advanced Intelligence

Focus areas:
* ML-based prediction refinement (retrainable models, embeddings, or tree-based heuristics supplementing ThreadWeaver).
* Causal inference improvements that incorporate richer momentum, theme/entity embeddings, and counterfactual guardrails.
* Strategy optimization loops that test playbooks, measure impact, and iterate with reinforcement-style scoring.

Execution checklist:
1. Prediction_engine can plug in new scoring models, measure drift, and surface model explainability data to dashboards.
2. Causal engine can ingest embedding-based coherence signals and support scenario simulations.
3. Strategy playbooks are evaluated in experiments with success tracking, scoring models, and feedback into recommendation priorities.

Exit criteria:
* Prediction and causal models have ML-ready hooks (configurable thresholds, retraining markers).
* Strategy optimization pipelines log outcomes and adjust confidence automatically.
* Documentation in `docs/roadmap/RIPPLETRACE.md` and relevant architecture docs references the Advanced Intelligence roadmap.

## 7. Change Governance Rules
- No evolution phase may violate `docs/governance/INVARIANTS.md`.
- No schema change without an Alembic migration.
- No external integration without a mocking strategy and test coverage.
- Major structural changes require proposal-first approval per `docs/governance/AGENT_WORKING_RULES.md`.

## 8. Deferred Considerations
The following are deferred unless explicitly prioritized:
- Distributed job queue.
- Auth layer redesign.
- Multi-tenant architecture.
- Horizontal scaling beyond current single-node assumptions.

## Traceability Matrix
| Phase | Primary Debt Sections |
|------|------------------------|
| Phase 1 – Stabilization | `TECH_DEBT.md` Sections 2, 3, 4, 7 |
| Phase 2 – Operational Hardening | `TECH_DEBT.md` Sections 1, 4, 5, 6 |
| Phase 3 – Observability and Resilience | `TECH_DEBT.md` Sections 2, 4, 7 |
| Phase 4 – Scalability Readiness | `TECH_DEBT.md` Sections 1, 5 |
| Phase 5 – Agentics Completion + Nodus Convergence | `TECH_DEBT.md` §16.6, §16.7, §16.8, §16.9, §16.10 |
| Phase 6 – Ownership Cleanup + Observability Hardening | `TECH_DEBT.md` Sections 1, 2, 7 |
| Phase 7 – Data Integrity + Operational Hygiene | `TECH_DEBT.md` Sections 2, 3 |

## Compliance Checklist (Per Phase)
- Invariants remain intact and tested (`docs/governance/INVARIANTS.md`).
- Error handling policy enforced (`docs/governance/ERROR_HANDLING_POLICY.md`).
- Schema changes include migrations and documentation updates.
- API contract updates reflected in `docs/interfaces/API_CONTRACTS.md`.
- Proposal-first approval applied where required (`docs/governance/AGENT_WORKING_RULES.md`).
- `Last updated` date in `docs/GOVERNANCE_INDEX.md` is refreshed after doc changes.

## Overall Release Sign-Off
- Final release requires explicit human approval after verifying:
- All phase exit criteria have been met.
- All governance documents are updated and consistent.
- No unresolved invariant violations remain.
- Evidence checklist for approval:
- Tests executed per `docs/engineering/TESTING_STRATEGY.md` (record command outputs or summaries).
- Alembic revision matches head (`alembic current` equals `alembic heads`).
- Schema vs. migration checks completed (`docs/governance/INVARIANTS.md` checklist).
- Store release evidence and sign-off notes in `docs/roadmap/release_notes.md` (create if missing).
