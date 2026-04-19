# /services/network_bridge_services.py
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from apps.authorship.models import AuthorDB
import uuid

def register_author(db: Session, name: str, platform: str, notes: str | None = None, user_id: str | uuid.UUID | None = None):
    """
    Registers or updates an author record in the database.
    """
    normalized_user_id = None
    if user_id:
        normalized_user_id = uuid.UUID(str(user_id))
    existing = db.query(AuthorDB).filter_by(name=name, platform=platform, user_id=normalized_user_id).first()
    if existing:
        # AuthorDB joined_at/last_seen are legacy naive DateTime columns; SQLAlchemy may strip tzinfo here.
        existing.last_seen = datetime.now(timezone.utc)
        db.commit()
        db.refresh(existing)
        return existing

    author = AuthorDB(
        id=f"author-{datetime.now(timezone.utc).timestamp()}",
        name=name,
        platform=platform,
        notes=notes,
        # AuthorDB joined_at/last_seen are legacy naive DateTime columns; SQLAlchemy may strip tzinfo here.
        joined_at=datetime.now(timezone.utc),
        last_seen=datetime.now(timezone.utc),
        user_id=normalized_user_id,
    )
    db.add(author)
    db.commit()
    db.refresh(author)
    return author


def connect_external_author(
    db: Session,
    *,
    author_name: str,
    platform: str,
    connection_type: str,
    notes: str | None,
) -> dict:
    """
    Register the author, log a ripple event, save a metric, and commit.

    Returns the result dict for the route handler.
    All DB work (including the final commit) is owned here.
    """
    from apps.rippletrace.services import rippletrace_services
    from apps.analytics.services.calculation_services import save_calculation
    from datetime import datetime

    author = register_author(db=db, name=author_name, platform=platform, notes=notes)

    ripple_event = {
        "ping_type": connection_type,
        "source_platform": platform,
        "summary": f"{author_name} connected via {platform}",
        "notes": notes or "",
        "drop_point_id": "bridge",
    }
    rippletrace_services.log_ripple_event(db, ripple_event)

    metric_name = f"UserEvent::{platform}"
    save_calculation(db, metric_name, 1)

    db.commit()

    return {
        "status": "connected",
        "author_id": author.id,
        "platform": platform,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def list_authors(db: Session, platform: str | None = None, limit: int = 100):
    query = db.query(AuthorDB)
    if platform:
        query = query.filter(AuthorDB.platform == platform)
    authors = query.order_by(AuthorDB.last_seen.desc()).limit(limit).all()
    return [
        {
            "id": a.id,
            "name": a.name,
            "platform": a.platform,
            "notes": a.notes,
            "joined_at": a.joined_at.isoformat() if a.joined_at else None,
            "last_seen": a.last_seen.isoformat() if a.last_seen else None,
        }
        for a in authors
    ]

