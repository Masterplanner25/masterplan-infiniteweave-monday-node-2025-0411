# Agent Working Rules

This document defines enforceable collaboration boundaries for AI agents operating in this repository. It is directive and governance-focused.

## 1. Scope of Authority

### Allowed Without Approval
- Documentation updates limited to `/docs` that reflect current implementation.
- Small, localized code changes that fix clear defects without changing public API, schema, or runtime behavior.
- Test additions that validate existing behavior without altering runtime logic.

### Requires Explicit Human Approval
- Any change to API contracts in `AINDY/routes/` or `client/src/api.js`.
- Any change to database schema, including ORM models in `AINDY/db/models/`.
- Any change to `AINDY/config.py` or `AINDY/db/database.py`.
- Any change to Memory Bridge logic (`AINDY/bridge/`, `AINDY/services/memory_persistence.py`, `AINDY/routes/bridge_router.py`).
- Any change to Genesis session or masterplan logic (`AINDY/routes/genesis_router.py`, `AINDY/services/masterplan_factory.py`, `AINDY/db/models/masterplan.py`).
- Any change to background tasks or concurrency behavior (`AINDY/main.py`, `AINDY/services/task_services.py`).

### Prohibited Without Exception
- Removing security checks or permission validation.
- Changing or deleting existing Alembic migration files.
- Introducing new frameworks or replacing core libraries without a written proposal and approval.

## 2. Refactoring Rules

### Refactoring Is Allowed Only If
- The refactor is small and localized, or
- A plan-first proposal has been approved for larger changes.

### Refactoring Must Preserve
- All invariants in `docs/governance/INVARIANTS.md`.
- Public API contracts (FastAPI routes and request/response shapes).
- Migration compatibility for existing database state.

### Refactoring Must Not
- Change the database schema without a new Alembic migration.
- Alter cross-module boundaries (e.g., move responsibilities across `routes/`, `services/`, `db/`).
- Modify the runtime concurrency model (threads, async behavior, background loops).

### Large Refactors
- Require a proposal-first plan and explicit approval before any implementation.

## 3. Sensitive Files and Directories

The following are high-sensitivity areas and require explanation of impact and explicit confirmation before any modification:
- `AINDY/db/models/`
- `AINDY/alembic/`
- `AINDY/config.py`
- `AINDY/db/database.py`
- Memory Bridge logic: `AINDY/bridge/`, `AINDY/services/memory_persistence.py`, `AINDY/routes/bridge_router.py`
- Genesis session logic: `AINDY/routes/genesis_router.py`, `AINDY/services/masterplan_factory.py`, `AINDY/db/models/masterplan.py`

## 4. Database and Migration Safety Rules
- Never edit existing Alembic migration files after they have been applied.
- Schema changes must include:
- ORM model update.
- New Alembic revision.
- Documentation update in `docs/architecture/DATA_MODEL_MAP.md`.
- Never remove constraints without explicit approval.

## 5. Concurrency and Session Rules
- Never share SQLAlchemy sessions across threads or requests.
- Never introduce global mutable state.
- Do not modify background loop behavior without approval.

## 6. Testing Requirements Before Merge
- New business logic requires tests.
- Changes that affect invariants require test coverage.
- Schema changes require migration validation instructions.
- Do not remove existing tests without approval.

## 7. Documentation Discipline
- Any architectural change must update:
- `docs/architecture/SYSTEM_SPEC.md` (if structural).
- `docs/governance/INVARIANTS.md` (if enforcement changes).
- `docs/architecture/DATA_MODEL_MAP.md` (if schema changes).
- Documentation must reflect actual implementation, not intended behavior.
- Update the `Last updated` date in `docs/GOVERNANCE_INDEX.md` whenever any file under `docs/` changes.

## 8. Proposal-First Rule

For any of the following, a proposal must be written and approved before implementation:
- Large refactors.
- Schema redesign.
- Runtime behavior changes.
- Cross-layer boundary changes.

The proposal must include:
- A structured change plan.
- Impact analysis on invariants in `docs/governance/INVARIANTS.md`.
- Migration and API contract implications.

## 9. Non-Goals

AI agents must not:
- Optimize prematurely.
- Replace libraries without clear justification and approval.
- Introduce new frameworks.
- Rewrite working subsystems.
