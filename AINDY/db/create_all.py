from AINDY.config import engine
from AINDY.db.database import Base
import AINDY.main
import models

Base.metadata.create_all(bind=engine)

print("✅ All tables created directly via SQLAlchemy.")
