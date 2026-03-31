Test layout target:

- `tests/unit/` for pure logic
- `tests/integration/` for DB-backed service tests
- `tests/api/` for route and contract tests
- `tests/system/` for end-to-end runtime, scheduler, and invariant behavior
- `tests/fixtures/` for shared pytest fixtures

The root-level legacy `test_*.py` files have been migrated out of `tests/`.
New and rebuilt tests should be added under the structured directories above.

Current foundation:

- shared SQLite-backed fixtures live under `tests/fixtures/`
- `TEST_MODE=true` is the default pytest runtime
- test env defaults are injected from `tests/conftest.py`
- Mongo connectivity is disabled in tests (`SKIP_MONGO_PING=1`, blank `MONGO_URL`) to avoid external dependencies
- API-key protected routes use `api_key_headers`
- the legacy compatibility surface is enabled in tests and remains API-key protected
- async heavy execution is disabled by default unless a test explicitly enables it
- `SystemEvent` remains active in tests; the DB-backed fixtures are expected to persist it successfully
- `PERMISSION_SECRET` is set to a non-placeholder test value so security checks validate the real config contract

Current invariant coverage:

- `tests/system/test_invariants.py` validates:
  - execution emits durable events
  - no cross-user leakage
  - capability denial changes execution outcome
  - memory create/read consistency
  - request metrics and dashboard summaries reflect actions

Optional Postgres-backed test stack:

- `docker compose -f docker-compose.test.yml up -d`
- point `DATABASE_URL` at `postgresql+psycopg2://postgres:postgres@localhost:5434/aindy_test`
- run `pytest`
