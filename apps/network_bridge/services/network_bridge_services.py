# /services/network_bridge_services.py
from sqlalchemy.orm import Session
from datetime import datetime, timezone
import uuid

from AINDY.kernel.syscall_dispatcher import dispatch_syscall

def register_author(db: Session, name: str, platform: str, notes: str | None = None, user_id: str | uuid.UUID | None = None):
    """
    Registers or updates an author record in the database.
    """
    from apps.authorship.public import register_author as register_author_public

    return register_author_public(
        db,
        name=name,
        platform=platform,
        notes=notes,
        user_id=user_id,
    )


def connect_external_author(
    db: Session,
    *,
    author_name: str,
    platform: str,
    connection_type: str,
    notes: str | None,
    user_id: str | uuid.UUID | None = None,
) -> dict:
    """
    Register the author, log a ripple event, save a metric, and commit.

    Returns the result dict for the route handler.
    All DB work (including the final commit) is owned here.
    """
    from datetime import datetime

    author = register_author(db=db, name=author_name, platform=platform, notes=notes)

    ripple_event = {
        "ping_type": connection_type,
        "source_platform": platform,
        "summary": f"{author_name} connected via {platform}",
        "notes": notes or "",
        "drop_point_id": "bridge",
    }
    normalized_user_id = str(user_id) if user_id is not None else None
    dispatch_syscall(
        "sys.v1.rippletrace.log_ripple_event",
        {
            "event_type": connection_type,
            "user_id": normalized_user_id,
            "source": platform,
            "data": ripple_event,
        },
        db=db,
        user_id=normalized_user_id,
        capability="rippletrace.write",
    )

    metric_name = f"UserEvent::{platform}"
    dispatch_syscall(
        "sys.v1.analytics.save_calculation",
        {"metric_name": metric_name, "value": 1, "user_id": normalized_user_id},
        db=db,
        user_id=normalized_user_id,
        capability="analytics.write",
    )

    db.commit()

    return {
        "status": "connected",
        "author_id": author["id"],
        "platform": platform,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def list_authors(db: Session, platform: str | None = None, limit: int = 100):
    from apps.authorship.public import list_authors as list_authors_public

    return list_authors_public(db, platform=platform, limit=limit)

