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
- Enforcement Type: Application-enforced (fail-closed for required `SystemEvent` emission on core execution and outbound external interactions); DB-enforced only if the SQL succeeds.

## 2.1 Background Lease Timestamps Use Aware UTC
- Invariant Name: Background task lease timestamps are compared as aware UTC datetimes
- Description: The background lease path normalizes Python-side timestamps to timezone-aware UTC before persistence and before any `expires_at` comparisons.
- Enforcement Location: `AINDY/services/task_services.py` (`_utcnow()`, `_ensure_aware_utc()`, lease acquire/refresh/release helpers)
- Enforcement Mechanism: Lease code uses `datetime.now(timezone.utc)` and coerces loaded lease timestamps to aware UTC if they are naive.
- What Would Break If Violated: Worker startup and heartbeat can fail with naive-vs-aware datetime comparison errors, preventing scheduler leadership acquisition.
- Enforcement Type: Application-enforced.

## 2.2 Required SystemEvent Emission Fails Closed
- Invariant Name: Required `SystemEvent` writes cannot fail silently
- Description: Critical execution and external-interaction paths must either persist their required `SystemEvent` rows or fail the calling action.
- Enforcement Location: `AINDY/services/system_event_service.py`, plus required call sites in execution, async job, and external call services
- Enforcement Mechanism: `emit_system_event(..., required=True)` raises `SystemEventEmissionError` on persistence failure after attempting a fallback `error.system_event_failure` record.
- What Would Break If Violated: The system could complete critical state transitions without a durable ledger entry, making observability incomplete and execution non-auditable.
- Enforcement Type: Application-enforced.

## 3. Memory Bridge Mutation Auth (JWT)
- Invariant Name: Memory Bridge mutations require JWT
- Description: `/bridge/nodes` and `/bridge/link` require JWT authentication; legacy HMAC permission is deprecated and ignored.
- Enforcement Location: `AINDY/routes/bridge_router.py` (router dependency `Depends(get_current_user)`)
- Enforcement Mechanism: `get_current_user` verifies JWT and raises HTTP 401 on failure.
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
- Enforcement Location:
  - `AINDY/routes/genesis_router.py: activate_masterplan`
  - `AINDY/routes/masterplan_router.py: activate_masterplan`
- Enforcement Mechanism: `db.query(MasterPlan).update({"is_active": False})` before setting selected plan active. Both activation routes enforce this.
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

## 16. (Retired) Permission Secret Default Exists
- Invariant Name: Permission secret is always defined
- Description: Deprecated; HMAC permission is no longer enforced.
- Enforcement Location: Not enforced in current implementation.
- Enforcement Mechanism: None.
- What Would Break If Violated: N/A (HMAC retired).
- Enforcement Type: Retired.

## 17. Session Isolation via `get_db`
- Invariant Name: Per-request DB session lifecycle
- Description: FastAPI routes using `Depends(get_db)` receive a new SQLAlchemy session that is closed after request.
- Enforcement Location: `AINDY/db/database.py: get_db`
- Enforcement Mechanism: Generator yields session and closes in `finally`.
- What Would Break If Violated: Session leakage and cross-request contamination.
- Enforcement Type: Application-enforced.

## 18. (Retired) HMAC Signature Computation Order and Scope Sorting
- Invariant Name: Permission signature depends on sorted scopes
- Description: Deprecated; HMAC permission is no longer enforced.
- Enforcement Location: Not enforced in current implementation.
- Enforcement Mechanism: None.
- What Would Break If Violated: N/A (HMAC retired).
- Enforcement Type: Retired.

## 19. DropPoint Presence Before Ping Creation
- Invariant Name: DropPoint exists for ripple events
- Description: Ripple event logging creates a DropPoint if the referenced `drop_point_id` does not exist.
- Enforcement Location: `AINDY/services/rippletrace_services.py: log_ripple_event`
- Enforcement Mechanism: Application logic inserts DropPoint before Ping creation.
- What Would Break If Violated: Ping insertion could fail due to foreign key constraints if DB enforces them.
- Enforcement Type: Application-enforced.

## 21. JWT Authentication on Protected Route Groups
- Invariant Name: Protected route groups require valid JWT Bearer token
- Description: All user-facing route groups require a valid JWT Bearer token. Routes protected via router-level `dependencies=[Depends(get_current_user)]`: `task_router`, `leadgen_router`, `genesis_router`, `analytics_router` (Phase 2); `seo_routes`, `authorship_router`, `arm_router`, `rippletrace_router`, `freelance_router`, `research_results_router`, `dashboard_router`, `social_router` (Phase 3). Requests without credentials or with an invalid/expired token are rejected with HTTP 401 before any route body executes.
- Enforcement Location: `AINDY/services/auth_service.py: get_current_user` (injected via router-level `dependencies=[Depends(get_current_user)]`)
- Enforcement Mechanism: `HTTPBearer` extracts the `Authorization: Bearer <token>` header. `decode_access_token()` verifies the HS256 signature and expiry using `SECRET_KEY`. Raises `HTTPException(401)` if no credentials are present or if verification fails.
- What Would Break If Violated: Unauthenticated users could access protected endpoints.
- Enforcement Type: Application-enforced. Auth routes (`POST /auth/login`, `POST /auth/register`), health routes, and bridge routes remain public.

## 22. API Key Authentication on Service-to-Service Routes
- Invariant Name: Service-to-service routes require valid API key
- Description: Routes intended for internal service-to-service calls require a valid `X-API-Key` header matching `AINDY_API_KEY` from the environment. Affected routers: `db_verify_router` (`/db/verify`), `network_bridge_router` (`/network_bridge/*`). Requests without the header or with an invalid key are rejected with HTTP 401.
- Enforcement Location: `AINDY/services/auth_service.py: verify_api_key` (injected via router-level `dependencies=[Depends(verify_api_key)]`)
- Enforcement Mechanism: Reads `X-API-Key` request header and compares to `settings.AINDY_API_KEY`. Raises `HTTPException(401)` on missing or mismatched key. Node.js gateway (`AINDY/server.js`) sends this key via `dotenv`-loaded `AINDY_API_KEY` env var on all FastAPI calls.
- What Would Break If Violated: DB schema inspection endpoint and network bridge handshake endpoint would be accessible without credentials.
- Enforcement Type: Application-enforced.

## 23. Rate Limiting on AI/Expensive Endpoints
- Invariant Name: AI-backed endpoints have per-IP rate limits
- Description: Endpoints that invoke external AI providers or perform expensive operations are rate-limited per remote IP using SlowAPI. Limits: `POST /leadgen/` (10/min), `POST /genesis/message` (20/min), `POST /genesis/synthesize` (5/min), `POST /genesis/audit` (5/min), `POST /arm/analyze` (10/min), `POST /arm/generate` (10/min).
- Enforcement Location: `@limiter.limit(...)` decorator on each route function; shared `Limiter` instance in `AINDY/services/rate_limiter.py`; `SlowAPIMiddleware` registered on the FastAPI app in `AINDY/main.py`.
- Enforcement Mechanism: SlowAPI intercepts requests before route body; returns HTTP 429 with `Retry-After` header when limit is exceeded.
- What Would Break If Violated: Unconstrained callers could exhaust OpenAI API quotas and incur unbounded cost.
- Enforcement Type: Application-enforced.

## 24. Genesis Session synthesis_ready Gate Before Lock
- Invariant Name: Only synthesis-ready sessions can produce a MasterPlan
- Description: `create_masterplan_from_genesis()` refuses to lock a genesis session unless `session.synthesis_ready` is `True`. This ensures a MasterPlan is only created from a session that has successfully completed synthesis.
- Enforcement Location: `AINDY/services/masterplan_factory.py: create_masterplan_from_genesis`
- Enforcement Mechanism: Raises `ValueError("Session is not synthesis-ready — run /genesis/synthesize first")` if `session.synthesis_ready` is `False`. Callers (`POST /genesis/lock`, `POST /masterplans/lock`) catch `ValueError` and return HTTP 422.
- What Would Break If Violated: MasterPlans could be created from incomplete or un-synthesized sessions, producing plans without a proper GPT-4o draft.
- Enforcement Type: Application-enforced.

## 25. Audit Endpoint Requires Persisted Draft
- Invariant Name: Strategic integrity audit requires a persisted draft
- Description: `POST /genesis/audit` can only run when the genesis session has a non-null `draft_json`. Sessions without a draft (i.e., synthesis has not been run yet) are rejected.
- Enforcement Location: `AINDY/routes/genesis_router.py: audit_genesis_draft`
- Enforcement Mechanism: Checks `if not session.draft_json` and raises `HTTPException(status_code=422, ...)` before calling `validate_draft_integrity()`.
- What Would Break If Violated: Audit would be called with a null/empty draft, causing either an empty OpenAI request or a MagicMock serialization error.
- Enforcement Type: Application-enforced.

## 26. Atomic MasterPlan Creation — Rollback on Failure
- Invariant Name: Factory database mutations are atomic with rollback
- Description: All DB write operations inside `create_masterplan_from_genesis()` are wrapped in a try/except. Any exception during `db.add()`, `db.commit()`, or `db.refresh()` triggers `db.rollback()` before the exception is re-raised, preserving DB consistency.
- Enforcement Location: `AINDY/services/masterplan_factory.py: create_masterplan_from_genesis` (try/except block around masterplan add + session freeze + commit)
- Enforcement Mechanism: Explicit `db.rollback()` in the except clause before re-raising.
- What Would Break If Violated: Partial DB state — e.g., a MasterPlan row inserted but session status not updated, or vice versa — could leave data in an inconsistent mid-lock state.
- Enforcement Type: Application-enforced.

## 27. Memory Node Type Enforcement (ORM Event)
- Invariant Name: `node_type` must be a valid type when set
- Description: When `memory_nodes.node_type` is not `None`, it must be one of `{"decision", "outcome", "insight", "relationship"}`.
- Enforcement Location: `AINDY/services/memory_persistence.py: validate_node_type` (SQLAlchemy `@event.listens_for(MemoryNodeModel, "before_insert")` and `"before_update"`)
- Enforcement Mechanism: Raises `ValueError` at ORM layer before the DB write executes if `node_type` is set to a value outside `VALID_NODE_TYPES`. API layer (`routes/memory_router.py`) additionally enforces this via Pydantic `Literal["decision", "outcome", "insight", "relationship"]` on `CreateNodeRequest.node_type`, returning HTTP 422 before DAO is called.
- What Would Break If Violated: Memory nodes with unconstrained `node_type` values could enter the DB, making `recall_by_type()` results unreliable and breaking type-filtered semantic search.
- Enforcement Type: Application-enforced (ORM event) + API-enforced (Pydantic Literal). Not enforced at DB level (no CHECK constraint).
- Note: Existing rows with legacy values (e.g., `"generic"`) are not affected unless updated via the ORM.

## 28. Asynchronous Embedding Write Safety
- Invariant Name: `MemoryNodeDAO.save()` never blocks request completion on embedding generation
- Description: Memory writes persist immediately with `embedding_status="pending"` and enqueue embedding generation asynchronously. If embedding generation later fails, the node remains saved and the embedding job marks the node failed or retries with backoff.
- Enforcement Location: `AINDY/db/dao/memory_node_dao.py: save`, `AINDY/services/embedding_jobs.py`
- Enforcement Mechanism: DAO writes the node first, queues async embedding work, and retrieval falls back to non-embedding paths while vectors are unavailable.
- What Would Break If Violated: Memory capture would reintroduce request-path latency and write failures for routes that depend on memory persistence.
- Enforcement Type: Application-enforced.

## 20. Documented but Not Enforced at Code Level
- Session isolation beyond routes (e.g., across background threads) is documented in various docs but not enforced beyond usage patterns. Documented but not enforced at code level.
- Any architectural invariants stated in `README.md` or `Architecture_README_v1.md` are not enforced in code. Documented but not enforced at code level.
- Alembic migrations define constraints but are not applied automatically at runtime. Documented but not enforced at code level.

## 29. Startup Schema Drift Guard
- Invariant Name: Application must refuse to start on schema drift
- Description: Startup verifies `alembic current` equals `alembic heads` unless explicitly disabled.
- Enforcement Location: `AINDY/main.py` (startup guard)
- Enforcement Mechanism: If heads differ, logs error and raises `RuntimeError`.
- What Would Break If Violated: App could run against stale or divergent schema.
- Enforcement Type: Application-enforced (startup).

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
