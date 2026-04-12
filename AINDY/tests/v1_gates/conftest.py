"""
Gate test conftest — SQLite compatibility shims for gate tests.

The shared fixtures/db.py already handles PG_UUID, JSONB, and Vector.
This file adds the missing ARRAY -> JSON shim so tests using the
`client`, `db_session`, and `app` fixtures work against the SQLite
in-memory test engine.

It also re-patches db.database.SessionLocal to the engine-bound
testing_session_factory so that observability emits (which call
SessionLocal() internally) use independent connections that survive
the connection-level rollbacks that the pipeline's FK errors trigger
in the test environment.
"""
from __future__ import annotations

import pytest
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.compiler import compiles


@compiles(ARRAY, "sqlite")
def _compile_array_sqlite(type_, compiler, **kw):
    """Map PostgreSQL ARRAY to JSON for SQLite compatibility in tests."""
    return "JSON"


@pytest.fixture(autouse=True)
def _patch_session_local_to_engine(app, testing_session_factory, monkeypatch):
    """
    Re-patch db.database.SessionLocal to the engine-bound factory.

    The shared client fixture patches SessionLocal to db_session_factory
    (bound to a single db_connection with an outer transaction).  In the
    gate-test environment the pipeline's FK errors cause rollbacks on that
    shared connection, undoing any observability emits before the test can
    query them.

    Depends on `app` so this patch runs AFTER the client fixture's patch,
    ensuring the engine-bound factory is the one in effect during the test.

    Using the engine-bound factory means SessionLocal() opens its own
    connection, so its commits are real and survive subsequent rollbacks
    on the test connection.
    """
    import AINDY.db.database as _db_module

    monkeypatch.setattr(_db_module, "SessionLocal", testing_session_factory, raising=False)
