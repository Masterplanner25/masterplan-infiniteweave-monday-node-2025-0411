def test_research_query_uses_ai_analyze(monkeypatch):
    from AINDY.routes.research_results_router import run_research_query
    from AINDY.schemas.research_results_schema import ResearchResultCreate

    def _fake_web_search(query: str) -> str:
        return "Raw search content"

    def _fake_ai_analyze(content: str) -> str:
        return "Summarized content"

    monkeypatch.setattr("AINDY.routes.research_results_router.web_search", _fake_web_search)
    monkeypatch.setattr("AINDY.routes.research_results_router.ai_analyze", _fake_ai_analyze)
    monkeypatch.setattr("AINDY.db.dao.memory_node_dao.MemoryNodeDAO.recall", lambda *args, **kwargs: [])

    class _DB:
        def add(self, _):
            pass

        def commit(self):
            pass

        def refresh(self, _):
            pass

    class _Result:
        def __init__(self, query, summary, source=None, data=None):
            self.id = 1
            self.query = query
            self.summary = summary
            self.source = source
            self.data = data
            from datetime import datetime
            self.created_at = datetime.utcnow()

    def _fake_create(db, result, user_id=None, data=None, source=None):
        return _Result(result.query, result.summary, source=source, data=data)

    monkeypatch.setattr(
        "AINDY.domain.research_results_service.create_research_result",
        _fake_create,
    )

    result = run_research_query(
        request=ResearchResultCreate(query="test", summary="fallback"),
        db=_DB(),
        current_user={"sub": "00000000-0000-0000-0000-000000000001"},
    )
    assert result["summary"] == "Summarized content"
    assert "search_score" in result

