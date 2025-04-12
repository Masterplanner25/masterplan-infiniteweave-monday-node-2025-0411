from config import engine
from base import Base
import main
import models

Base.metadata.create_all(bind=engine)

print("✅ All tables created directly via SQLAlchemy.")
