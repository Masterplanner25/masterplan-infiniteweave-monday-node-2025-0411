from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from base import Base  # <- from your clean base.py

DATABASE_URL = "postgresql://postgres:140671@localhost:5432/base"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


