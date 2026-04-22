# routes/research_results_router.py

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from AINDY.core.execution_gate import to_envelope
from AINDY.core.execution_helper import execute_with_pipeline_sync
from AINDY.db.database import get_db
from AINDY.platform_layer.rate_limiter import limiter
from apps.search.schemas.research_results_schema import ResearchResultCreate
from apps.search.services.search_service import build_learning_context, unified_query
from apps.search.services import research_results_service
from apps.search.services.research_engine import ai_analyze, web_search
from AINDY.services.auth_service import get_current_user

router = APIRouter(prefix="/research", tags=["Research"], dependencies=[Depends(get_current_user)])
search_history_router = APIRouter(prefix="/search", tags=["Search History"], dependencies=[Depends(get_current_user)])
logger = logging.getLogger(__name__)


def _run_flow_research(flow_name: str, payload: dict, db: Session, user_id: str):
    from AINDY.runtime.flow_engine import run_flow
    result = run_flow(flow_name, payload, db=db, user_id=user_id)
    if result.get("status") == "FAILED":
        error = result.get("error", "")
        if error.startswith("HTTP_"):
            parts = error.split(":", 1)
            code = int(parts[0].replace("HTTP_", ""))
            msg = parts[1] if len(parts) > 1 else error
            raise HTTPException(status_code=code, detail=msg)
        raise HTTPException(status_code=500, detail=error or f"{flow_name} failed")
    return result.get("data")


def _execute_research(request: Request, route_name: str, handler, *, db: Session, user_id: str,
                      input_payload=None, success_status_code: int = 200):
    result = execute_with_pipeline_sync(
        request=request,
        route_name=route_name,
        handler=handler,
        user_id=user_id,
        input_payload=input_payload or {},
        metadata={"db": db, "source": "research"},
        success_status_code=success_status_code,
        return_result=True,
    )
    if not result.success:
        detail = result.metadata.get("detail") or result.error or "Execution failed"
        raise HTTPException(
            status_code=int(result.metadata.get("status_code", 500)),
            detail=detail,
        )
    data = result.data
    if isinstance(data, dict):
        data = dict(data)
        data.setdefault(
            "execution_envelope",
            to_envelope(
                eu_id=result.metadata.get("eu_id"),
                trace_id=result.metadata.get("trace_id"),
                status="SUCCESS",
                output=None,
                error=None,
                duration_ms=None,
                attempt_count=1,
            ),
        )
    return data


def _do_create_result(db: Session, result: ResearchResultCreate, user_id: str):
    data = _run_flow_research("research_create", {"result": result.model_dump()}, db, user_id)
    return data.get("data") if isinstance(data, dict) and "data" in data else data


def _do_run_research_query(db: Session, request: ResearchResultCreate, user_id: str):
    data = _run_flow_research(
        "research_query",
        {"query": request.query, "summary": request.summary or ""},
        db,
        user_id,
    )
    return data.get("data") if isinstance(data, dict) and "data" in data else data


def _do_delete_search_history_detail(db: Session, history_id: str, user_id: str):
    return _run_flow_research("search_history_delete", {"history_id": history_id}, db, user_id)


@router.post("/")
@limiter.limit("30/minute")
def create_result(
    request: Request,
    result: ResearchResultCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])
    def handler(_ctx):
        return _do_create_result(db, result, user_id)
    return _execute_research(
        request,
        "research.create",
        handler,
        db=db,
        user_id=user_id,
        input_payload=result.model_dump(),
        success_status_code=201,
    )


@router.get("/")
@limiter.limit("60/minute")
def list_results(
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])
    def handler(_ctx):
        return _run_flow_research("research_list", {}, db, user_id)
    return _execute_research(request, "research.list", handler, db=db, user_id=user_id)


@router.post("/query")
@limiter.limit("30/minute")
def run_research_query(
    request: ResearchResultCreate,
    http_request: Request = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])
    if http_request is None:
        unified = unified_query(
            request.query,
            db=db,
            user_id=user_id,
            web_search_fn=web_search,
            ai_analyze_fn=ai_analyze,
        )
        raw = unified.get("raw_excerpt") or ""
        summary = unified.get("summary") or request.summary or ""
        record = research_results_service.create_research_result(
            db=db,
            result=ResearchResultCreate(query=request.query, summary=summary),
            user_id=user_id,
            data={"raw_content": raw},
            source=unified.get("source") or "web_search",
        )
        return {
            "id": getattr(record, "id", None),
            "query": record.query,
            "summary": record.summary,
            "source": getattr(record, "source", "web_search"),
            "data": getattr(record, "data", None),
            "search_score": unified.get("search_score") or 1.0,
            "learning_context": unified.get("learning_context")
            or build_learning_context(unified, default_search_type="research"),
            "created_at": record.created_at.isoformat() if getattr(record, "created_at", None) else None,
        }

    def handler(_ctx):
        return _do_run_research_query(db, request, user_id)
    return _execute_research(
        http_request,
        "research.query",
        handler,
        db=db,
        user_id=user_id,
        input_payload=request.model_dump(),
    )


@search_history_router.get("/history")
def list_search_history(
    request: Request,
    limit: int = 25,
    search_type: str | None = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])
    def handler(_ctx):
        return _run_flow_research(
            "search_history_list",
            {"limit": limit, "search_type": search_type},
            db, user_id,
        )
    return _execute_research(request, "search.history.list", handler, db=db, user_id=user_id,
                             input_payload={"search_type": search_type})


@search_history_router.get("/history/{history_id}")
def get_search_history_detail(
    request: Request,
    history_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])
    def handler(_ctx):
        return _run_flow_research("search_history_get", {"history_id": history_id}, db, user_id)
    return _execute_research(request, "search.history.detail", handler, db=db, user_id=user_id,
                             input_payload={"history_id": history_id})


@search_history_router.delete("/history/{history_id}")
def delete_search_history_detail(
    request: Request,
    history_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])
    def handler(_ctx):
        return _do_delete_search_history_detail(db, history_id, user_id)
    return _execute_research(
        request,
        "search.history.delete",
        handler,
        db=db,
        user_id=user_id,
        input_payload={"history_id": history_id},
    )

