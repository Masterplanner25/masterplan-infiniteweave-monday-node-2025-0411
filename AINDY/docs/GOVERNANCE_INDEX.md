# Governance Index
Last updated: 2026-03-22 (Phase 3 error handling consistency across core routes)
Update rule: Change this date whenever any file under `docs/` is modified.

This file is the authoritative registry of documentation scope and authority. It defines hierarchy, change protocols, and agent obligations.

## 1. Documentation Hierarchy

### Level 1 – Structural Authority
- `docs/architecture/SYSTEM_SPEC.md`
- `docs/governance/INVARIANTS.md`

### Level 2 – Operational Authority
- `docs/architecture/RUNTIME_BEHAVIOR.md`
- `docs/architecture/DATA_MODEL_MAP.md`
- `docs/architecture/MEMORY_BRIDGE.md`
- `docs/governance/ERROR_HANDLING_POLICY.md`
- `docs/engineering/MIGRATION_POLICY.md`
- `docs/engineering/DEPLOYMENT_MODEL.md`

### Level 3 – Interface Authority
- `docs/interfaces/API_CONTRACTS.md`
- `docs/interfaces/GATEWAY_CONTRACT.md`
- `docs/interfaces/MEMORY_BRIDGE_CONTRACT.md`

### Level 4 – Governance & Collaboration
- `docs/governance/AGENT_WORKING_RULES.md`
- `docs/engineering/TESTING_STRATEGY.md`

### Level 5 – Evolution & Risk Tracking
- `docs/roadmap/TECH_DEBT.md`
- `docs/roadmap/EVOLUTION_PLAN.md`
- `docs/roadmap/INFINITY_ALGORITHM_SUPPORT_SYSTEM.md`
- `docs/roadmap/RIPPLETRACE.md`
- `docs/roadmap/SEARCH_SYSTEM.md`
- `docs/roadmap/FREELANCING_SYSTEM.md`
- `docs/roadmap/SOCIAL_LAYER.md`
- `docs/roadmap/AUTONOMOUS_REASONING_MODULE.md`
- `docs/roadmap/MASTERPLAN_SAAS.md`
- `docs/roadmap/IMPLEMENTATION_DOCS_AUDIT.md`
- `docs/roadmap/AGENTICS.md`

## 2. Authority Rules
- `docs/architecture/SYSTEM_SPEC.md` defines architecture.
- `docs/governance/INVARIANTS.md` defines non-negotiable constraints.
- No lower-level document may contradict higher-level documents.
- Conflict resolution order:
- INVARIANTS override all.
- SYSTEM_SPEC overrides implementation detail.
- API_CONTRACTS override route refactors.

## 3. Change Protocol
Any structural change must:
- Update `docs/architecture/SYSTEM_SPEC.md` if architecture changes.
- Update `docs/architecture/MEMORY_BRIDGE.md` for Memory Bridge architecture changes.
- Update `docs/governance/INVARIANTS.md` if enforcement changes.
- Update `docs/architecture/DATA_MODEL_MAP.md` if schema changes.
- Update `docs/interfaces/API_CONTRACTS.md` if route behavior changes.
- Update `docs/engineering/MIGRATION_POLICY.md` if schema discipline changes.
- Update `docs/engineering/TESTING_STRATEGY.md` if validation discipline changes.

## 4. Agent Interaction Protocol
AI agents must:
- Treat `docs/governance/INVARIANTS.md` as hard constraints.
- Treat `docs/architecture/SYSTEM_SPEC.md` as architectural baseline.
- Consult `docs/architecture/DATA_MODEL_MAP.md` before modifying schema.
- Consult `docs/governance/ERROR_HANDLING_POLICY.md` before modifying error paths.
- Propose-first before altering migration or concurrency model.

## 5. Governance Stability Principle
- Documentation must reflect implementation reality.
- Documentation must be updated before or alongside code changes.
- Documentation drift is considered technical debt.

## 6. Entry Point
This file is the first document AI agents must read before performing architectural modifications.

## 7. Docs Changes Checklist
- Update `Last updated` in this file for any `docs/` change.
- Ensure modified docs do not contradict higher-level authority.
- Update related documents per the Change Protocol.

## 8. Doc Ownership
- Governance documents require explicit human sign-off by the project owner or designated maintainer.
- Designated maintainer: Shawn Knight.








