# Migration Policy

This document describes the current Alembic migration discipline as practiced in the repository. It does not invent rules that are not already observed; it records what is done.

## 1. Alembic Source of Truth

- All schema migrations live in `AINDY/alembic/versions/`.
- `AINDY/alembic/env.py` configures Alembic to read `DATABASE_URL` from the `AINDY/config.py` `Settings` object.
- `AINDY/alembic.ini` is the Alembic configuration file; `script_location = alembic`.
- Alembic is the sole mechanism for schema changes in production. SQLAlchemy models alone do not alter the live database.

### Verification Commands
```bash
# From AINDY/ directory:
alembic current          # what revision the DB is on
alembic heads            # what revision(s) are at the head
alembic history          # full revision chain
alembic upgrade head     # apply all pending migrations
```

## 2. Model Changes

### Required Steps When Changing `AINDY/db/models/`

1. **Edit the SQLAlchemy model** in `AINDY/db/models/*.py`.
2. **Generate a new Alembic revision** with a descriptive message:
   ```bash
   alembic revision --autogenerate -m "add_X_column_to_Y_table"
   ```
3. **Review the generated migration** — autogenerate does not always produce correct output. Verify:
   - New columns have correct types, `nullable` settings, and defaults.
   - No existing columns are dropped unless intentional.
   - Index and constraint names are explicit (avoid auto-generated names that may differ between environments).
4. **Add a test** confirming the new table/column exists (column presence tests use `Model.__table__.columns`).
5. **Apply the migration immediately** in the target environment — do not start the application or run the test suite against the live DB until this is done:
   ```bash
   alembic upgrade head
   ```

> **Rule: Always run `alembic upgrade head` immediately after any SQLAlchemy model change.**
> SQLAlchemy model edits do not alter the live database. Forgetting to apply the migration causes schema drift: the application code expects columns that don't exist in the DB, producing runtime errors or silent data corruption. This applies in development, CI, and production — every environment, every time.

### Additive-Only Policy
- Columns are added, never removed, during active development unless explicitly agreed.
- This policy exists because removing a column requires coordinating model code, migration, and all query sites simultaneously — additive changes reduce blast radius.
- Example applied: `user_id_str` (String) was added to `genesis_sessions` alongside the existing integer `user_id` rather than replacing it.

## 3. Migration Integrity

### Forward-Only Migrations
- Migrations must not edit or delete previously applied revisions.
- New constraints, renames, or restructures require a new revision — never in-place edits.

### Constraint and Index Naming
- Unique constraints and indexes must be given explicit names (e.g., `"uq_memory_links_unique"`, `"uq_canonical_period_scope"`).
- Auto-generated constraint names can differ between Alembic versions and environments, causing migration drift.

### Merge Revisions
- When branches diverge (multiple heads), create a merge revision:
  ```bash
  alembic merge heads -m "merge_branch_A_and_B"
  ```
- Merge revisions must be empty (no schema changes) unless the merge itself resolves a conflict.

### Migration Validation Before Merge
- Run `alembic upgrade head` against a clean test DB before any merge that includes schema changes.
- Confirm `alembic current` == `alembic heads` after applying.
- Run the full test suite after migration to catch model/migration drift.

## 4. Known Migration Debt

- Multiple overlapping migrations and no automated migration validation in CI (see `docs/roadmap/TECH_DEBT.md §2`).
- Some application-level constraints (e.g., genesis session locking, synthesis_ready gate) are not enforced at DB level — they depend on application code only.
- Several FK relationships exist in ORM models but are not backed by DB-level FK constraints in all migrations.
- `AINDY/version.json` and `AINDY/system_manifest.json` are not auto-updated by migrations; they must be manually updated when a release is tagged.
