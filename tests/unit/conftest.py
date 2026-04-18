"""
tests/unit/conftest.py — SQLite type shims for unit tests.

Maps PostgreSQL-specific column types to their SQLite equivalents so that
tests using the in-memory SQLite test engine can create tables that contain
ARRAY, JSONB, UUID, or Vector columns.

Also registers a Python sqlite3 adapter so that Python list values bound to
ARRAY/JSON columns are automatically serialised to JSON strings.
"""
from __future__ import annotations

import json
import sqlite3

from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.compiler import compiles


# ── DDL: map ARRAY to JSON for CREATE TABLE statements ───────────────────────

@compiles(ARRAY, "sqlite")
def _compile_array_sqlite(type_, compiler, **kw):
    """Map PostgreSQL ARRAY to JSON for SQLite compatibility in unit tests."""
    return "JSON"


# ── DML: serialise Python lists to JSON strings for INSERT/UPDATE ─────────────
# SQLite's JSON column type expects a TEXT value, not a Python list object.
# Registering an sqlite3 adapter converts any Python list automatically.

sqlite3.register_adapter(list, lambda v: json.dumps(v))
