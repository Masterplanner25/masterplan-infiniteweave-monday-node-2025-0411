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
- Agentics conceptual layer audit and completion roadmap are defined in `docs/roadmap/AGENTICS.md` (Phases 1–7).

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
- Strengthen HMAC validation handling with consistent error mapping.
- Links to debt: `docs/roadmap/TECH_DEBT.md` → Section 6 (Security Debt).

Exit criteria (policy-aligned):
- Background tasks are supervised or safely gated without changing core runtime model.
- Health check endpoints reflect actual routes and do not report false degradation from mismatched paths.
- External provider failures are consistently mapped to 5xx with structured error responses (per `docs/governance/ERROR_HANDLING_POLICY.md`).
Sign-off required: Human approval of Phase 2 completion and operational readiness.

## 4. Phase 3 – Observability and Resilience
Focus areas:
- Implement structured logging consistently across services and routes.
- Links to debt: `docs/roadmap/TECH_DEBT.md` → Section 7 (Observability Debt), Section 4 (Error Handling Debt).
- Add basic metrics instrumentation for core endpoints.
- Links to debt: `docs/roadmap/TECH_DEBT.md` → Section 7 (Observability Debt).
- Add failure monitoring hooks aligned with current deployment model.
- Links to debt: `docs/roadmap/TECH_DEBT.md` → Section 7 (Observability Debt).
- Strengthen deployment safeguards (schema drift detection, health verification before exposure).
- Links to debt: `docs/roadmap/TECH_DEBT.md` → Section 2 (Schema / Migration Debt).

Exit criteria (policy-aligned):
- Structured logging is used across core routes and services.
- Basic metrics exist for core endpoints or request outcomes.
- Deployment checks block startup on schema drift (aligned with `docs/governance/INVARIANTS.md`).
Sign-off required: Human approval of Phase 3 completion and observability readiness.

## 5. Phase 4 – Scalability Readiness
Focus areas:
- Background task isolation to reduce duplicate work in multi-instance deployments.
- Links to debt: `docs/roadmap/TECH_DEBT.md` → Section 5 (Concurrency Debt).
- Horizontal deployment considerations (state isolation, background work gating).
- Links to debt: `docs/roadmap/TECH_DEBT.md` → Sections 1 (Structural Debt), 5 (Concurrency Debt).
- Gateway persistence improvements (remove in-memory-only state).
- Links to debt: `docs/roadmap/TECH_DEBT.md` → Section 1 (Structural Debt).
- Concurrency improvements within current framework constraints.
- Links to debt: `docs/roadmap/TECH_DEBT.md` → Section 5 (Concurrency Debt).

Exit criteria (policy-aligned):
- Background task execution is isolated to avoid duplicate work in multi-instance deployments.
- Gateway no longer relies on in-memory-only state for critical flows.
- Horizontal deployment does not violate invariants or session isolation (per `docs/governance/INVARIANTS.md`).
Sign-off required: Human approval of Phase 4 completion and scalability readiness.

## 6. Change Governance Rules
- No evolution phase may violate `docs/governance/INVARIANTS.md`.
- No schema change without an Alembic migration.
- No external integration without a mocking strategy and test coverage.
- Major structural changes require proposal-first approval per `docs/governance/AGENT_WORKING_RULES.md`.

## 7. Deferred Considerations
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
