# Release Notes

---

## Release: Genesis Blocks 4-6 — Strategic Integrity Audit + Lock Pipeline

- **Version/Tag:** `feature/cpp-semantic-engine` → `main` (commit `3739b01`)
- **Date:** 2026-03-17
- **Owner:** Shawn Knight
- **Designated maintainer:** Shawn Knight

### Summary

Completed the Genesis/MasterPlan feature with three blocks:

- **Block 4 — Strategic Integrity Audit:** GPT-4o audit function (`validate_draft_integrity`), `POST /genesis/audit` endpoint, audit panel in `GenesisDraftPreview.jsx` with severity-color-coded findings.
- **Block 5 — Lock Pipeline Hardening:** `synthesis_ready` gate in `create_masterplan_from_genesis()`, draft loaded from `session.draft_json`, atomic rollback on DB failure, new `POST /masterplans/lock` endpoint, `GET /masterplans/` returns `{"plans": [...]}`, `synthesis_notes` added to synthesis prompt.
- **Block 6 — Cleanup:** Duplicate `POST /create_masterplan` (MasterPlanCreate variant) removed from `main_router.py`; `tests/test_genesis_flow.py` added with 55 tests.

### Evidence Checklist

- Tests executed: `python -m pytest tests/ -q` → **301 passed, 0 failed**
- `alembic current`: No schema changes in this release (all changes are application-layer only; no new columns added)
- `alembic heads`: No migration changes
- Schema vs. migration verification: N/A (no migrations added)

### Invariants Verified

- **Invariant 8** (Single Active MasterPlan): enforcement location updated — now also in `masterplan_router.py: activate_masterplan`
- **Invariant 9** (Genesis Session Locking): still enforced; factory now also checks `synthesis_ready` before locking
- **Invariant 23** (Rate Limiting): `POST /genesis/audit` added at 5/min
- **Invariant 24** (synthesis_ready gate): NEW — enforced in `create_masterplan_from_genesis()`
- **Invariant 25** (Audit requires draft): NEW — enforced in `audit_genesis_draft()`
- **Invariant 26** (Atomic factory rollback): NEW — enforced in `create_masterplan_from_genesis()`

### API Contract Updates

New endpoints documented in `docs/interfaces/API_CONTRACTS.md`:
- `POST /genesis/audit` — 5/min rate limit, JWT required, 422 if no draft
- `POST /masterplans/lock` — JWT required, ValueError → 422, posture_description in response
- `GET /masterplans/` — response shape changed to `{"plans": [...]}`

### Deployment Notes

- **Environment:** No new environment variables required
- **Migration steps:** None — no schema changes
- **Frontend:** `MasterPlanDashboard.jsx` updated to consume `data.plans || []`; `GenesisDraftPreview.jsx` updated to accept `sessionId` prop for audit
- **Known issues:** `synthesis_notes` field in synthesis drafts only appears if draft was generated after this release; older drafts may not have the field

### Sign-Off

- **Approved by:** Shawn Knight
- **Maintainer sign-off (Shawn Knight):** Pending
- **Approval date:** 2026-03-17
- **Verification performed by:** Automated pytest suite
- **Verification date:** 2026-03-17
- **Verification scope:** Full test suite (301 tests)

### Verification Artifacts

- Test run: `python -m pytest tests/ -q` — 301 passed, 11 warnings in ~40s
- Commit: `3739b01` on `main`

---

## Release: Genesis Blocks 1-3 — DB + Auth + Real Synthesis

- **Version/Tag:** `feature/cpp-semantic-engine` → `main` (commit `cce0582`)
- **Date:** 2026-03-17
- **Owner:** Shawn Knight

### Summary

Delivered the Genesis/MasterPlan module (Blocks 1-3): user-scoped DB columns, real GPT-4o synthesis, posture detection, masterplan_router CRUD, synthesis_ready flag, `GenesisDraftPreview.jsx`, `MasterPlanDashboard.jsx`.

### Evidence Checklist

- Tests executed: `python -m pytest tests/ -q` → **246 passed, 0 failed**
- Alembic migration: `a1b2c3d4e5f6` — added `synthesis_ready`, `draft_json`, `locked_at`, `user_id_str` to `genesis_sessions`; added `user_id`, `status` to `master_plans`

---

## Release: ARM Phases 1+2 — Autonomous Reasoning Module

- **Version/Tag:** `feature/cpp-semantic-engine` (commit `f1cd3b5`)
- **Date:** 2026-03-17
- **Owner:** Shawn Knight

### Summary

ARM Phase 1: GPT-4o code analysis/generation engine, SecurityValidator, ConfigManager, FileProcessor, 5 API endpoints. ARM Phase 2: Thinking KPI System, self-tuning config suggestions, `/arm/metrics`, `/arm/config/suggest` endpoints.

### Evidence Checklist

- Tests executed: `python -m pytest tests/test_arm.py -q` → **62 passed, 0 failed**

---

## Release Template

Use this template for future releases:

```
## Release: <Name>

- **Version/Tag:**
- **Date:**
- **Owner:**
- **Designated maintainer:** Shawn Knight

### Summary
- High-level summary of changes:

### Evidence Checklist
- Tests executed (commands and results):
- `alembic current`:
- `alembic heads`:
- Schema vs. migration verification completed:

### Invariants Verification
- List invariants validated (reference `docs/governance/INVARIANTS.md`):

### API Contract Updates
- Any changes to `docs/interfaces/API_CONTRACTS.md`:

### Deployment Notes
- Environment:
- Migration steps performed:
- Known issues:

### Sign-Off
- Approved by:
- Maintainer sign-off (Shawn Knight):
- Approval date:
- Notes:
- Verification performed by:
- Verification date:
- Verification scope:

### Verification Artifacts
- Logs/screenshots saved at:
```
