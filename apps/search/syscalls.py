"""Search domain syscall handlers."""
from __future__ import annotations

import logging

from AINDY.kernel.syscall_registry import SyscallContext, register_syscall

logger = logging.getLogger(__name__)


def _session_from_context(ctx: SyscallContext):
    from AINDY.db.database import SessionLocal

    external_db = ctx.metadata.get("_db")
    if external_db is not None:
        return external_db, False
    return SessionLocal(), True


def _handle_leadgen_search(payload: dict, ctx: SyscallContext) -> dict:
    from apps.search.services.leadgen_service import create_lead_results

    query = payload.get("query", "")
    if not query:
        raise ValueError("sys.v1.leadgen.search requires 'query'")

    db, owns_session = _session_from_context(ctx)
    try:
        raw = create_lead_results(db, query, user_id=ctx.user_id)
        serialized = [
            {
                "company": row.company,
                "url": row.url,
                "fit_score": row.fit_score,
                "intent_score": row.intent_score,
                "data_quality_score": row.data_quality_score,
                "overall_score": row.overall_score,
                "reasoning": row.reasoning,
                "search_score": search_score,
                "created_at": (
                    row.created_at.isoformat()
                    if hasattr(row.created_at, "isoformat")
                    else str(row.created_at or "")
                ),
            }
            for row, search_score in raw
        ]
        return {"search_results": serialized, "count": len(serialized)}
    finally:
        if owns_session:
            db.close()


def _handle_leadgen_search_ai(payload: dict, ctx: SyscallContext) -> dict:
    from apps.search.services.leadgen_service import run_ai_search

    query = payload.get("query", "")
    if not query:
        raise ValueError("sys.v1.leadgen.search_ai requires 'query'")

    db, owns_session = _session_from_context(ctx)
    try:
        leads = run_ai_search(query=query, user_id=ctx.user_id, db=db)
        return {"leads": leads, "count": len(leads)}
    finally:
        if owns_session:
            db.close()


def _handle_leadgen_store(payload: dict, ctx: SyscallContext) -> dict:
    from AINDY.core.execution_signal_helper import queue_memory_capture
    from apps.search.services.search_service import persist_search_result

    query: str = payload.get("query", "")
    results: list = payload.get("results") or []

    db, owns_session = _session_from_context(ctx)
    try:
        if ctx.user_id and results:
            queue_memory_capture(
                db=db,
                user_id=ctx.user_id,
                agent_namespace="leadgen",
                event_type="leadgen_search",
                content=f"LeadGen '{query[:80]}': {len(results)} results",
                source="flow_engine:leadgen",
                tags=["leadgen", "search", "outcome"],
            )

        if ctx.user_id and query and results:
            try:
                persist_search_result(
                    db=db,
                    user_id=ctx.user_id,
                    query=query,
                    result={"query": query, "count": len(results), "results": results},
                    search_type="leadgen",
                )
            except Exception as exc:
                logger.warning("[sys.v1.leadgen.store] cache persist failed (non-fatal): %s", exc)

        return {"stored": True, "count": len(results)}
    finally:
        if owns_session:
            db.close()


def _handle_research_query(payload: dict, ctx: SyscallContext) -> dict:
    from apps.search.services.research_engine import web_search

    query = payload.get("query", "")
    if not query:
        raise ValueError("sys.v1.research.query requires 'query'")

    raw = web_search(query)
    return {"raw_result": raw[:2000] if raw else ""}


def register_search_syscall_handlers() -> None:
    register_syscall(
        name="sys.v1.leadgen.search",
        handler=_handle_leadgen_search,
        capability="leadgen.search",
        description="B2B lead search via create_lead_results.",
        stable=False,
    )
    register_syscall(
        name="sys.v1.leadgen.search_ai",
        handler=_handle_leadgen_search_ai,
        capability="leadgen.search_ai",
        description="AI-powered B2B lead search.",
        stable=False,
    )
    register_syscall(
        name="sys.v1.leadgen.store",
        handler=_handle_leadgen_store,
        capability="leadgen.store",
        description="Persist leadgen results to memory bridge and search cache.",
        stable=False,
    )
    register_syscall(
        name="sys.v1.research.query",
        handler=_handle_research_query,
        capability="research.query",
        description="Web research query.",
        stable=False,
    )
