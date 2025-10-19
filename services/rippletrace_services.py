# /services/rippletrace_services.py
from sqlalchemy.orm import Session
from models import DropPointDB, PingDB
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
    db.commit()
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
    db.commit()
    db.refresh(db_pg)
    return db_pg

def get_ripples(db: Session, drop_point_id: str):
    return db.query(PingDB).filter(PingDB.drop_point_id == drop_point_id).all()

def get_all_drop_points(db: Session):
    return db.query(DropPointDB).all()

def get_all_pings(db: Session):
    return db.query(PingDB).all()
