## Release: Phase 7 — Contract + Test Coverage Hardening

- **Version/Tag:** `main` (commit `1258c4e`)
- **Date:** 2026-03-22
- **Owner:** Shawn Knight
- **Designated maintainer:** Shawn Knight

### Summary

Phase 7 contract and test coverage hardening:
- **API contract cleanup:** removed stale duplicate `/create_masterplan` gap note.
- **SEO legacy routes removed:** `/analyze_seo/`, `/generate_meta/`, `/suggest_improvements/` removed; docs aligned.
- **Health pings aligned:** `/health` targets updated to `/seo/*` and `/memory/metrics`.
- **Observability + route tests:** new tests for `/observability/requests`, `/dashboard/overview`, `/identity/*`, `/memory/metrics*`.
- **Legacy diagnostics guarded:** `bridge/benchmark_similarity.py` now guarded by `__main__`.

### Evidence Checklist

- Tests executed: Not recorded in release note (see latest CI run)
- Schema changes: None

### API Contract Updates

- SEO legacy endpoints removed from contract.

### Deployment Notes

- **Environment:** No new environment variables required.
- **Migration steps:** None.

### Sign-Off

- **Approved by:** Shawn Knight
- **Maintainer sign-off (Shawn Knight):** Pending
- **Approval date:** 2026-03-22

---
## Release: Phase 6 — Ownership Cleanup + Observability Hardening

- **Version/Tag:** `main` (commit `2b43f54`)
- **Date:** 2026-03-22
- **Owner:** Shawn Knight
- **Designated maintainer:** Shawn Knight

### Summary

Phase 6 cleanup and observability hardening:
- **Ownership backfill tooling:** `Tools/backfill_user_ids.py` added (dry-run capable) for legacy user_id gaps.
- **MasterPlan version cleanup:** `master_plans.version` removed; `version_label` is canonical.
- **Identity normalization:** `genesis_sessions.user_id` and `canonical_metrics.user_id` now UUID FK (legacy columns removed).
- **Observability surface:** `GET /observability/requests` added for request metrics query.
- **Health alignment:** `/health` pings aligned with active endpoints.
- **Memory metrics:** single write path enforced from execution loop.

### Evidence Checklist

- Tests executed: Not recorded in release note (see latest CI run)
- `alembic current`: `c4f2a9d1e7b3`, `d2a7f4c1b9e8`
- `alembic heads`: `c4f2a9d1e7b3`, `d2a7f4c1b9e8`
- Schema vs. migration verification: MasterPlan version removal + request metrics indices verified via migration logs

### API Contract Updates

- `GET /observability/requests` added (JWT required).

### Deployment Notes

- **Environment:** No new environment variables required.
- **Migration steps:** `alembic upgrade head` required for schema cleanup.
- **Known issues:** Legacy rows with `user_id = NULL` still require backfill execution (see `Tools/backfill_user_ids.py`).

### Sign-Off

- **Approved by:** Shawn Knight
- **Maintainer sign-off (Shawn Knight):** Pending
- **Approval date:** 2026-03-22

---


