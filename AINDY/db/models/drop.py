from sqlalchemy import Column, String, DateTime, Text, ForeignKey
from db.database import Base


class DropPointDB(Base):
    __tablename__ = "drop_points"
    id = Column(String, primary_key=True, index=True)
    title = Column(String)
    platform = Column(String)
    url = Column(String, nullable=True)
    date_dropped = Column(DateTime)
    core_themes = Column(Text)
    tagged_entities = Column(Text)
    intent = Column(String)

class PingDB(Base):
    __tablename__ = "pings"
    id = Column(String, primary_key=True, index=True)
    drop_point_id = Column(String, ForeignKey("drop_points.id"))
    ping_type = Column(String)
    source_platform = Column(String)
    date_detected = Column(DateTime)
    connection_summary = Column(Text, nullable=True)
    external_url = Column(String, nullable=True)
    reaction_notes = Column(Text, nullable=True)