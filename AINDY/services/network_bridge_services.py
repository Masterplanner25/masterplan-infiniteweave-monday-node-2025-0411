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
