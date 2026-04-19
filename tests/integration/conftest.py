"""
tests/integration/conftest.py

Two responsibilities:
1. SQLite shims — kept for backward compatibility when integration tests are run
   via the standard pytest.ini (SQLite in-memory). These shims are no-ops against
   a real PostgreSQL connection and do not interfere.

2. PostgreSQL session fixture — session-scoped fixture used when running with
   pytest.integration.ini. Ensures DATABASE_URL points at PostgreSQL, runs
   alembic migrations once, and wraps the session in a transaction that is
   rolled back at teardown to clean up test-created rows.

Root conftest (tests/conftest.py) uses os.environ.setdefault throughout, so it
never overrides DATABASE_URL or AINDY_ALLOW_SQLITE when they are already set by
the caller — it is safe to keep as-is alongside this file.
"""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.compiler import compiles


# ── 1. SQLite shims (backward compat) ────────────────────────────────────────

@compiles(ARRAY, "sqlite")
def _compile_array_sqlite(type_, compiler, **kw):
    """Map PostgreSQL ARRAY to JSON for SQLite compatibility in integration tests."""
    return "JSON"


sqlite3.register_adapter(list, lambda v: json.dumps(v))


# ── 2. PostgreSQL session fixture ─────────────────────────────────────────────

_REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def pg_db_session():
    """
    Session-scoped PostgreSQL fixture for integration tests.

    Guards against accidental SQLite use, runs alembic migrations once, then
    yields a sessionmaker bound to a connection that wraps all test DML in a
    single transaction. The transaction is rolled back at teardown so no
    test-created rows persist between runs.

    Usage in tests:
        def test_something(pg_db_session):
            session = pg_db_session()
            ...
    """
    db_url = os.environ.get("DATABASE_URL", "")
    assert db_url.startswith("postgresql"), (
        f"Integration tests require a PostgreSQL DATABASE_URL. "
        f"Got: {db_url!r}. "
        "Pass DATABASE_URL=postgresql://... when invoking pytest -c pytest.integration.ini."
    )

    # Run alembic migrations once before any test in the session.
    result = subprocess.run(
        ["alembic", "upgrade", "head"],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"alembic upgrade head failed (exit {result.returncode}):\n"
        f"stdout: {result.stdout}\n"
        f"stderr: {result.stderr}"
    )

    engine = create_engine(db_url)
    connection = engine.connect()
    transaction = connection.begin()
    Session = sessionmaker(bind=connection)

    yield Session

    transaction.rollback()
    connection.close()
    engine.dispose()
