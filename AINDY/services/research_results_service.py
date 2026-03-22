# /services/research_results_service.py
import logging
import uuid
from sqlalchemy.orm import Session
from services.memory_capture_engine import MemoryCaptureEngine
from db.models.research_results import ResearchResult
from schemas.research_results_schema import ResearchResultCreate

logger = logging.getLogger(__name__)

def log_to_memory_bridge(query: str, summary: str, db: Session, user_id: str | None):
    """
    Logs research results into A.I.N.D.Y.'s symbolic Memory Bridge layer.
    Persists a MemoryNode via the capture engine.
    """
    try:
        engine = MemoryCaptureEngine(
            db=db,
            user_id=str(user_id) if user_id else None,
            agent_namespace="research",
        )
        engine.evaluate_and_capture(
            event_type="research_result",
            content=f"Research: {query} | {summary}",
            source="research_engine",
            tags=["research", "insight"],
            node_type="insight",
        )
        logger.info("[MemoryBridge] Logged node for query: %s", query)
    except Exception as e:
        logger.warning("[MemoryBridge] Logging failed: %s", e)


def create_research_result(
    db: Session,
    result: ResearchResultCreate,
    user_id: str = None,
    data: dict | None = None,
    source: str | None = None,
):
    """Store a new research result and propagate to the symbolic bridge."""
    payload = result.dict()
    if data:
        payload["data"] = data
    if source:
        payload["source"] = source
    user_uuid = uuid.UUID(str(user_id)) if user_id else None
    db_item = ResearchResult(**payload, user_id=user_uuid)
    db.add(db_item)
    db.commit()
    db.refresh(db_item)

    # Log to bridge
    log_to_memory_bridge(db_item.query, db_item.summary, db=db, user_id=user_id)
    return db_item


def get_all_research_results(db: Session, user_id: str = None):
    """Retrieve all stored research results ordered by creation date."""
    q = db.query(ResearchResult)
    if user_id:
        q = q.filter(ResearchResult.user_id == uuid.UUID(str(user_id)))
    return q.order_by(ResearchResult.created_at.desc()).all()

