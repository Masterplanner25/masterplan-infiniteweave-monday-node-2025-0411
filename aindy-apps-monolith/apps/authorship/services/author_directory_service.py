from __future__ import annotations

from datetime import datetime, timezone
import uuid

from sqlalchemy.orm import Session


def upsert_author(
    db: Session,
    *,
    name: str,
    platform: str,
    notes: str | None = None,
    user_id: str | uuid.UUID | None = None,
):
    from apps.authorship.models import AuthorDB

    normalized_user_id = uuid.UUID(str(user_id)) if user_id else None
    existing = (
        db.query(AuthorDB)
        .filter_by(name=name, platform=platform, user_id=normalized_user_id)
        .first()
    )
    if existing:
        existing.last_seen = datetime.now(timezone.utc)
        db.commit()
        db.refresh(existing)
        return existing

    author = AuthorDB(
        id=f"author-{datetime.now(timezone.utc).timestamp()}",
        name=name,
        platform=platform,
        notes=notes,
        joined_at=datetime.now(timezone.utc),
        last_seen=datetime.now(timezone.utc),
        user_id=normalized_user_id,
    )
    db.add(author)
    db.commit()
    db.refresh(author)
    return author


def list_authors(
    db: Session,
    *,
    platform: str | None = None,
    limit: int = 100,
) -> list:
    from apps.authorship.models import AuthorDB

    query = db.query(AuthorDB)
    if platform:
        query = query.filter(AuthorDB.platform == platform)
    return query.order_by(AuthorDB.last_seen.desc()).limit(limit).all()
