"""
LEAD GENERATION ROUTER
------------------------------------
Endpoint Layer for: B2B Lead Generation via AI Search Optimization
Purpose: Exposes API routes to trigger A.I.N.D.Y.'s autonomous
lead discovery and scoring engine.
"""

import logging
import time

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from AINDY.core.execution_gate import to_envelope
from AINDY.core.execution_helper import execute_with_pipeline_sync
from AINDY.db.database import get_db
from apps.search.schemas.leadgen_schema import LeadGenItem
from AINDY.services.auth_service import get_current_user
from AINDY.platform_layer.rate_limiter import limiter
from apps.search.services.search_service import build_learning_context, get_cached_search_result

router = APIRouter(prefix="/leadgen", tags=["Lead Generation"])
legacy_router = APIRouter(tags=["Lead Generation"])
logger = logging.getLogger(__name__)


def _execute_leadgen(request: Request, route_name: str, handler, *, db: Session, user_id: str, input_payload=None):
    result = execute_with_pipeline_sync(
        request=request,
        route_name=route_name,
        handler=handler,
        user_id=user_id,
        input_payload=input_payload or {},
        metadata={"db": db, "source": "leadgen"},
        return_result=True,
    )
    if not result.success:
        detail = result.metadata.get("detail") or result.error or "Execution failed"
        raise HTTPException(
            status_code=int(result.metadata.get("status_code", 500)),
            detail=detail,
        )
    eu_id = result.metadata.get("eu_id")
    if eu_id is None:
        raise HTTPException(status_code=500, detail="Execution pipeline did not attach eu_id")
    data = result.data
    if isinstance(data, dict):
        data = dict(data)
        data.setdefault(
            "execution_envelope",
            to_envelope(
                eu_id=eu_id,
                trace_id=result.metadata.get("trace_id"),
                status="SUCCESS",
                output=None,
                error=None,
                duration_ms=None,
                attempt_count=1,
            ),
        )
    return data


def _do_generate_b2b_leads(db: Session, user_id: str, query: str):
    start = time.perf_counter()

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
            "learning_context": cached.get("learning_context")
            or build_learning_context(cached, default_search_type="leadgen"),
            "_execution_meta": {"cached": True, "count": len(cached_results)},
        }

    from AINDY.runtime.flow_engine import run_flow

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


@router.post("/")
@limiter.limit("10/minute")
def generate_b2b_leads(
    request: Request,
    query: str = Query(..., description="Search intent or keyword for AI lead discovery"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])
    def handler(_ctx):
        return _do_generate_b2b_leads(db, user_id, query)
    return _execute_leadgen(
        request,
        "leadgen.generate",
        handler,
        db=db,
        user_id=user_id,
        input_payload={"query": query},
    )


@router.get("/search")
@limiter.limit("60/minute")
def preview_lead_search(
    request: Request,
    query: str = Query(..., description="Search intent or keyword for AI lead discovery"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])
    def handler(_ctx):
        from apps.search.services.search_service import search_leads
        return search_leads(query=query, db=db, user_id=user_id)
    return _execute_leadgen(request, "leadgen.search", handler, db=db, user_id=user_id, input_payload={"query": query})


@router.get("/")
@limiter.limit("60/minute")
def list_all_leads(
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])

    def handler(_ctx):
        from apps.search.services.leadgen_service import list_leads
        return list_leads(db, user_id=user_id)

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


