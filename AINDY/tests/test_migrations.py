"""
test_migrations.py
--------------------------------
Checks for Alembic migration drift (current == heads).
"""
import subprocess
import sys


def _run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def _parse_revisions(output: str) -> set[str]:
    revisions = set()
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        rev = line.split()[0]
        if len(rev) >= 4:
            revisions.add(rev)
    return revisions


def test_alembic_current_matches_heads():
    current = _run([sys.executable, "-m", "alembic", "current"])
    heads = _run([sys.executable, "-m", "alembic", "heads"])

    assert current.returncode == 0, (
        f"alembic current failed: {current.stderr.strip()}"
    )
    assert heads.returncode == 0, (
        f"alembic heads failed: {heads.stderr.strip()}"
    )

    current_revs = _parse_revisions(current.stdout)
    head_revs = _parse_revisions(heads.stdout)

    assert current_revs == head_revs, (
        "Alembic drift detected. Current revisions do not match heads."
        f"\ncurrent={current_revs}\nheads={head_revs}"
    )
