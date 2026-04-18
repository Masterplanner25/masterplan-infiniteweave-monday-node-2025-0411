from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session


def check_db_connectivity(db: Session) -> bool:
    """Execute a trivial query to verify the DB session is alive. Returns True on success."""
    db.execute(text("SELECT 1"))
    return True


def check_db_ready(db: Session) -> bool:
    """Readiness probe: execute SELECT 1 and return True. Raises on failure."""
    db.execute(text("SELECT 1"))
    return True
