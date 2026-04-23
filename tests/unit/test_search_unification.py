from __future__ import annotations

import importlib


def test_execute_durable_search_reuses_cached_result(monkeypatch, persisted_user):
    from apps.search.services import search_service

    cached = {"query": "agency", "results": [{"company": "Acme"}], "history_id": "h-1"}

    monkeypatch.setattr(search_service, "get_cached_search_result", lambda **_: cached)
    monkeypatch.setattr(
        search_service,
        "search_memory",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("search_memory should not run")),
    )

    result = search_service.execute_durable_search(
        db=object(),
        user_id=str(persisted_user.id),
        query="agency",
        search_type="lead_preview",
        memory_tags=["leadgen"],
        builder=lambda _memory: (_ for _ in ()).throw(AssertionError("builder should not run")),
    )

    assert result is cached


def test_research_query_route_uses_execution_pipeline(client, auth_headers, monkeypatch):
    monkeypatch.setattr(
        "AINDY.runtime.flow_engine.run_flow",
        lambda *args, **kwargs: {
            "status": "SUCCESS",
            "data": {
                "query": "durable search",
                "summary": "Shared summary",
                "source": "external_search",
                "search_score": 0.87,
                "learning_context": {
                    "search_type": "research",
                    "history_id": "hist-1",
                    "search_score": 0.87,
                    "memory_count": 2,
                    "memory_ids": ["mem-1", "mem-2"],
                    "recalled_memory": True,
                },
            },
        },
    )

    response = client.post(
        "/research/query",
        json={"query": "durable search", "summary": "fallback"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"] == "Shared summary"
    assert payload["search_score"] == 0.87
    assert payload["learning_context"]["search_type"] == "research"
    assert payload["learning_context"]["memory_count"] == 2
    assert payload["execution_envelope"]["eu_id"] is not None


def test_preview_lead_search_route_uses_shared_search_service(client, auth_headers, monkeypatch):
    import apps.search.services.search_service as _search_service

    captured: dict[str, object] = {}

    def _fake_search_leads(*, query: str, db=None, user_id: str | None = None, max_results: int = 3):
        captured["query"] = query
        captured["user_id"] = user_id
        return {
            "query": query,
            "results": [{"company": "Acme", "url": "https://acme.test", "context": "match"}],
            "memory": {"items": [], "ids": [], "formatted": "", "count": 0},
            "raw_excerpt": "raw",
            "history_id": "lead-1",
            "search_score": 0.63,
            "learning_context": {
                "search_type": "lead_preview",
                "history_id": "lead-1",
                "search_score": 0.63,
                "memory_count": 0,
                "memory_ids": [],
                "recalled_memory": False,
            },
        }

    monkeypatch.setattr(_search_service, "search_leads", _fake_search_leads)

    response = client.get("/leadgen/search", params={"query": "agency"}, headers=auth_headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["query"] == "agency"
    assert payload["results"][0]["company"] == "Acme"
    assert payload["learning_context"]["search_type"] == "lead_preview"
    assert payload["learning_context"]["history_id"] == "lead-1"
    assert captured["query"] == "agency"
    assert captured["user_id"]


def test_seo_analyze_route_uses_shared_search_contract(client, auth_headers, monkeypatch):
    seo_routes = importlib.import_module("apps.search.routes.seo_routes")

    captured: dict[str, object] = {}

    def _fake_analyze(text: str, top_n: int = 10, *, db=None, user_id: str | None = None):
        captured["text"] = text
        captured["top_n"] = top_n
        captured["user_id"] = user_id
        return {
            "readability": 81.0,
            "word_count": 420,
            "keyword_densities": {"ai": 1.2},
            "top_keywords": ["ai"],
            "search_score": 0.91,
            "memory": {"items": [], "ids": [], "formatted": "", "count": 0},
            "learning_context": {
                "search_type": "seo_analysis",
                "history_id": "seo-1",
                "search_score": 0.91,
                "memory_count": 0,
                "memory_ids": [],
                "recalled_memory": False,
            },
        }

    monkeypatch.setattr(seo_routes, "analyze_seo_content", _fake_analyze)

    response = client.post(
        "/seo/analyze",
        json={"text": "search friendly content", "top_n": 4},
        headers=auth_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["readability"] == 81.0
    assert payload["search_score"] == 0.91
    assert payload["learning_context"]["search_type"] == "seo_analysis"
    assert payload["learning_context"]["history_id"] == "seo-1"
    assert payload["execution_envelope"]["eu_id"] is not None
    assert captured["text"] == "search friendly content"
    assert captured["top_n"] == 4
    assert captured["user_id"]


def test_seo_meta_route_persists_history_and_uses_execution_pipeline(
    client,
    auth_headers,
    db_session,
    test_user,
):
    from apps.search.models import SearchHistory

    response = client.post(
        "/seo/meta",
        json={"text": "search friendly content", "limit": 140},
        headers=auth_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["meta_description"]
    assert payload["learning_context"]["search_type"] == "seo_meta"
    assert payload["execution_envelope"]["eu_id"] is not None

    history = (
        db_session.query(SearchHistory)
        .filter(SearchHistory.user_id == test_user.id)
        .order_by(SearchHistory.created_at.desc())
        .first()
    )
    assert history is not None
    assert history.query == "search friendly content"
    assert (history.result or {}).get("search_type") == "seo_meta"
    assert (history.result or {}).get("meta_description") == payload["meta_description"]


def test_legacy_twr_response_exposes_memory_learning_context():
    from apps.analytics.routes.main_router import _legacy_twr_response

    class _Task:
        task_name = "Ship v1"

    payload = _legacy_twr_response(
        task=_Task(),
        infinity_result={
            "score": {
                "master_score": 87.0,
                "metadata": {
                    "memory_context_count": 3,
                    "memory_signal_count": 2,
                },
            },
            "next_action": {"title": "Stabilize routing"},
            "memory_influence": {
                "memory_adjustment": {"reason": "high_impact_failures_detected"},
                "memory_summary": {"signals_considered": 2},
            },
        },
    )

    assert payload["memory_influence"]["memory_adjustment"]["reason"] == "high_impact_failures_detected"
    assert payload["learning_context"]["memory_context_count"] == 3
    assert payload["learning_context"]["memory_signal_count"] == 2
    assert payload["learning_context"]["has_memory_influence"] is True
