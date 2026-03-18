# Invariants

This document lists invariants enforced by the current implementation. Each invariant includes enforcement location and mechanism. If a rule is mentioned in docs but not enforced in code, it is explicitly marked.

## 1. PostgreSQL Requirement for `DATABASE_URL`
- Invariant Name: PostgreSQL database URL required
- Description: `DATABASE_URL` must start with `postgres`.
- Enforcement Location: `AINDY/config.py: Settings.ensure_postgres`
- Enforcement Mechanism: Pydantic field validator raises `ValueError` if URI does not start with `postgres`.
- What Would Break If Violated: Application fails to start due to configuration validation error.
- Enforcement Type: Application-enforced.

## 2. UTC Timezone Enforcement on DB Connections
- Invariant Name: DB connections use UTC timezone
- Description: SQLAlchemy engine connection sets DB session timezone to UTC.
- Enforcement Location: `AINDY/db/database.py: set_utc` (SQLAlchemy `event.listens_for(engine, "connect")`)
- Enforcement Mechanism: Executes `SET TIME ZONE 'UTC';` on connection. Exceptions are swallowed.
- What Would Break If Violated: Timestamps could be stored in non-UTC timezone; time-based logic may drift.
- Enforcement Type: Application-enforced (best-effort); DB-enforced only if the SQL succeeds.

## 3. Memory Bridge Permission Signature and TTL
- Invariant Name: Memory Bridge mutations require valid HMAC signature and TTL
- Description: `/bridge/nodes` and `/bridge/link` require a signed permission with valid signature and non-expired TTL.
- Enforcement Location: `AINDY/routes/bridge_router.py: verify_permission_or_403`
- Enforcement Mechanism: HMAC SHA-256 signature check and timestamp + TTL expiration check; raises HTTP 403 on failure.
- What Would Break If Violated: Unauthorized writes to memory bridge nodes or links.
- Enforcement Type: Application-enforced.

## 4. Memory Link Uniqueness (DB)
- Invariant Name: Memory links are unique per (source, target, link_type)
- Description: `memory_links` enforces uniqueness across `source_node_id`, `target_node_id`, `link_type`.
- Enforcement Location:
- `AINDY/services/memory_persistence.py: MemoryLinkModel` (unique index `uq_memory_links_unique`)
- `AINDY/alembic/versions/bff24d352475_create_memory_nodes_links.py`
- `AINDY/alembic/versions/831b86c9e536_improve_memory_nodes_indexes.py`
- `AINDY/alembic/versions/a318e9194478_improve_memory_nodes_uuid_defaults_tsv_.py`
- `AINDY/alembic/versions/f4ef29bb03f3_merge_task_models.py`
- Enforcement Mechanism: Database unique index.
- What Would Break If Violated: Duplicate links in memory graph; potential graph ambiguity.
- Enforcement Type: DB-enforced.

## 5. Memory Links Cannot Self-Reference
- Invariant Name: Memory link source != target
- Description: `source_id` and `target_id` must differ when creating a link.
- Enforcement Location: `AINDY/services/memory_persistence.py: MemoryNodeDAO.create_link`
- Enforcement Mechanism: Application logic raises `ValueError` if source == target.
- What Would Break If Violated: Self-referential link creation; not allowed by application logic.
- Enforcement Type: Application-enforced.

## 6. Memory Links Require Existing Nodes
- Invariant Name: Memory links require existing nodes
- Description: Both `source_id` and `target_id` must exist in `memory_nodes`.
- Enforcement Location: `AINDY/services/memory_persistence.py: MemoryNodeDAO.create_link`
- Enforcement Mechanism: Application logic checks count of existing node IDs; raises `ValueError` if not both found.
- What Would Break If Violated: Links would point to nonexistent nodes.
- Enforcement Type: Application-enforced.

## 7. Memory Link Foreign Keys
- Invariant Name: Memory links reference valid memory nodes
- Description: `memory_links.source_node_id` and `memory_links.target_node_id` are foreign keys to `memory_nodes.id`.
- Enforcement Location:
- `AINDY/alembic/versions/c7602451aabb_init_memory_persistence.py`
- `AINDY/alembic/versions/f4ef29bb03f3_merge_task_models.py`
- Enforcement Mechanism: DB foreign key constraints.
- What Would Break If Violated: Link creation would fail due to FK constraint violations.
- Enforcement Type: DB-enforced.

## 8. Single Active MasterPlan on Activation
- Invariant Name: Only one active masterplan
- Description: Activating a masterplan deactivates all other plans.
- Enforcement Location: `AINDY/routes/genesis_router.py: activate_masterplan`
- Enforcement Mechanism: `db.query(MasterPlan).update({"is_active": False})` before setting selected plan active.
- What Would Break If Violated: Multiple masterplans marked active simultaneously.
- Enforcement Type: Application-enforced.

## 9. Genesis Session Locking
- Invariant Name: Genesis sessions cannot be locked twice
- Description: A genesis session with status `locked` cannot be re-locked or used to create another masterplan.
- Enforcement Location: `AINDY/services/masterplan_factory.py: create_masterplan_from_genesis`
- Enforcement Mechanism: Raises `Exception("Session already locked")` if `session.status == "locked"`.
- What Would Break If Violated: Multiple masterplans could derive from the same locked session.
- Enforcement Type: Application-enforced.

## 10. Canonical Metrics Uniqueness per Period Scope
- Invariant Name: Canonical metrics unique per masterplan/scope/period
- Description: `canonical_metrics` enforces uniqueness across masterplan and period scope dimensions.
- Enforcement Location:
- `AINDY/db/models/metrics_models.py: CanonicalMetricDB.__table_args__`
- `AINDY/alembic/versions/97ef6237e153_structure_integrity_check.py`
- Enforcement Mechanism: `UniqueConstraint(..., name="uq_canonical_period_scope")`.
- What Would Break If Violated: Duplicate metric rows for the same scope and period.
- Enforcement Type: DB-enforced.

## 11. Required Non-Null Columns (Selected Examples)
- Invariant Name: Column non-null constraints are respected
- Description: Some columns are defined with `nullable=False` and will reject NULL inserts.
- Enforcement Location: SQLAlchemy models and migrations:
- `AINDY/db/models/masterplan.py`: `start_date`, `duration_years`, `target_date` are `nullable=False`.
- `AINDY/db/models/freelance.py`: `client_name`, `client_email`, `service_type`, `price` are `nullable=False`.
- `AINDY/services/memory_persistence.py` and `AINDY/alembic/versions/c7602451aabb_init_memory_persistence.py`: `memory_nodes.content`, `memory_nodes.node_type`, `memory_links.source_node_id`, `memory_links.target_node_id`, `memory_links.link_type`, `memory_links.strength` are `nullable=False`.
- Enforcement Mechanism: DB-level not-null constraints for fields marked `nullable=False`.
- What Would Break If Violated: Insert/update failures at DB level.
- Enforcement Type: DB-enforced.

## 12. Memory Nodes UUID Defaults (DB)
- Invariant Name: Memory node IDs default to UUIDs
- Description: `memory_nodes.id` defaults to `gen_random_uuid()` in DB migrations.
- Enforcement Location:
- `AINDY/alembic/versions/c7602451aabb_init_memory_persistence.py`
- `AINDY/alembic/versions/831b86c9e536_improve_memory_nodes_indexes.py`
- `AINDY/alembic/versions/a318e9194478_improve_memory_nodes_uuid_defaults_tsv_.py`
- Enforcement Mechanism: DB default function `gen_random_uuid()`.
- What Would Break If Violated: Inserts without explicit IDs could fail or create null IDs.
- Enforcement Type: DB-enforced.

## 13. Memory Nodes Updated Timestamp Trigger (DB)
- Invariant Name: `memory_nodes.updated_at` is auto-updated on update
- Description: DB trigger updates `updated_at` before updates.
- Enforcement Location:
- `AINDY/alembic/versions/831b86c9e536_improve_memory_nodes_indexes.py`
- `AINDY/alembic/versions/a318e9194478_improve_memory_nodes_uuid_defaults_tsv_.py`
- Enforcement Mechanism: PL/pgSQL trigger `trg_update_memory_nodes_updated_at`.
- What Would Break If Violated: `updated_at` would not reflect row updates consistently.
- Enforcement Type: DB-enforced.

## 14. Memory Nodes Full-Text Indexing (DB)
- Invariant Name: `memory_nodes` content is indexed for full-text search
- Description: DB-level tsvector/index exists in migrations (may be added/removed by migration history).
- Enforcement Location:
- `AINDY/alembic/versions/a318e9194478_improve_memory_nodes_uuid_defaults_tsv_.py`
- `AINDY/alembic/versions/831b86c9e536_improve_memory_nodes_indexes.py`
- `AINDY/alembic/versions/f4ef29bb03f3_merge_task_models.py` (drops content_tsv/index)
- Enforcement Mechanism: DB index and trigger definitions in migrations.
- What Would Break If Violated: Full-text search performance or behavior may degrade. Presence depends on applied migration set.
- Enforcement Type: DB-enforced when migrations are applied; not enforced in application code.

## 15. Author System Identity Seeding
- Invariant Name: System author record exists or is updated at startup
- Description: A record with id `author-system` is created if missing; otherwise `last_seen` is updated.
- Enforcement Location: `AINDY/main.py: ensure_system_identity` (startup event)
- Enforcement Mechanism: Application logic creates or updates row in `authors` table.
- What Would Break If Violated: System identity row may be missing; downstream references could fail.
- Enforcement Type: Application-enforced.

## 16. Permission Secret Default Exists
- Invariant Name: Permission secret is always defined
- Description: `PERMISSION_SECRET` is read from env with a fallback string.
- Enforcement Location: `AINDY/routes/bridge_router.py: PERMISSION_SECRET = os.getenv(..., "dev-secret-must-change")`
- Enforcement Mechanism: Default value ensures non-empty secret string at runtime.
- What Would Break If Violated: HMAC validation would be undefined; requests could not be verified.
- Enforcement Type: Application-enforced.

## 17. Session Isolation via `get_db`
- Invariant Name: Per-request DB session lifecycle
- Description: FastAPI routes using `Depends(get_db)` receive a new SQLAlchemy session that is closed after request.
- Enforcement Location: `AINDY/db/database.py: get_db`
- Enforcement Mechanism: Generator yields session and closes in `finally`.
- What Would Break If Violated: Session leakage and cross-request contamination.
- Enforcement Type: Application-enforced.

## 18. HMAC Signature Computation Order and Scope Sorting
- Invariant Name: Permission signature depends on sorted scopes
- Description: Permission signature uses `','.join(sorted(scopes))` in payload.
- Enforcement Location: `AINDY/routes/bridge_router.py: compute_perm_sig`
- Enforcement Mechanism: Application logic for signature generation/verification.
- What Would Break If Violated: Valid permissions would fail verification if scopes are not sorted consistently.
- Enforcement Type: Application-enforced.

## 19. DropPoint Presence Before Ping Creation
- Invariant Name: DropPoint exists for ripple events
- Description: Ripple event logging creates a DropPoint if the referenced `drop_point_id` does not exist.
- Enforcement Location: `AINDY/services/rippletrace_services.py: log_ripple_event`
- Enforcement Mechanism: Application logic inserts DropPoint before Ping creation.
- What Would Break If Violated: Ping insertion could fail due to foreign key constraints if DB enforces them.
- Enforcement Type: Application-enforced.

## 20. Documented but Not Enforced at Code Level
- Session isolation beyond routes (e.g., across background threads) is documented in various docs but not enforced beyond usage patterns. Documented but not enforced at code level.
- Any architectural invariants stated in `README.md` or `Architecture_README_v1.md` are not enforced in code. Documented but not enforced at code level.
- Alembic migrations define constraints but are not applied automatically at runtime. Documented but not enforced at code level.

## Schema vs. Migration Verification Checklist
- Confirm the current DB schema matches Alembic head:
- Run `alembic current` in `AINDY/` to capture current revision.
- Run `alembic heads` in `AINDY/` to identify expected head revision(s).
- If `current` != `heads`, review unapplied migrations and apply in a controlled environment.
- Validate key invariants at the DB level using schema inspection:
- Memory Bridge: verify `memory_links` unique index and FK constraints exist.
- Canonical metrics: verify `uq_canonical_period_scope` exists.
- Masterplan: verify `master_plans` contains `parent_id` and `linked_genesis_session_id` FKs (if expected by migrations).
- If discrepancies exist, treat migration drift as a blocking issue before further changes.

## Appendix: DB Inspection Commands
Use these SQL snippets against the PostgreSQL database to verify constraints and indexes. Adjust schema name if not `public`.

### Memory Bridge Constraints and Indexes
```sql
-- Unique index on memory_links (source_node_id, target_node_id, link_type)
SELECT indexname, indexdef
FROM pg_indexes
WHERE tablename = 'memory_links' AND indexname IN ('uq_memory_links_unique', 'ux_memory_links_src_tgt_type');
```

```sql
-- Foreign keys from memory_links to memory_nodes
SELECT conname, conrelid::regclass AS table_name, confrelid::regclass AS ref_table, pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE conrelid = 'memory_links'::regclass AND contype = 'f';
```

```sql
-- GIN index on memory_nodes tags
SELECT indexname, indexdef
FROM pg_indexes
WHERE tablename = 'memory_nodes' AND indexname = 'ix_memory_nodes_tags_gin';
```

### Canonical Metrics Unique Constraint
```sql
-- Unique constraint on canonical_metrics
SELECT conname, conrelid::regclass AS table_name, pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE conrelid = 'canonical_metrics'::regclass AND contype = 'u';
```

### MasterPlan Foreign Keys
```sql
-- Foreign keys on master_plans
SELECT conname, conrelid::regclass AS table_name, confrelid::regclass AS ref_table, pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE conrelid = 'master_plans'::regclass AND contype = 'f';
```

### Not-Null Columns (Sample)
```sql
-- Check not-null columns in master_plans
SELECT column_name, is_nullable, data_type
FROM information_schema.columns
WHERE table_name = 'master_plans' AND column_name IN ('start_date', 'duration_years', 'target_date');
```
