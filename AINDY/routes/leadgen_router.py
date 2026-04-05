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

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from core.execution_service import ExecutionContext
from core.execution_service import run_execution
from db.database import get_db
from db.models.leadgen_model import LeadGenResult
from schemas.leadgen_schema import LeadGenItem
from services.auth_service import get_current_user
from platform_layer.rate_limiter import limiter
from domain.search_service import get_cached_search_result, search_leads

router = APIRouter(prefix="/leadgen", tags=["Lead Generation"])
legacy_router = APIRouter(tags=["Lead Generation"])
logger = logging.getLogger(__name__)


def _execute_leadgen(request: Request, route_name: str, handler, *, db: Session, user_id: str, input_payload=None):
    result = run_execution(
        ExecutionContext(
            db=db,
            user_id=user_id,
            source="leadgen",
            operation=route_name,
            start_payload=input_payload or {},
        ),
        lambda: handler(None),
    )
    if isinstance(result, dict) and "data" in result and str(result.get("status", "")).upper() == "SUCCESS":
        return result["data"]
    return result


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

        from runtime.flow_engine import run_flow
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
        return search_leads(query=query, db=db, user_id=user_id)
    return _execute_leadgen(request, "leadgen.search", handler, db=db, user_id=user_id, input_payload={"query": query})


@router.get("/")
def list_all_leads(
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])

    def handler(_ctx):
        rows = (
            db.query(LeadGenResult)
            .filter(LeadGenResult.user_id == current_user["sub"])
            .order_by(LeadGenResult.created_at.desc(), LeadGenResult.id.desc())
            .all()
        )
        return [
            {
                "id": row.id,
                "query": row.query,
                "company": row.company,
                "url": row.url,
                "context": row.context,
                "fit_score": row.fit_score,
                "intent_score": row.intent_score,
                "search_score": row.overall_score,
                "reasoning": row.reasoning,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ]

    return _execute_leadgen(request, "leadgen.list", handler, db=db, user_id=user_id)


for _route in list(router.routes):
    _path = getattr(_route, "path", None)
    if not _path or not _path.startswith("/leadgen"):
        continue
    legacy_router.add_api_route(
        _path.removeprefix("/leadgen") or "/",
        _route.endpoint,
        methods=list(_route.methods or []),
        name=f"legacy_{_route.name}",
        include_in_schema=False,
    )


