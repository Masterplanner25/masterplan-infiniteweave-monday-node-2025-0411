import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from config import DATABASE_URL
from base import Base
from models import *     # bring in all models from models.py
from main import *       # bring in models from main.py

from alembic import context
from sqlalchemy import create_engine, pool

import logging
logging.basicConfig(level=logging.DEBUG)

target_metadata = Base.metadata

# Add DEBUG PRINT to verify what Alembic sees
print("\n🔍 Registered SQLAlchemy Tables:")
for table in Base.metadata.sorted_tables:
    print(f" - {table.name}")
print("🔍 All tables:", list(Base.metadata.tables.keys()))

def run_migrations_offline():
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online():
    connectable = create_engine(DATABASE_URL, poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
