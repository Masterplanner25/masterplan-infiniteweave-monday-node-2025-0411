# routers/research_results_router.py
from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from db.dao.memory_node_dao import MemoryNodeDAO
from db.database import get_db
from runtime.memory import MemoryOrchestrator
from schemas.research_results_schema import ResearchResultCreate
from services import research_results_service
from services.auth_service import get_current_user
from services.execution_service import ExecutionContext, ExecutionErrorConfig, run_execution
from services.search_service import (
    delete_search_history_item,
    get_search_history,
    get_search_history_item,
    unified_query,
)

router = APIRouter(prefix="/research", tags=["Research"], dependencies=[Depends(get_current_user)])
search_history_router = APIRouter(prefix="/search", tags=["Search History"], dependencies=[Depends(get_current_user)])
logger = logging.getLogger(__name__)


def _result_payload(result) -> dict:
    result_data = getattr(result, "data", None)
    search_score = result_data.get("search_score") if isinstance(result_data, dict) else None
    return {
        "id": result.id,
        "query": result.query,
        "summary": result.summary,
        "source": result.source,
        "data": result_data,
        "created_at": result.created_at.isoformat() if getattr(result, "created_at", None) else None,
        "search_score": search_score,
    }


@router.post("/")
def create_result(
    result: ResearchResultCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])
    return run_execution(
        ExecutionContext(db=db, user_id=user_id, source="research", operation="research.create"),
        lambda: _result_payload(research_results_service.create_research_result(db, result, user_id=user_id)),
        success_status_code=201,
        completed_payload_builder=lambda created: {"research_id": created["id"]},
        handled_exceptions={
            Exception: ExecutionErrorConfig(status_code=500, message="Failed to create research result"),
        },
    )


@router.get("/")
def list_results(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])
    return run_execution(
        ExecutionContext(db=db, user_id=user_id, source="research", operation="research.list"),
        lambda: [_result_payload(item) for item in research_results_service.get_all_research_results(db, user_id=user_id)],
        completed_payload_builder=lambda items: {"count": len(items)},
        handled_exceptions={
            Exception: ExecutionErrorConfig(status_code=500, message="Failed to load research results"),
        },
    )


@router.post("/query")
def run_research_query(
    request: ResearchResultCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])
    def _run_query() -> dict:
        start = time.perf_counter()
        logger.info("Running research for query: %s", request.query)
        context = None
        try:
            orchestrator = MemoryOrchestrator(MemoryNodeDAO)
            context = orchestrator.get_context(
                user_id=user_id,
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
        unified = unified_query(request.query, db=db, user_id=user_id)
        if unified.get("summary"):
            summary = unified["summary"]
        source = unified.get("source")
        raw_excerpt = unified.get("raw_excerpt")

        data = None
        if context and context.items:
            data = {
                "memory_context_ids": context.ids,
                "memory_context": context.formatted,
            }
        memory_context_count = len(context.items) if context else 0
        search_score = unified.get("search_score") or 0.0
        data = data or {}
        data.update(
            {
                "search_score": search_score,
                "raw_excerpt": raw_excerpt,
                "source": source,
                "memory_context_count": memory_context_count,
            }
        )
        result = research_results_service.create_research_result(
            db,
            ResearchResultCreate(query=request.query, summary=summary),
            user_id=user_id,
            data=data,
            source=source or "research_query",
        )
        duration_ms = (time.perf_counter() - start) * 1000
        logger.info("Research query completed in %.2fms", duration_ms)
        payload = _result_payload(result)
        payload["_execution_meta"] = {
            "research_id": str(result.id),
            "duration_ms": round(duration_ms, 2),
            "search_score": search_score,
        }
        return payload

    return run_execution(
        ExecutionContext(
            db=db,
            user_id=user_id,
            source="research",
            operation="research.query",
            start_payload={"query": request.query},
        ),
        _run_query,
        completed_payload_builder=lambda result: result.pop("_execution_meta", None),
        handled_exceptions={
            Exception: ExecutionErrorConfig(status_code=500, message="Research query failed"),
        },
    )


def _history_to_dict(item):
    payload = dict(item.result or {})
    return {
        "id": item.id,
        "query": item.query,
        "result": payload,
        "search_type": payload.get("search_type"),
        "created_at": item.created_at.isoformat() if getattr(item, "created_at", None) else None,
    }


@search_history_router.get("/history")
def list_search_history(
    limit: int = 25,
    search_type: str | None = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])
    return run_execution(
        ExecutionContext(
            db=db,
            user_id=user_id,
            source="search_history",
            operation="search.history.list",
            start_payload={"search_type": search_type},
        ),
        lambda: {
            "count": len(items := get_search_history(db, user_id, limit=limit, search_type=search_type)),
            "items": [_history_to_dict(item) for item in items],
        },
        completed_payload_builder=lambda result: {"count": result["count"]},
    )


@search_history_router.get("/history/{history_id}")
def get_search_history_detail(
    history_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])
    return run_execution(
        ExecutionContext(
            db=db,
            user_id=user_id,
            source="search_history",
            operation="search.history.detail",
            start_payload={"history_id": history_id},
        ),
        lambda: _history_to_dict(_require_history_item(db, user_id, history_id)),
        completed_payload_builder=lambda result: {"history_id": result["id"]},
        handled_exceptions={
            LookupError: ExecutionErrorConfig(status_code=404, message="Search history item not found"),
        },
    )


@search_history_router.delete("/history/{history_id}")
def delete_search_history_detail(
    history_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["sub"])
    return run_execution(
        ExecutionContext(
            db=db,
            user_id=user_id,
            source="search_history",
            operation="search.history.delete",
            start_payload={"history_id": history_id},
        ),
        lambda: _delete_history_item(db, user_id, history_id),
        completed_payload_builder=lambda result: {"history_id": result["id"]},
        handled_exceptions={
            LookupError: ExecutionErrorConfig(status_code=404, message="Search history item not found"),
        },
    )


def _require_history_item(db: Session, user_id: str, history_id: str):
    item = get_search_history_item(db, user_id, history_id)
    if not item:
        raise LookupError(history_id)
    return item


def _delete_history_item(db: Session, user_id: str, history_id: str) -> dict:
    deleted = delete_search_history_item(db, user_id, history_id)
    if not deleted:
        raise LookupError(history_id)
    return {"status": "deleted", "id": history_id}
