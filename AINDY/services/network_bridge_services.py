# /services/network_bridge_services.py
from sqlalchemy.orm import Session
from datetime import datetime
from db.models.author_model import AuthorDB

def register_author(db: Session, name: str, platform: str, notes: str | None = None):
    """
    Registers or updates an author record in the database.
    """
    existing = db.query(AuthorDB).filter_by(name=name, platform=platform).first()
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
    )
    db.add(author)
    db.commit()
    db.refresh(author)
    return author
