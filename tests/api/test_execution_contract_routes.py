from __future__ import annotations


def _assert_execution_envelope(payload: dict) -> None:
    envelope = payload.get("execution_envelope")
    assert isinstance(envelope, dict)
    for key in (
        "eu_id",
        "trace_id",
        "status",
        "output",
        "error",
        "duration_ms",
        "attempt_count",
    ):
        assert key in envelope
    assert envelope["eu_id"] is not None
    assert envelope["status"] == "SUCCESS"


def test_goals_create_route_runs_through_execution_pipeline(client, auth_headers, monkeypatch):
    monkeypatch.setattr(
        "AINDY.runtime.flow_engine.run_flow",
        lambda *args, **kwargs: {
            "status": "SUCCESS",
            "data": {"id": "goal-1", "name": "Ship v1"},
        },
    )

    response = client.post(
        "/goals",
        json={
            "name": "Ship v1",
            "description": "Release goal",
            "goal_type": "strategic",
            "priority": 0.8,
            "status": "active",
            "success_metric": {"target": 1},
        },
        headers=auth_headers,
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["id"] == "goal-1"
    _assert_execution_envelope(payload)


def test_research_query_route_runs_through_execution_pipeline(client, auth_headers, monkeypatch):
    monkeypatch.setattr(
        "AINDY.runtime.flow_engine.run_flow",
        lambda *args, **kwargs: {
            "status": "SUCCESS",
            "data": {
                "query": "market map",
                "summary": "Condensed research",
                "source": "web_search",
            },
        },
    )

    response = client.post(
        "/research/query",
        json={"query": "market map", "summary": "fallback"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["query"] == "market map"
    _assert_execution_envelope(payload)


def test_leadgen_generate_route_runs_through_execution_pipeline(client, auth_headers, monkeypatch):
    monkeypatch.setattr(
        "AINDY.runtime.flow_engine.run_flow",
        lambda *args, **kwargs: {
            "status": "SUCCESS",
            "data": [
                {
                    "company": "Acme",
                    "url": "https://acme.test",
                    "search_score": 0.9,
                }
            ],
        },
    )

    response = client.post("/leadgen/?query=acme", headers=auth_headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["query"] == "acme"
    assert payload["results"][0]["company"] == "Acme"
    _assert_execution_envelope(payload)


def test_freelance_orders_route_runs_through_execution_pipeline(client, auth_headers, monkeypatch):
    monkeypatch.setattr(
        "AINDY.runtime.flow_engine.run_flow",
        lambda *args, **kwargs: {
            "status": "SUCCESS",
            "data": {"orders": []},
        },
    )

    response = client.get("/freelance/orders", headers=auth_headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["orders"] == []
    _assert_execution_envelope(payload)
