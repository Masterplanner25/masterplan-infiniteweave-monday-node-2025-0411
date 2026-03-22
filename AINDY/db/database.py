"""
database.py – Core database engine and session manager for A.I.N.D.Y.
Loads configuration from config.py, enforces UTC timestamps, and yields
database sessions for FastAPI routes and background tasks.
"""

from datetime import datetime, timezone
from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker
import logging
import threading
from config import settings

# --------------------------------------------------------------------
# Database Configuration
# --------------------------------------------------------------------
DATABASE_URL = settings.DATABASE_URL

# SQLAlchemy Base
Base = declarative_base()

# Engine + Session Factory
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,        # Reconnect dropped sessions
    pool_size=10,              # Handle concurrent async calls
    max_overflow=20,           # Burst allowance
)

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
        cursor.execute("SET TIME ZONE 'UTC';")
    except Exception:
        pass
    finally:
        cursor.close()

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
            result = conn.execute("SELECT now();")
            print("✅ Database connected at:", list(result)[0][0])
    except Exception as e:
        print("❌ Database connection failed:", e)



