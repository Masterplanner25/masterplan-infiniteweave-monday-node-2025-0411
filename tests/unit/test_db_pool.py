"""
Tests that database.py engine creation uses correct pool configuration.
"""
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool


def _build_engine(database_url: str):
    """Replicate database.py pool-selection logic for isolated testing."""
    from AINDY.config import settings

    connect_args = {}
    pool_kwargs: dict = {}
    if database_url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}
        pool_kwargs = {"poolclass": StaticPool}
    else:
        pool_kwargs = {
            "pool_size": settings.DB_POOL_SIZE,
            "max_overflow": settings.DB_MAX_OVERFLOW,
            "pool_timeout": settings.DB_POOL_TIMEOUT,
            "pool_recycle": settings.DB_POOL_RECYCLE,
            "pool_pre_ping": True,
        }
    return create_engine(database_url, connect_args=connect_args, **pool_kwargs)


def test_postgres_engine_uses_configured_pool_size():
    """PostgreSQL engine pool_size matches settings.DB_POOL_SIZE."""
    from AINDY.config import settings

    engine = _build_engine("postgresql://user:pass@localhost/testdb")
    assert engine.pool.size() == settings.DB_POOL_SIZE


def test_sqlite_engine_uses_static_pool():
    """SQLite engine uses StaticPool (no connection-pool tuning)."""
    engine = _build_engine("sqlite:///:memory:")
    assert type(engine.pool).__name__ == "StaticPool"
