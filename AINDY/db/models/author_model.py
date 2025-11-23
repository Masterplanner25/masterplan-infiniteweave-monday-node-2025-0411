# /db/models/author_model.py
from sqlalchemy import Column, String, DateTime, Text
from datetime import datetime
from db.database import Base

class AuthorDB(Base):
    __tablename__ = "authors"

    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    platform = Column(String, nullable=False)
    notes = Column(Text, nullable=True)
    joined_at = Column(DateTime, default=datetime.utcnow)
    last_seen = Column(DateTime, default=datetime.utcnow)
