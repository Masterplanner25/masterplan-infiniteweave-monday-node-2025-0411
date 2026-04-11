"""
test_migrations.py
--------------------------------
Checks for Alembic migration drift (current == heads).

NOTE: Uses `alembic` CLI directly (not `python -m alembic`) because the
local AINDY/alembic/ migrations directory has an __init__.py that shadows
the installed alembic package when imported as a module.

This test requires a live DB connection. It is automatically skipped in
environments where the DB is unavailable (e.g. unit-test runs with a
mocked DB). Schema drift is also caught at startup by the guard in main.py.
"""
import shutil
import subprocess
import pytest
from AINDY.config import settings


def test_alembic_current_matches_heads():
    """Verify alembic is at head — no pending migrations."""
    if settings.TEST_MODE:
        pytest.skip("Alembic drift check is skipped in TEST_MODE SQLite runs")

    alembic_cmd = shutil.which("alembic")
    if not alembic_cmd:
        pytest.skip("alembic CLI not found in PATH")

    current = subprocess.run(
        [alembic_cmd, "current"],
        capture_output=True,
        text=True,
    )

    # DB connection failed (e.g. test environment with mocked DB or wrong credentials)
    if current.returncode != 0:
        pytest.skip(
            f"alembic current could not connect to DB (expected in test env): "
            f"{current.stderr[-200:].strip()}"
        )

    heads = subprocess.run(
        [alembic_cmd, "heads"],
        capture_output=True,
        text=True,
    )

    if heads.returncode != 0:
        pytest.skip(
            f"alembic heads could not connect to DB: {heads.stderr[-200:].strip()}"
        )

    # If alembic connected successfully, verify we are at head
    assert "(head)" in current.stdout, (
        "Alembic drift detected — DB is not at head revision.\n"
        f"current output: {current.stdout.strip()}\n"
        f"heads output:   {heads.stdout.strip()}\n"
        "Run: alembic upgrade head"
    )
