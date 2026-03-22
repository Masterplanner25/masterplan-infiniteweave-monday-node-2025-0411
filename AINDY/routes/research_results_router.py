# routers/research_results_router.py
from fastapi import APIRouter, Depends
import logging
from sqlalchemy.orm import Session
from db.database import get_db
from schemas.research_results_schema import ResearchResultCreate, ResearchResultResponse
from services import research_results_service
from db.dao.memory_node_dao import MemoryNodeDAO
from runtime.memory import MemoryOrchestrator
from modules.research_engine import web_search, ai_analyze
from services.search_scoring import score_research_result
from services.auth_service import get_current_user

router = APIRouter(prefix="/research", tags=["Research"], dependencies=[Depends(get_current_user)])
logger = logging.getLogger(__name__)

@router.post("/", response_model=ResearchResultResponse)
def create_result(
    result: ResearchResultCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Create and store a new research result owned by the current user.
    """
    return research_results_service.create_research_result(
        db, result, user_id=str(current_user["sub"])
    )

@router.get("/", response_model=list[ResearchResultResponse])
def list_results(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Retrieve all research results belonging to the current user.
    """
    return research_results_service.get_all_research_results(
        db, user_id=str(current_user["sub"])
    )

@router.post("/query", response_model=ResearchResultResponse)
def run_research_query(
    request: ResearchResultCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Accepts a research query, stores it, and triggers MemoryBridge logging.
    """
    logger.info("Running research for query: %s", request.query)
    context = None
    try:
        orchestrator = MemoryOrchestrator(MemoryNodeDAO)
        context = orchestrator.get_context(
            user_id=str(current_user["sub"]),
            query=request.query,
            task_type="analysis",
            db=db,
            max_tokens=400,
            metadata={
                "tags": ["research", "insight"],
                "node_type": "insight",
                "limit": 3,
            },
        )
    except Exception:
        context = None

    summary = request.summary
    source = None
    raw_excerpt = None
    try:
        raw = web_search(request.query)
        raw_excerpt = (raw or "")[:2000]
        summary = ai_analyze(raw)
        source = "external_search"
    except Exception:
        summary = request.summary

    data = None
    if context and context.items:
        data = {
            "memory_context_ids": context.ids,
            "memory_context": context.formatted,
        }
    memory_context_count = len(context.items) if context else 0
    search_score = score_research_result(
        summary=summary or "",
        memory_context_count=memory_context_count,
    )
    data = data or {}
    data.update({
        "search_score": search_score,
        "raw_excerpt": raw_excerpt,
        "source": source,
    })

    result = research_results_service.create_research_result(
        db,
        ResearchResultCreate(query=request.query, summary=summary),
        user_id=str(current_user["sub"]),
        data=data,
        source=source or "research_query",
    )
    search_score = None
    result_data = getattr(result, "data", None)
    if isinstance(result_data, dict):
        search_score = result_data.get("search_score")
    return {
        "id": result.id,
        "query": result.query,
        "summary": result.summary,
        "source": result.source,
        "data": result_data,
        "created_at": result.created_at,
        "search_score": search_score,
    }
