"""
tests/integration/conftest.py — SQLite compatibility shims for integration tests.

Maps PostgreSQL ARRAY to JSON so that the SQLite in-memory test engine can
create tables with ARRAY columns (e.g. platform_api_keys.scopes).

Also registers a Python sqlite3 adapter so that Python list values bound to
ARRAY/JSON columns are automatically serialised to JSON strings.
"""
from __future__ import annotations

import json
import sqlite3

from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.compiler import compiles


@compiles(ARRAY, "sqlite")
def _compile_array_sqlite(type_, compiler, **kw):
    """Map PostgreSQL ARRAY to JSON for SQLite compatibility in integration tests."""
    return "JSON"


# Serialise Python lists to JSON strings for INSERT/UPDATE on JSON/ARRAY columns.
sqlite3.register_adapter(list, lambda v: json.dumps(v))
