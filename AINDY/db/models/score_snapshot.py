from sqlalchemy import Column, String, DateTime, Float
from db.database import Base


class ScoreSnapshotDB(Base):
    __tablename__ = "score_snapshots"

    id = Column(String, primary_key=True, index=True)
    drop_point_id = Column(String, index=True)
    timestamp = Column(DateTime, index=True)

    narrative_score = Column(Float)
    velocity_score = Column(Float)
    spread_score = Column(Float)
