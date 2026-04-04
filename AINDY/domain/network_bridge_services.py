# /services/network_bridge_services.py
from sqlalchemy.orm import Session
from datetime import datetime
from db.models.author_model import AuthorDB
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
        existing.last_seen = datetime.utcnow()
        db.commit()
        db.refresh(existing)
        return existing

    author = AuthorDB(
        id=f"author-{datetime.utcnow().timestamp()}",
        name=name,
        platform=platform,
        notes=notes,
        joined_at=datetime.utcnow(),
        last_seen=datetime.utcnow(),
        user_id=normalized_user_id,
    )
    db.add(author)
    db.commit()
    db.refresh(author)
    return author


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

