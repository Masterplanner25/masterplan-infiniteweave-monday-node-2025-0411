"""
LEAD GENERATION ROUTER
------------------------------------
Endpoint Layer for: B2B Lead Generation via AI Search Optimization
Purpose: Exposes API routes to trigger A.I.N.D.Y.’s autonomous
lead discovery and scoring engine.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from db.database import get_db
from services import leadgen_service

router = APIRouter(prefix="/leadgen", tags=["Lead Generation"])

@router.post("/")
def generate_b2b_leads(
    query: str = Query(..., description="Search intent or keyword for AI lead discovery"),
    db: Session = Depends(get_db)
):
    """
    Executes the A.I.N.D.Y. Lead Generation module.
    Example: POST /leadgen?query=companies hiring AI consultants
    """
    results = leadgen_service.create_lead_results(db, query)
    formatted = [
        {
            "company": r.company,
            "url": r.url,
            "fit_score": r.fit_score,
            "intent_score": r.intent_score,
            "data_quality_score": r.data_quality_score,
            "overall_score": r.overall_score,
            "reasoning": r.reasoning,
            "created_at": r.created_at
        }
        for r in results
    ]
    return {"query": query, "count": len(formatted), "results": formatted}


@router.get("/")
def list_all_leads(db: Session = Depends(get_db)):
    """
    Retrieve all stored lead generation results.
    """
    from db.models.leadgen_model import LeadGenResult
    all_results = db.query(LeadGenResult).order_by(LeadGenResult.created_at.desc()).all()
    return [
        {
            "company": r.company,
            "url": r.url,
            "fit_score": r.fit_score,
            "intent_score": r.intent_score,
            "overall_score": r.overall_score,
            "reasoning": r.reasoning,
            "created_at": r.created_at
        }
        for r in all_results
    ]
