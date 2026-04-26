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
from typing import Iterator
from uuid import uuid4
from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient
from pymongo import MongoClient
from pymongo.errors import PyMongoError
from sqlalchemy import create_engine, inspect
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


def _patch_session_aliases(session_factory, engine):
    patched: list[tuple[object, str, object, bool]] = []

    def _setattr(target, name: str, value):
        had_attr = hasattr(target, name)
        original = getattr(target, name, None)
        setattr(target, name, value)
        patched.append((target, name, original, had_attr))

    import AINDY.db.database as db_database

    _setattr(db_database, "SessionLocal", session_factory)
    _setattr(db_database, "engine", engine)

    for module_name, module in list(sys.modules.items()):
        if not module_name:
            continue
        if (
            module_name == "AINDY.platform_layer.async_job_service"
            and engine.dialect.name == "postgresql"
        ):
            continue
        if not (
            module_name == "main"
            or module_name == "AINDY.main"
            or module_name.startswith("routes.")
            or module_name.startswith("services.")
            or module_name.startswith("platform_layer.")
            or module_name.startswith("runtime.")
            or module_name.startswith("agents.")
            or module_name.startswith("memory.")
            or module_name.startswith("apps.")
            or module_name.startswith("core.")
            or module_name == "worker"
            or module_name.startswith("AINDY.routes.")
            or module_name.startswith("AINDY.services.")
            or module_name.startswith("AINDY.platform_layer.")
            or module_name.startswith("AINDY.runtime.")
            or module_name.startswith("AINDY.agents.")
            or module_name.startswith("AINDY.memory.")
            or module_name.startswith("AINDY.core.")
        ):
            continue
        if hasattr(module, "SessionLocal"):
            _setattr(module, "SessionLocal", session_factory)
        if hasattr(module, "engine"):
            _setattr(module, "engine", engine)

    def _restore():
        for target, name, original, had_attr in reversed(patched):
            if had_attr:
                setattr(target, name, original)
            else:
                delattr(target, name)

    return _restore


def pytest_collection_modifyitems(config, items):
    """Skip Redis-marked tests unless REDIS_URL is available."""
    if os.environ.get("REDIS_URL"):
        return

    skip_redis = pytest.mark.skip(reason="requires REDIS_URL to be set")
    for item in items:
        if "redis" in item.keywords:
            item.add_marker(skip_redis)


@pytest.fixture(scope="session")
def app(testing_session_factory, test_engine):
    from AINDY.main import app as fastapi_app

    restore = _patch_session_aliases(testing_session_factory, test_engine)
    try:
        yield fastapi_app
    finally:
        fastapi_app.dependency_overrides.clear()
        restore()


@pytest.fixture(autouse=True)
def _integration_get_db_override(app, testing_session_factory):
    from AINDY.db.database import get_db

    def _get_test_db():
        db = testing_session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _get_test_db
    yield


@pytest.fixture(scope="session")
def client(app):
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
def pg_db_session():
    """
    Function-scoped PostgreSQL fixture for integration tests.

    Guards against accidental SQLite use, runs alembic migrations once, then
    yields a sessionmaker bound to a dedicated connection for the current test.
    All DML for the test stays inside one outer transaction that is rolled back
    before global cleanup fixtures run. This avoids holding table locks across
    the full session, which can deadlock teardown when other fixtures truncate
    tables after each test.

    Usage in tests:
        def test_something(pg_db_session):
            session = pg_db_session()
            ...
    """
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url.startswith("postgresql"):
        pytest.skip(
            "Integration tests require a PostgreSQL DATABASE_URL. "
            f"Got: {db_url!r}. "
            "Pass DATABASE_URL=postgresql://... when invoking pytest -c pytest.integration.ini."
        )

    engine = create_engine(db_url)
    if not inspect(engine).get_table_names():
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
    connection = engine.connect()
    transaction = connection.begin()
    Session = sessionmaker(
        bind=connection,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )
    opened_sessions = []

    def _session_factory():
        session = Session()
        opened_sessions.append(session)
        return session

    try:
        yield _session_factory
    finally:
        for session in reversed(opened_sessions):
            try:
                if session.is_active:
                    session.rollback()
            finally:
                session.close()
        transaction.rollback()
        connection.close()
        engine.dispose()


@pytest.fixture
def redis_backend() -> Iterator:
    """Provide an isolated Redis queue namespace for each test."""
    redis_url = os.environ["REDIS_URL"]

    from AINDY.core.distributed_queue import RedisQueueBackend

    queue_name = f"aindy:test:{uuid4().hex}"
    backend = RedisQueueBackend(url=redis_url, queue_name=queue_name)

    try:
        yield backend
    finally:
        backend._redis.delete(  # type: ignore[attr-defined]
            backend._queue_name,
            backend._inflight_key,
            backend._delayed_key,
        backend._dlq_key,
        )


@pytest.fixture(scope="session")
def mongo_client() -> Iterator[MongoClient]:
    mongo_url = os.environ.get("MONGO_URL", "")
    if not mongo_url:
        pytest.skip("Integration tests require MONGO_URL to be set")

    client = MongoClient(
        mongo_url,
        serverSelectionTimeoutMS=5000,
        uuidRepresentation="standard",
    )
    try:
        client.admin.command("ping")
    except PyMongoError as exc:
        client.close()
        pytest.skip(f"MongoDB not reachable for integration tests: {exc}")
    try:
        yield client
    finally:
        client.close()


@pytest.fixture
def mongo_db(mongo_client: MongoClient):
    db_name = os.environ.get("MONGO_DB_NAME", "aindy_test")
    db = mongo_client[db_name]
    db.client.drop_database(db_name)
    try:
        yield db
    finally:
        db.client.drop_database(db_name)
