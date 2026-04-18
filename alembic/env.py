# alembic/env.py  -- unified version for A.I.N.D.Y.
#
# Merges two previous env.py variants:
# - original alembic env (uses config file, fileConfig)
# - memory-bridge env (uses config.DATABASE_URL + debug table listing)
#
# Notes:
# - This file inserts the project root into sys.path so imports like
#   `from AINDY.db.models import Base` work when Alembic runs from the repo root.
# - It intentionally avoids importing `main` unless you explicitly uncomment that line,
#   because main.py can have side effects (app startup, event loops). Import models only.

from __future__ import annotations
import logging
import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import pool, create_engine

# -------------------------
# Project root and sys.path
# -------------------------
# env.py lives at alembic/env.py
# parents[0] = alembic/
# parents[1] = repo root  (where AINDY/ package lives)
CURRENT_FILE = Path(__file__).resolve()
REPO_ROOT = CURRENT_FILE.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

possible_env_paths = [
    REPO_ROOT / ".env",
    REPO_ROOT / "AINDY" / ".env",
]

for env_path in possible_env_paths:
    if env_path.exists():
        load_dotenv(env_path, override=False)
        break

# -------------------------
# Alembic config
# -------------------------
config = context.config

database_url = os.getenv("DATABASE_URL")
if not database_url:
    raise RuntimeError(
        "DATABASE_URL not set. Ensure .env is present in repo root or AINDY/"
    )

config.set_main_option("sqlalchemy.url", database_url)

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# -------------------------
# Application imports (models & base)
# -------------------------
# Import the project's Base and register all models so Alembic can autogenerate migrations.
# - Import memory_persistence to ensure any models it registers get included.
# - Import models.py to load the rest of your mapped classes.
# - Avoid importing main.py by default: uncomment only if main.py is safe (no server startup).
#
from AINDY.db.base import Base
import AINDY.db.model_registry  # imports platform ORM models and registration hook
import apps.bootstrap
import AINDY.memory.memory_persistence

apps.bootstrap.bootstrap_models()

# Combine all known metadata objects
target_metadata = Base.metadata

# -------------------------
# Debug / verification (optional)
# -------------------------
# Useful to verify Alembic sees all tables. Remove or comment out after verification.
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("alembic.env")
logger.info("Running Alembic env from project root: %s", REPO_ROOT)
logger.info("Using Base metadata: %s", getattr(target_metadata, "name", "<metadata>"))

# Print table list for quick debugging (keeps output concise)
try:
    table_names = [t.name for t in target_metadata.sorted_tables]
    logger.info("🔍 Registered SQLAlchemy Tables (%d): %s", len(table_names), table_names)
except Exception:
    logger.debug("Could not enumerate tables from metadata at import time.", exc_info=True)

# Updated import for Memory Bridge models
try:
    from AINDY.memory import memory_persistence
except ImportError:
    import warnings
    warnings.warn("memory_persistence module not found — skipping Memory Bridge model registration")

# -------------------------
# Config helpers
# -------------------------
def get_database_url() -> str:
    return database_url

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
