from AINDY.domain.leadgen_service import run_ai_search, _extract_leads_from_text, _extract_leads_from_response


def test_extract_leads_from_text_parses_urls():
    text = "Find vendors https://example.com and https://foo.bar/path for outreach."
    leads = _extract_leads_from_text(text, max_results=2)
    assert len(leads) == 2
    assert leads[0]["url"].startswith("https://")
    assert leads[0]["company"]


def test_extract_leads_from_response_parses_structured_results():
    payload = {
        "results": [
            {"title": "Acme AI", "url": "https://acmeai.com", "snippet": "Hiring ML engineers"},
            {"title": "Finovate Labs", "url": "https://finovatelabs.io", "snippet": "Automation tools"},
        ]
    }
    leads = _extract_leads_from_response(payload, max_results=2)
    assert len(leads) == 2
    assert leads[0]["url"] == "https://acmeai.com"


def test_run_ai_search_uses_external_search(monkeypatch):
    def _fake_search(query: str) -> str:
        return '{"results":[{"title":"Example","url":"https://example.com","snippet":"Best fit"}]}'

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


def test_search_scoring_for_leads():
    from AINDY.analytics.search_scoring import score_lead_result

    score = score_lead_result(overall_score=80)
    assert 0.0 <= score <= 1.0
    assert score > 0.5


def test_search_scoring_for_seo():
    from AINDY.analytics.search_scoring import score_seo_result

    score = score_seo_result(readability=80, avg_keyword_density=2.0, word_count=800)
    assert 0.0 <= score <= 1.0


def test_search_scoring_for_research():
    from AINDY.analytics.search_scoring import score_research_result

    score = score_research_result(summary="A" * 600, memory_context_count=2)
    assert 0.0 <= score <= 1.0

