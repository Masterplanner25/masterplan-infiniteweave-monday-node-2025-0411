# config.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from base import Base

DATABASE_URL = "postgresql://postgres:Yourpasswordhere@localhost:5433/base"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Add this:
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


