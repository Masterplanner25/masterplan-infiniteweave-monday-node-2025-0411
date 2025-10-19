# smoke_memory.py
import sys
from pathlib import Path
import uuid
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# ensure project root is importable regardless of cwd
PROJECT_ROOT = Path(__file__).resolve().parents[0]  # project root (file lives in project root)
sys.path.insert(0, str(PROJECT_ROOT))

from base import Base
from memory_persistence import MemoryNodeDAO, MemoryNodeModel

# NOTE: set DATABASE_URL here or via the env var DATABASE_URL
DATABASE_URL = "postgresql+psycopg2://postgres:140671aA%40@localhost:5433/base"

engine = create_engine(DATABASE_URL, echo=False, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def main():
    db = SessionLocal()
    try:
        # fake in-memory node-like object
        class PseudoNode:
            def __init__(self):
                self.id = str(uuid.uuid4())
                self.content = "Hello memory bridge"
                self.tags = ["demo", "bridge"]
                self.node_type = "note"
                self.extra = {"source": "smoke-test"}

        dao = MemoryNodeDAO(db)
        saved = dao.save_memory_node(PseudoNode())
        print("Saved:", saved.id)

        # load and print safely (handles dict or object)
        loaded = dao.load_memory_node(str(saved.id))
        if isinstance(loaded, dict):
            print("Loaded:", loaded.get("content", "<no content>"), loaded.get("tags", []))
        else:
            print("Loaded:", getattr(loaded, "content", "<no content>"), getattr(loaded, "tags", []))

        # create a self link test on purpose (should fail)
        try:
            dao.create_link(str(saved.id), str(saved.id))
            print("Self-link test FAILED (should have been prevented)")
        except Exception as e:
            print("Self-link prevented OK:", e)

    finally:
        db.close()


if __name__ == "__main__":
    main()
