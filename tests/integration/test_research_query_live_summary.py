def test_research_query_uses_execution_pipeline(client, auth_headers, monkeypatch):
    monkeypatch.setattr(
        "AINDY.runtime.flow_engine.run_flow",
        lambda *args, **kwargs: {
            "status": "SUCCESS",
            "data": {
                "query": "test",
                "summary": "Summarized content",
                "source": "web_search",
                "search_score": 1.0,
            },
        },
    )

    response = client.post(
        "/research/query",
        json={"query": "test", "summary": "fallback"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"] == "Summarized content"
    assert "search_score" in payload
    assert payload["execution_envelope"]["eu_id"] is not None

