"""
LEAD GENERATION ROUTER
------------------------------------
Endpoint Layer for: B2B Lead Generation via AI Search Optimization
Purpose: Exposes API routes to trigger A.I.N.D.Y.'s autonomous
lead discovery and scoring engine.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from core.execution_helper import execute_with_pipeline_sync
from db.database import get_db
from schemas.leadgen_schema import LeadGenItem
from services.auth_service import get_current_user
from services.rate_limiter import limiter
from services.search_service import get_cached_search_result

router = APIRouter(prefix="/leadgen", tags=["Lead Generation"])
logger = logging.getLogger(__name__)


def _execute_leadgen(request: Request, route_name: str, handler, *, db: Session, user_id: str, input_payload=None):
    return execute_with_pipeline_sync(
        request=request,
        route_name=route_name,
        handler=handler,
        user_id=user_id,
        input_payload=input_payload,
        metadata={"db": db, "source": "leadgen"},
    )


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

    def handler(_ctx):
        # Fast path: return cached results without running the flow
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

        from services.flow_engine import run_flow
        result = run_flow(
            "leadgen_search",
            {"query": query},
            db=db,
            user_id=user_id,
        )
        if result.get("status") == "error":
            raise RuntimeError(
                (result.get("data") or {}).get("message", "LeadGen flow failed")
            )

        # result["data"] = serialized list from leadgen_search_node
        search_results = result.get("data") or []
        duration_ms = (time.perf_counter() - start) * 1000
        logger.info("LeadGen generated %s results in %.2fms", len(search_results), duration_ms)
        results_payload = [LeadGenItem(**item).model_dump() for item in search_results]
        return {
            "query": query,
            "count": len(search_results),
            "results": results_payload,
            "_execution_meta": {
                "count": len(search_results),
                "duration_ms": round(duration_ms, 2),
            },
        }

    return _execute_leadgen(request, "leadgen.generate", handler, db=db, user_id=user_id, input_payload={"query": query})


@router.get("/search")
def preview_lead_search(
    request: Request,
    query: str = Query(..., description="Search intent or keyword for AI lead discovery"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])
    def handler(_ctx):
        from services.flow_engine import run_flow
        result = run_flow("leadgen_preview_search", {"query": query}, db=db, user_id=user_id)
        if result.get("status") == "error":
            raise RuntimeError((result.get("data") or {}).get("message", "Lead search failed"))
        return result.get("data")
    return _execute_leadgen(request, "leadgen.search", handler, db=db, user_id=user_id, input_payload={"query": query})


@router.get("/")
def list_all_leads(
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])

    def handler(_ctx):
        from services.flow_engine import run_flow
        result = run_flow("leadgen_list", {}, db=db, user_id=user_id)
        if result.get("status") == "error":
            raise RuntimeError((result.get("data") or {}).get("message", "Failed to load leads"))
        return result.get("data")

    return _execute_leadgen(request, "leadgen.list", handler, db=db, user_id=user_id)
