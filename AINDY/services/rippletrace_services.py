# /services/rippletrace_services.py
from sqlalchemy.orm import Session
from db.models import DropPointDB, PingDB
from datetime import datetime

def add_drop_point(db: Session, dp):
    db_dp = DropPointDB(
        id=dp.id,
        title=dp.title,
        platform=dp.platform,
        url=dp.url,
        date_dropped=dp.date_dropped or datetime.utcnow(),
        core_themes=",".join(dp.core_themes),
        tagged_entities=",".join(dp.tagged_entities),
        intent=dp.intent
    )
    db.add(db_dp)
    db.flush()
    db.refresh(db_dp)
    return db_dp

def add_ping(db: Session, pg):
    db_pg = PingDB(
        id=pg.id,
        drop_point_id=pg.drop_point_id,
        ping_type=pg.ping_type,
        source_platform=pg.source_platform,
        date_detected=pg.date_detected or datetime.utcnow(),
        connection_summary=pg.connection_summary,
        external_url=pg.external_url,
        reaction_notes=pg.reaction_notes
    )
    db.add(db_pg)
    db.flush()
    db.refresh(db_pg)
    return db_pg

def get_ripples(db: Session, drop_point_id: str):
    return db.query(PingDB).filter(PingDB.drop_point_id == drop_point_id).all()

def get_all_drop_points(db: Session):
    return db.query(DropPointDB).all()

def get_all_pings(db: Session):
    return db.query(PingDB).all()

def log_ripple_event(db: Session, event: dict):
    """
    Logs a symbolic ripple event triggered by the Bridge or other ecosystem nodes.
    Ensures the referenced DropPoint exists before inserting.
    """
    from db.models import DropPointDB, PingDB
    from datetime import datetime

    drop_id = event.get("drop_point_id", "bridge")

    # ✅ Ensure referenced DropPoint exists before inserting Ping
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
            intent="auto-generated"
        )
        db.add(new_dp)
        db.flush()        
        db.refresh(new_dp)

    # ✅ Create Ping record safely
    new_pg = PingDB(
        id=event.get("id") or f"ripple-{datetime.utcnow().timestamp()}",
        drop_point_id=drop_id,
        ping_type=event.get("ping_type", "symbolic"),
        source_platform=event.get("source_platform", "AINDY"),
        date_detected=datetime.utcnow(),
        connection_summary=event.get("summary", ""),
        external_url=event.get("url", ""),
        reaction_notes=event.get("notes", "")
    )

    db.add(new_pg)
    db.flush()
    db.refresh(new_pg)
    return new_pg


def get_recent_ripples(db: Session, limit: int = 10):
    """
    Fetch the most recent ripple/ping events for dashboard visualization.
    """
    from db.models import PingDB
    return db.query(PingDB).order_by(PingDB.date_detected.desc()).limit(limit).all()
