from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from db.database import get_db
from services import research_results_service
from db.models.research_results_schema import ResearchResultCreate, ResearchResultResponse
from services import research_results_service

router = APIRouter(prefix="/research", tags=["Research"])

@router.post("/", response_model=ResearchResultResponse)
def create_result(result: ResearchResultCreate, db: Session = Depends(get_db)):
    return research_results_service.create_research_result(db, result)

@router.get("/", response_model=list[ResearchResultResponse])
def list_results(db: Session = Depends(get_db)):
    return research_results_service.get_all_research_results(db)

@router.post("/query")
def run_research_query(request: ResearchResultCreate, db: Session = Depends(get_db)):
    """
    Accepts a research query, stores it, and triggers MemoryBridge logging.
    """
    # Here you could integrate actual AI summarization later.
    print(f"🧠 Running research for query: {request.query}")

    result = create_research_result(db, request)
    return {
        "id": result.id,
        "query": result.query,
        "summary": result.summary,
        "created_at": result.created_at
    }