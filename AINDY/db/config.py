# db/config.py

from db.database import DATABASE_URL, Base, SessionLocal

# --- Add this function for FastAPI dependency injection ---
def get_db():
    """Yield a database session for FastAPI routes."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
