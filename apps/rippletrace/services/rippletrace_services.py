# /services/rippletrace_services.py
import logging
from datetime import datetime

import uuid
from sqlalchemy.orm import Session

from apps.rippletrace.models import DropPointDB, PingDB
from apps.rippletrace.services.threadweaver import analyze_drop_point, classify_connection_type

logger = logging.getLogger(__name__)

def add_drop_point(db: Session, dp, user_id: str = None):
    user_uuid = uuid.UUID(str(user_id)) if user_id else None
    db_dp = DropPointDB(
        id=dp.id,
        title=dp.title,
        platform=dp.platform,
        url=dp.url,
        date_dropped=dp.date_dropped or datetime.utcnow(),
        core_themes=",".join(dp.core_themes),
        tagged_entities=",".join(dp.tagged_entities),
        intent=dp.intent,
        user_id=user_uuid,
    )
    db.add(db_dp)
    db.flush()
    db.refresh(db_dp)
    return db_dp

def add_ping(db: Session, pg, user_id: str = None):
    user_uuid = uuid.UUID(str(user_id)) if user_id else None
    strength = getattr(pg, "strength", None)
    connection_type = classify_connection_type(pg.connection_summary)
    if strength is None:
        strength = 1.0
    db_pg = PingDB(
        id=pg.id,
        drop_point_id=pg.drop_point_id,
        ping_type=pg.ping_type,
        source_platform=pg.source_platform,
        date_detected=pg.date_detected or datetime.utcnow(),
        connection_summary=pg.connection_summary,
        external_url=pg.external_url,
        reaction_notes=pg.reaction_notes,
        user_id=user_uuid,
        strength=strength,
        connection_type=connection_type,
    )
    db.add(db_pg)
    db.flush()
    db.refresh(db_pg)
    try:
        analyze_drop_point(pg.drop_point_id, db)
    except Exception as exc:
        logger.warning("ThreadWeaver analysis failed for ping %s: %s", pg.id, exc)
    return db_pg

def get_ripples(db: Session, drop_point_id: str, user_id: str = None):
    q = db.query(PingDB).filter(PingDB.drop_point_id == drop_point_id)
    if user_id:
        q = q.filter(PingDB.user_id == uuid.UUID(str(user_id)))
    return q.all()

def get_all_drop_points(db: Session, user_id: str = None):
    q = db.query(DropPointDB)
    if user_id:
        q = q.filter(DropPointDB.user_id == uuid.UUID(str(user_id)))
    return q.all()

def get_all_pings(db: Session, user_id: str = None):
    q = db.query(PingDB)
    if user_id:
        q = q.filter(PingDB.user_id == uuid.UUID(str(user_id)))
    return q.all()

def log_ripple_event(db: Session, event: dict, user_id: str = None):
    """
    Logs a symbolic ripple event triggered by the Bridge or other ecosystem nodes.
    Ensures the referenced DropPoint exists before inserting.
    user_id is optional — system-internal calls (bridge hooks) pass None.
    """
    from apps.rippletrace.models import DropPointDB, PingDB
    from datetime import datetime

    drop_id = event.get("drop_point_id", "bridge")

    # Ensure referenced DropPoint exists before inserting Ping
    existing_dp = db.query(DropPointDB).filter_by(id=drop_id).first()
    if not existing_dp:
        new_dp = DropPointDB(
            id=drop_id,
            title="Bridge System DropPoint",
            platform=event.get("source_platform", "AINDY"),
            url=None,
            date_dropped=datetime.utcnow(),
            core_themes="auto",
            tagged_entities="system",
            intent="auto-generated",
            user_id=None,  # system-generated drop points are unowned
        )
        db.add(new_dp)
        db.flush()
        db.refresh(new_dp)

    # Create Ping record safely
    user_uuid = uuid.UUID(str(user_id)) if user_id else None
    connection_type = classify_connection_type(event.get("summary", ""))
    new_pg = PingDB(
        id=event.get("id") or f"ripple-{datetime.utcnow().timestamp()}",
        drop_point_id=drop_id,
        ping_type=event.get("ping_type", "symbolic"),
        source_platform=event.get("source_platform", "AINDY"),
        date_detected=datetime.utcnow(),
        connection_summary=event.get("summary", ""),
        external_url=event.get("url", ""),
        reaction_notes=event.get("notes", ""),
        user_id=user_uuid,
        connection_type=connection_type,
        strength=1.0,
    )

    db.add(new_pg)
    db.flush()
    db.refresh(new_pg)
    try:
        analyze_drop_point(drop_id, db)
    except Exception as exc:
        logger.warning("ThreadWeaver analysis failed for event ping %s: %s", new_pg.id, exc)
    return new_pg


def get_recent_ripples(db: Session, limit: int = 10, user_id: str = None):
    """
    Fetch the most recent ripple/ping events for dashboard visualization.
    """
    from apps.rippletrace.models import PingDB
    q = db.query(PingDB).order_by(PingDB.date_detected.desc())
    if user_id:
        q = q.filter(PingDB.user_id == uuid.UUID(str(user_id)))
    return q.limit(limit).all()

