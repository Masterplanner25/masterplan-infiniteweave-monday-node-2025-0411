"""
LEAD GENERATION ROUTER
------------------------------------
Endpoint Layer for: B2B Lead Generation via AI Search Optimization
Purpose: Exposes API routes to trigger A.I.N.D.Y.'s autonomous
lead discovery and scoring engine.
"""

from __future__ import annotations

import logging
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from db.database import get_db
from schemas.leadgen_schema import LeadGenItem
from services import leadgen_service
from services.auth_service import get_current_user
from services.execution_service import ExecutionContext, ExecutionErrorConfig, run_execution
from services.rate_limiter import limiter
from services.search_service import get_cached_search_result, persist_search_result, search_leads

router = APIRouter(prefix="/leadgen", tags=["Lead Generation"])
logger = logging.getLogger(__name__)


@router.post("/")
@limiter.limit("10/minute")
def generate_b2b_leads(
    request: Request,
    query: str = Query(..., description="Search intent or keyword for AI lead discovery"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    start = time.perf_counter()
    user_id = str(current_user["sub"])
    def _generate() -> dict:
        cached = get_cached_search_result(
            db=db,
            user_id=user_id,
            query=query,
            search_type="leadgen",
        )
        if cached:
            cached_results = cached.get("results") or []
            return {
                "query": query,
                "count": len(cached_results),
                "results": [LeadGenItem(**row).model_dump() for row in cached_results],
                "_execution_meta": {"cached": True, "count": len(cached_results)},
            }

        results = leadgen_service.create_lead_results(db, query, user_id=user_id)
        formatted = [
            {
                "company": r.company,
                "url": r.url,
                "fit_score": r.fit_score,
                "intent_score": r.intent_score,
                "data_quality_score": r.data_quality_score,
                "overall_score": r.overall_score,
                "reasoning": r.reasoning,
                "search_score": search_score,
                "created_at": r.created_at,
            }
            for r, search_score in results
        ]
        cached_payload = persist_search_result(
            db=db,
            user_id=user_id,
            query=query,
            result={
                "query": query,
                "count": len(formatted),
                "results": formatted,
            },
            search_type="leadgen",
        )
        duration_ms = (time.perf_counter() - start) * 1000
        logger.info("LeadGen generated %s results in %.2fms", len(formatted), duration_ms)
        return {
            "query": query,
            "count": len(formatted),
            "results": [LeadGenItem(**row).model_dump() for row in (cached_payload.get("results") or formatted)],
            "_execution_meta": {
                "count": len(formatted),
                "duration_ms": round(duration_ms, 2),
            },
        }

    return run_execution(
        ExecutionContext(
            db=db,
            user_id=user_id,
            source="leadgen",
            operation="leadgen.generate",
            start_payload={"query": query},
        ),
        _generate,
        completed_payload_builder=lambda result: {"query": query, **(result.pop("_execution_meta", {}))},
        handled_exceptions={
            Exception: ExecutionErrorConfig(status_code=500, message="Lead generation failed"),
        },
    )


@router.get("/search")
def preview_lead_search(
    query: str = Query(..., description="Search intent or keyword for AI lead discovery"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])
    return run_execution(
        ExecutionContext(
            db=db,
            user_id=user_id,
            source="leadgen",
            operation="leadgen.search",
            start_payload={"query": query},
        ),
        lambda: search_leads(query, db=db, user_id=user_id),
        completed_payload_builder=lambda payload: {"query": query, "count": len(payload.get("results") or [])},
        handled_exceptions={
            Exception: ExecutionErrorConfig(status_code=500, message="Lead search failed"),
        },
    )


@router.get("/")
def list_all_leads(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    start = time.perf_counter()
    user_id = str(current_user["sub"])
    from db.models.leadgen_model import LeadGenResult

    def _list_results() -> list[dict]:
        all_results = (
            db.query(LeadGenResult)
            .filter(LeadGenResult.user_id == uuid.UUID(user_id))
            .order_by(LeadGenResult.created_at.desc())
            .all()
        )
        duration_ms = (time.perf_counter() - start) * 1000
        logger.info("LeadGen list returned %s results in %.2fms", len(all_results), duration_ms)
        return [
            LeadGenItem(
                company=r.company,
                url=r.url,
                fit_score=r.fit_score,
                intent_score=r.intent_score,
                data_quality_score=r.data_quality_score,
                overall_score=r.overall_score,
                reasoning=r.reasoning,
                created_at=r.created_at,
            ).model_dump()
            for r in all_results
        ]

    return run_execution(
        ExecutionContext(db=db, user_id=user_id, source="leadgen", operation="leadgen.list"),
        _list_results,
        completed_payload_builder=lambda results: {
            "count": len(results),
            "duration_ms": round((time.perf_counter() - start) * 1000, 2),
        },
        handled_exceptions={
            Exception: ExecutionErrorConfig(status_code=500, message="Failed to load leads"),
        },
    )
