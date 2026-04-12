from datetime import datetime

from sqlalchemy import Column, String, Text, Float, DateTime
from AINDY.db.database import Base


class PlaybookDB(Base):
    __tablename__ = "playbooks"

    id = Column(String, primary_key=True)
    strategy_id = Column(String, index=True)

    title = Column(String)
    steps = Column(Text)
    template = Column(Text, nullable=True)

    success_rate = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)
