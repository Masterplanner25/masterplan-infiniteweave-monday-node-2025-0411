"""
database.py – Core database engine and session manager for A.I.N.D.Y.
Loads configuration from config.py, enforces UTC timestamps, and yields
database sessions for FastAPI routes and background tasks.
"""

from datetime import datetime, timezone
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool, StaticPool
import logging
import threading
import time

from AINDY.config import settings
from AINDY.core.observability_events import emit_observability_event

# --------------------------------------------------------------------
# Database Configuration
# --------------------------------------------------------------------
DATABASE_URL = settings.DATABASE_URL

# SQLAlchemy Base
Base = declarative_base()

# Engine + Session Factory
connect_args = {}
pool_kwargs: dict = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
    pool_kwargs = {"poolclass": StaticPool}
else:
    connect_args = {"connect_timeout": 10}
    if settings.is_testing:
        # Tests create many short-lived sessions across app imports and fixtures.
        # NullPool avoids cross-test pool exhaustion and stale pooled connections.
        pool_kwargs = {"poolclass": NullPool}
        connect_args["options"] = (
            "-c statement_timeout=10000 "
            "-c idle_in_transaction_session_timeout=10000"
        )
    else:
        pool_kwargs = {
            "pool_size": settings.DB_POOL_SIZE,
            "max_overflow": settings.DB_MAX_OVERFLOW,
            "pool_timeout": settings.DB_POOL_TIMEOUT,
            "pool_recycle": settings.DB_POOL_RECYCLE,
            "pool_pre_ping": True,
        }

engine = create_engine(DATABASE_URL, connect_args=connect_args, **pool_kwargs)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
logger = logging.getLogger(__name__)
_session_guard_lock = threading.Lock()
_active_sessions: set[int] = set()

# --------------------------------------------------------------------
# UTC Enforcement
# --------------------------------------------------------------------
utcnow = lambda: datetime.now(timezone.utc)

@event.listens_for(engine, "connect")
def set_utc(dbapi_connection, connection_record):
    """Ensure all DB connections operate in UTC."""
    cursor = dbapi_connection.cursor()
    try:
        if DATABASE_URL.startswith("sqlite"):
            return
        cursor.execute("SET TIME ZONE 'UTC';")
        if settings.is_testing:
            cursor.execute("SET statement_timeout = '10s';")
            cursor.execute("SET idle_in_transaction_session_timeout = '10s';")
    except Exception as exc:
        emit_observability_event(
            logger,
            event="db_set_utc_failed",
            level="error",
            error=str(exc),
        )
        raise
    finally:
        cursor.close()


@event.listens_for(engine, "before_cursor_execute")
def _track_query_start(conn, cursor, statement, parameters, context, executemany):
    if settings.is_testing:
        context._query_start_time = time.perf_counter()


@event.listens_for(engine, "after_cursor_execute")
def _log_slow_queries(conn, cursor, statement, parameters, context, executemany):
    if not settings.is_testing:
        return
    started_at = getattr(context, "_query_start_time", None)
    if started_at is None:
        return
    elapsed_ms = (time.perf_counter() - started_at) * 1000.0
    if elapsed_ms >= 2000:
        logger.warning(
            "Slow test query detected (%.1f ms): %s",
            elapsed_ms,
            " ".join(str(statement).split())[:300],
        )

# --------------------------------------------------------------------
# FastAPI Dependency
# --------------------------------------------------------------------
def get_db():
    """Provide a transactional session scope for routes and services."""
    db = SessionLocal()
    session_id = id(db)
    with _session_guard_lock:
        if session_id in _active_sessions:
            logger.warning("DB session reuse detected (session_id=%s).", session_id)
        _active_sessions.add(session_id)
    try:
        yield db
    finally:
        with _session_guard_lock:
            _active_sessions.discard(session_id)
        db.close()

# --------------------------------------------------------------------
# Utility
# --------------------------------------------------------------------
def test_connection():
    """Manual diagnostic helper."""
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT now();"))
            logger.info("✅ Database connected at: %s", list(result)[0][0])
    except Exception as e:
        logger.exception("❌ Database connection failed: %s", e)




