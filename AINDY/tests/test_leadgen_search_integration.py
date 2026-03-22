from services.leadgen_service import run_ai_search, _extract_leads_from_text


def test_extract_leads_from_text_parses_urls():
    text = "Find vendors https://example.com and https://foo.bar/path for outreach."
    leads = _extract_leads_from_text(text, max_results=2)
    assert len(leads) == 2
    assert leads[0]["url"].startswith("https://")
    assert leads[0]["company"]


def test_run_ai_search_uses_external_search(monkeypatch):
    def _fake_search(query: str) -> str:
        return "Results: https://example.com Best fit."

    monkeypatch.setattr("modules.research_engine.web_search", _fake_search)
    results = run_ai_search("test query")
    assert results
    assert results[0]["url"] == "https://example.com"


def test_run_ai_search_falls_back_on_error(monkeypatch):
    def _boom(query: str) -> str:
        raise RuntimeError("search down")

    monkeypatch.setattr("modules.research_engine.web_search", _boom)
    results = run_ai_search("test query")
    assert results
    assert all("company" in r and "url" in r and "context" in r for r in results)
