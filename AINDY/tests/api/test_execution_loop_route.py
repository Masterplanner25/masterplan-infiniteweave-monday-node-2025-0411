from __future__ import annotations


def test_memory_execute_route(client, auth_headers):
    response = client.post(
        "/memory/execute",
        headers=auth_headers,
        json={
            "workflow": "analysis",
            "input": {"query": "test"},
            "session_tags": ["test"],
            "recall_before": True,
            "remember_after": True,
            "auto_feedback": True,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    data = payload["data"]
    assert "result" in data
    assert "recalled_memories" in data
    assert "memory_context" in data
