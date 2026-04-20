from apps.automation.flows._flow_registration import register_nodes, register_single_node_flows


def leadgen_list_node(state, context):
    try:
        import uuid
        from apps.search.models.leadgen_model import LeadGenResult
        from apps.search.schemas.leadgen_schema import LeadGenItem

        db = context.get("db")
        user_id = uuid.UUID(str(context.get("user_id")))
        results = (
            db.query(LeadGenResult)
            .filter(LeadGenResult.user_id == user_id)
            .order_by(LeadGenResult.created_at.desc())
            .all()
        )
        data = [
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
            for r in results
        ]
        return {"status": "SUCCESS", "output_patch": {"leadgen_list_result": data}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def leadgen_preview_search_node(state, context):
    try:
        from apps.search.services.search_service import search_leads

        db = context.get("db")
        user_id = context.get("user_id")
        query = state.get("query", "")
        result = search_leads(query, db=db, user_id=user_id)
        return {"status": "SUCCESS", "output_patch": {"leadgen_preview_search_result": result}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def research_create_node(state, context):
    try:
        from apps.search.schemas.research_results_schema import ResearchResultCreate
        from apps.search.services import research_results_service

        db = context.get("db")
        user_id = str(context.get("user_id"))
        result_obj = ResearchResultCreate(**state.get("result", {}))
        created = research_results_service.create_research_result(db, result_obj, user_id=user_id)

        def _payload(r):
            d = getattr(r, "data", None)
            return {
                "id": r.id, "query": r.query, "summary": r.summary, "source": r.source, "data": d,
                "created_at": r.created_at.isoformat() if getattr(r, "created_at", None) else None,
                "search_score": d.get("search_score") if isinstance(d, dict) else None,
            }

        return {"status": "SUCCESS", "output_patch": {"research_create_result": {"data": _payload(created)}}}
    except Exception as e:
        return {"status": "FAILURE", "error": f"HTTP_500:Failed to create research result: {e}"}


def research_list_node(state, context):
    try:
        from apps.search.services import research_results_service

        db = context.get("db")
        user_id = str(context.get("user_id"))
        items = research_results_service.get_all_research_results(db, user_id=user_id)

        def _payload(r):
            d = getattr(r, "data", None)
            return {
                "id": r.id, "query": r.query, "summary": r.summary, "source": r.source, "data": d,
                "created_at": r.created_at.isoformat() if getattr(r, "created_at", None) else None,
                "search_score": d.get("search_score") if isinstance(d, dict) else None,
            }

        return {"status": "SUCCESS", "output_patch": {"research_list_result": [_payload(i) for i in items]}}
    except Exception as e:
        return {"status": "FAILURE", "error": f"HTTP_500:Failed to load research results: {e}"}


def research_query_node(state, context):
    try:
        import time as _time
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO
        from AINDY.runtime.memory import MemoryOrchestrator
        from apps.search.schemas.research_results_schema import ResearchResultCreate
        from apps.search.services import research_results_service
        from apps.search.services.search_service import unified_query

        db = context.get("db")
        user_id = str(context.get("user_id"))
        query_str = state.get("query", "")
        summary_hint = state.get("summary", "")
        start = _time.perf_counter()
        memory_context = None
        try:
            orchestrator = MemoryOrchestrator(MemoryNodeDAO)
            memory_context = orchestrator.get_context(
                user_id=user_id, query=query_str, task_type="analysis", db=db,
                max_tokens=400, metadata={"tags": ["research", "insight"], "node_type": "insight", "limit": 3},
            )
        except Exception:
            memory_context = None
        unified = unified_query(query_str, db=db, user_id=user_id)
        summary = unified.get("summary") or summary_hint
        source = unified.get("source")
        raw_excerpt = unified.get("raw_excerpt")
        search_score = unified.get("search_score") or 0.0
        data = {}
        if memory_context and memory_context.items:
            data = {"memory_context_ids": memory_context.ids, "memory_context": memory_context.formatted}
        data.update({
            "search_score": search_score, "raw_excerpt": raw_excerpt, "source": source,
            "memory_context_count": len(memory_context.items) if memory_context else 0,
        })
        created = research_results_service.create_research_result(
            db, ResearchResultCreate(query=query_str, summary=summary),
            user_id=user_id, data=data, source=source or "research_query",
        )
        duration_ms = (_time.perf_counter() - start) * 1000
        d = getattr(created, "data", None)
        payload = {
            "id": created.id, "query": created.query, "summary": created.summary,
            "source": created.source, "data": d,
            "created_at": created.created_at.isoformat() if getattr(created, "created_at", None) else None,
            "search_score": d.get("search_score") if isinstance(d, dict) else None,
            "_execution_meta": {
                "research_id": str(created.id),
                "duration_ms": round(duration_ms, 2),
                "search_score": search_score,
            },
        }
        return {"status": "SUCCESS", "output_patch": {"research_query_result": {"data": payload}}}
    except Exception as e:
        return {"status": "FAILURE", "error": f"HTTP_500:Research query failed: {e}"}


def search_history_list_node(state, context):
    try:
        from apps.search.services.search_service import get_search_history

        db = context.get("db")
        user_id = str(context.get("user_id"))
        limit = state.get("limit", 25)
        search_type = state.get("search_type")
        items = get_search_history(db, user_id, limit=limit, search_type=search_type)

        def _h(item):
            p = dict(item.result or {})
            return {
                "id": item.id, "query": item.query, "result": p,
                "search_type": p.get("search_type"),
                "created_at": item.created_at.isoformat() if getattr(item, "created_at", None) else None,
            }

        return {"status": "SUCCESS", "output_patch": {"search_history_list_result": {
            "count": len(items), "items": [_h(i) for i in items],
        }}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def search_history_get_node(state, context):
    try:
        from apps.search.services.search_service import get_search_history_item

        db = context.get("db")
        user_id = str(context.get("user_id"))
        history_id = state.get("history_id")
        item = get_search_history_item(db, user_id, history_id)
        if not item:
            return {"status": "FAILURE", "error": "HTTP_404:Search history item not found"}
        p = dict(item.result or {})
        return {"status": "SUCCESS", "output_patch": {"search_history_get_result": {
            "id": item.id, "query": item.query, "result": p,
            "search_type": p.get("search_type"),
            "created_at": item.created_at.isoformat() if getattr(item, "created_at", None) else None,
        }}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def search_history_delete_node(state, context):
    try:
        from apps.search.services.search_service import delete_search_history_item

        db = context.get("db")
        user_id = str(context.get("user_id"))
        history_id = state.get("history_id")
        deleted = delete_search_history_item(db, user_id, history_id)
        if not deleted:
            return {"status": "FAILURE", "error": "HTTP_404:Search history item not found"}
        return {"status": "SUCCESS", "output_patch": {"search_history_delete_result": {
            "status": "deleted", "id": history_id,
        }}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def register() -> None:
    register_nodes(
        {
            "leadgen_list_node": leadgen_list_node,
            "leadgen_preview_search_node": leadgen_preview_search_node,
            "research_create_node": research_create_node,
            "research_list_node": research_list_node,
            "research_query_node": research_query_node,
            "search_history_list_node": search_history_list_node,
            "search_history_get_node": search_history_get_node,
            "search_history_delete_node": search_history_delete_node,
        }
    )
    register_single_node_flows(
        {
            "leadgen_list": "leadgen_list_node",
            "leadgen_preview_search": "leadgen_preview_search_node",
            "research_create": "research_create_node",
            "research_list": "research_list_node",
            "research_query": "research_query_node",
            "search_history_list": "search_history_list_node",
            "search_history_get": "search_history_get_node",
            "search_history_delete": "search_history_delete_node",
        }
    )
