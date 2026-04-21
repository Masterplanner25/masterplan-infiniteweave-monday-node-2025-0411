from __future__ import annotations

import random
import sys
from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import OperationalError
from sqlalchemy import event
from sqlalchemy import types as sqltypes
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID as PG_UUID
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from pgvector.sqlalchemy import Vector


@compiles(PG_UUID, "sqlite")
def _compile_uuid_sqlite(type_, compiler, **kw):
    return "CHAR(36)"


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"


@compiles(ARRAY, "sqlite")
def _compile_array_sqlite(type_, compiler, **kw):
    return "JSON"


@compiles(Vector, "sqlite")
def _compile_vector_sqlite(type_, compiler, **kw):
    return "BLOB"


def _import_model_registry():
    import AINDY.db.model_registry  # noqa: F401
    import apps.bootstrap
    import AINDY.memory.memory_persistence  # noqa: F401

    apps.bootstrap.bootstrap_models()


@pytest.fixture(scope="session")
def test_engine():
    import os
    from sqlalchemy import create_engine

    _import_model_registry()

    if os.environ.get("AINDY_TEST_DB") == "postgres":
        engine = create_engine(os.environ["DATABASE_URL"])
    else:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragmas(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            try:
                # The production database is PostgreSQL. SQLite is used here as a
                # lightweight test harness, and several event-chain tables rely on
                # self-referential / cross-session inserts that produce false FK
                # failures under SQLite's reduced UUID/JSON semantics.
                cursor.execute("PRAGMA foreign_keys=OFF")
            finally:
                cursor.close()

    from AINDY.db.database import Base

    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture(scope="session")
def testing_session_factory(test_engine):
    return sessionmaker(
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
        bind=test_engine,
    )


@pytest.fixture
def db_connection(test_engine):
    connection = test_engine.connect()
    transaction = connection.begin()
    try:
        yield connection
    finally:
        transaction.rollback()
        connection.close()


@pytest.fixture
def db_session_factory(db_connection):
    return sessionmaker(
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
        bind=db_connection,
    )


@pytest.fixture
def db_session(db_session_factory):
    session = db_session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def mock_db(app, db_session):
    from AINDY.db.database import get_db

    def _override():
        yield db_session

    app.dependency_overrides[get_db] = _override
    try:
        yield db_session
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def fixed_time():
    class FrozenDateTime(datetime):
        _fixed = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return cls._fixed.replace(tzinfo=None)
            return cls._fixed.astimezone(tz)

        @classmethod
        def utcnow(cls):
            return cls._fixed.replace(tzinfo=None)

    return FrozenDateTime._fixed, FrozenDateTime


@pytest.fixture(autouse=True)
def deterministic_random():
    random.seed(42)
    yield
    random.seed(42)


@pytest.fixture(autouse=True)
def cleanup_committed_test_state(test_engine):
    yield
    from AINDY.db.database import Base

    with test_engine.begin() as connection:
        for table in reversed(Base.metadata.sorted_tables):
            try:
                connection.execute(table.delete())
            except OperationalError as exc:
                if "no such table" not in str(exc).lower():
                    raise
