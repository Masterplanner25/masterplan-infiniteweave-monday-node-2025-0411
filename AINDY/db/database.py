"""
database.py – Core database engine and session manager for A.I.N.D.Y.
Loads configuration from config.py, enforces UTC timestamps, and yields
database sessions for FastAPI routes and background tasks.
"""

from datetime import datetime, timezone
from sqlalchemy import create_engine, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
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
    try:
        yield db
    finally:
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



