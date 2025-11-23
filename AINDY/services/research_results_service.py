# /services/research_results_service.py
from sqlalchemy.orm import Session
from bridge.bridge import create_memory_node, MemoryNode, MemoryTrace
from db.models.research_results import ResearchResult
from db.models.research_results_schema import ResearchResultCreate

# Singleton memory trace for runtime continuity
_memory_trace = None


def get_runtime_trace():
    """Return a global runtime trace; initialize if missing."""
    global _memory_trace
    if _memory_trace is None:
        _memory_trace = MemoryTrace()
    return _memory_trace


def log_to_memory_bridge(query: str, summary: str):
    """
    Logs research results into A.I.N.D.Y.'s symbolic Memory Bridge layer.
    Creates a MemoryNode and links it to the active runtime trace.
    """
    try:
        trace = get_runtime_trace()
        node = MemoryNode(
            content=f"Research Summary for '{query}': {summary}",
            source="Research Engine",
            tags=["research", "insight", "bridge"],
        )
        trace.add_node(node)

        # Persist lightweight DB representation
        create_memory_node(
            title=f"Research: {query}",
            content=summary,
            tags=["research", "insight"],
        )

        print(f"[MemoryBridge] Logged node for query: {query}")
    except Exception as e:
        print(f"[MemoryBridge] Logging failed: {e}")


def create_research_result(db: Session, result: ResearchResultCreate):
    """Store a new research result and propagate to the symbolic bridge."""
    db_item = ResearchResult(**result.dict())
    db.add(db_item)
    db.commit()
    db.refresh(db_item)

    # Log to bridge
    log_to_memory_bridge(db_item.query, db_item.summary)
    return db_item


def get_all_research_results(db: Session):
    """Retrieve all stored research results ordered by creation date."""
    return db.query(ResearchResult).order_by(ResearchResult.created_at.desc()).all()

