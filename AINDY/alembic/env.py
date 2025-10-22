# alembic/env.py  -- unified version for A.I.N.D.Y.
#
# Merges two previous env.py variants:
# - original alembic env (uses config file, fileConfig)
# - memory-bridge env (uses config.DATABASE_URL + debug table listing)
#
# Notes:
# - This file inserts the project root into sys.path so imports like `from base import Base`
#   and `from config import DATABASE_URL` work when Alembic runs from the repo root.
# - It intentionally avoids importing `main` unless you explicitly uncomment that line,
#   because main.py can have side effects (app startup, event loops). Import models only.

from __future__ import annotations
import sys, os
from pathlib import Path
import logging
from logging.config import fileConfig
from alembic import context
from sqlalchemy import engine_from_config, pool, create_engine

# -------------------------
# Project root and sys.path
# -------------------------
# PROJECT_ROOT = <repo>/A.I.N.D.Y  (two levels or one depending on layout)
# We choose parents[1] to match your earlier setup where alembic/ lives at <repo>/A.I.N.D.Y/alembic
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)


# -------------------------
# Alembic config
# -------------------------
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# -------------------------
# Application imports (models & base)
# -------------------------
# Import the project's Base and all models so Alembic can autogenerate migrations.
# - Import memory_persistence to ensure any models it registers get included.
# - Import models.py to load the rest of your mapped classes.
# - Avoid importing main.py by default: uncomment only if main.py is safe (no server startup).
#
# If you prefer to use DATABASE_URL from config module (memory bridge), we try that first,
# otherwise fall back to alembic.ini sqlalchemy.url.

try:
    # config with DATABASE_URL defined (memory bridge)
    from config import DATABASE_URL  # optional, used if present
except Exception:
    DATABASE_URL = None  # will fallback to alembic.ini value later

# Bring in Base and model modules
from db.database import Base     # declarative_base() lives here
import db.models  # imports all models inside db/models.py
import services.memory_persistence

target_metadata = Base.metadata

# -------------------------
# Debug / verification (optional)
# -------------------------
# Useful to verify Alembic sees all tables. Remove or comment out after verification.
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("alembic.env")
logger.info("Running Alembic env from project root: %s", PROJECT_ROOT)
logger.info("Using Base metadata: %s", getattr(target_metadata, "name", "<metadata>"))

# Print table list for quick debugging (keeps output concise)
try:
    table_names = [t.name for t in target_metadata.sorted_tables]
    logger.info("🔍 Registered SQLAlchemy Tables (%d): %s", len(table_names), table_names)
except Exception:
    logger.debug("Could not enumerate tables from metadata at import time.", exc_info=True)

# Updated import for Memory Bridge models
try:
    from services import memory_persistence
except ImportError:
    import warnings
    warnings.warn("memory_persistence module not found — skipping Memory Bridge model registration")

# -------------------------
# Config helpers
# -------------------------
def get_database_url() -> str:
    """
    Return the database URL used for alembic.
    Prefer `config.DATABASE_URL` if provided by config.py (memory bridge).
    Otherwise fall back to the ini value `sqlalchemy.url`.
    """
    if DATABASE_URL:
        return DATABASE_URL
    # fallback to alembic.ini sqlalchemy.url
    url = config.get_main_option("sqlalchemy.url")
    if not url:
        raise RuntimeError("No DATABASE_URL found: set config.DATABASE_URL or alembic.ini sqlalchemy.url")
    return url

# -------------------------
# Offline migrations
# -------------------------
def run_migrations_offline() -> None:
    url = get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,   # detect type changes
    )

    with context.begin_transaction():
        context.run_migrations()

# -------------------------
# Online migrations
# -------------------------
def run_migrations_online() -> None:
    # If alembic.ini provides sqlalchemy.* settings, engine_from_config could be used.
    # Here we prefer a direct engine from DATABASE_URL to keep behavior explicit.
    url = get_database_url()
    connectable = create_engine(url, poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,   # detect type changes
        )

        with context.begin_transaction():
            context.run_migrations()

# -------------------------
# Entrypoint
# -------------------------
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
