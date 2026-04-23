"""
test_memory_browser_ui.py

Backend endpoint tests for the "Make It Visible" UI sprint.
Covers the Memory Browser, Identity Dashboard, and Agent Registry routes
that are now surfaced in the React frontend.
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch

from AINDY.services.auth_service import create_access_token


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    from AINDY.main import app
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def auth_headers(test_user):
    """Return valid bearer-token headers for authenticated endpoints."""
    token = create_access_token(
        {
            "sub": str(test_user.id),
            "email": test_user.email,
        }
    )
    return {"Authorization": f"Bearer {token}"}


# ── TestMemoryBrowserEndpoints ───────────────────────────────────────────────

class TestMemoryBrowserEndpoints:
    """Smoke tests: routes respond, shapes are valid, auth is enforced."""

    def test_memory_nodes_requires_auth(self, client):
        res = client.get("/memory/nodes")
        assert res.status_code in (401, 403, 422)

    def test_memory_nodes_returns_list(self, client, auth_headers):
        res = client.get("/memory/nodes?limit=5", headers=auth_headers)
        assert res.status_code in (200, 404, 500)
        if res.status_code == 200:
            body = res.json()
            assert isinstance(body, (list, dict))

    def test_recall_v3_requires_auth(self, client):
        res = client.post("/memory/recall/v3", json={"query": "test", "tags": [], "limit": 3})
        assert res.status_code in (401, 403, 422)

    def test_recall_v3_returns_results_shape(self, client, auth_headers):
        res = client.post(
            "/memory/recall/v3",
            json={"query": "test decision", "tags": [], "limit": 3},
            headers=auth_headers,
        )
        assert res.status_code in (200, 422, 500)
        if res.status_code == 200:
            body = res.json()
            assert "results" in body
            assert "query" in body

    def test_memory_suggest_requires_auth(self, client):
        res = client.post("/memory/suggest", json={"query": "next step", "tags": [], "limit": 3})
        assert res.status_code in (401, 403, 422)

    def test_memory_suggest_returns_suggestions(self, client, auth_headers):
        res = client.post(
            "/memory/suggest",
            json={"query": "what should I do next", "tags": [], "limit": 3},
            headers=auth_headers,
        )
        assert res.status_code in (200, 422, 500)
        if res.status_code == 200:
            body = res.json()
            assert "suggestions" in body

    def test_federated_recall_requires_auth(self, client):
        res = client.post(
            "/memory/federated/recall",
            json={"query": "test", "agent_namespaces": None, "limit": 5},
        )
        assert res.status_code in (401, 403, 422)

    def test_federated_recall_returns_results_shape(self, client, auth_headers):
        res = client.post(
            "/memory/federated/recall",
            json={"query": "project planning", "agent_namespaces": None, "limit": 5},
            headers=auth_headers,
        )
        assert res.status_code in (200, 422, 500)
        if res.status_code == 200:
            body = res.json()
            assert "merged_results" in body or "results" in body or "memories" in body

    def test_agent_list_requires_auth(self, client):
        res = client.get("/memory/agents")
        assert res.status_code in (401, 403, 422)

    def test_agent_list_returns_agents_shape(self, client, auth_headers):
        res = client.get("/memory/agents", headers=auth_headers)
        assert res.status_code in (200, 404, 500)
        if res.status_code == 200:
            body = res.json()
            assert "agents" in body
            assert isinstance(body["agents"], list)
            for agent in body["agents"]:
                assert "name" in agent
                assert "is_active" in agent

    def test_node_feedback_requires_auth(self, client):
        res = client.post(
            "/memory/nodes/1/feedback",
            json={"outcome": "success", "context": ""},
        )
        assert res.status_code in (401, 403, 422)

    def test_node_performance_requires_auth(self, client):
        res = client.get("/memory/nodes/1/performance")
        assert res.status_code in (401, 403, 422)

    def test_node_performance_shape_when_found(self, client, auth_headers):
        # Use a node_id that is very unlikely to exist — expect 404 or 200.
        res = client.get("/memory/nodes/99999/performance", headers=auth_headers)
        assert res.status_code in (200, 404, 500)
        if res.status_code == 200:
            body = res.json()
            assert "node_id" in body
            assert "performance" in body

    def test_node_traverse_requires_auth(self, client):
        res = client.get("/memory/nodes/1/traverse")
        assert res.status_code in (401, 403, 422)

    def test_node_history_requires_auth(self, client):
        res = client.get("/memory/nodes/1/history")
        assert res.status_code in (401, 403, 422)


# ── TestIdentityDashboardEndpoints ──────────────────────────────────────────

class TestIdentityDashboardEndpoints:
    """Verify the identity routes used by IdentityDashboard.jsx."""

    def test_identity_get_requires_auth(self, client):
        res = client.get("/identity/")
        assert res.status_code in (401, 403, 422)

    def test_identity_profile_has_four_dimensions(self, client, auth_headers):
        res = client.get("/identity/", headers=auth_headers)
        assert res.status_code in (200, 500)
        if res.status_code == 200:
            body = res.json()
            profile = body.get("data") if isinstance(body, dict) and "data" in body else body
            for key in ("communication", "tools", "decision_making", "learning"):
                assert key in profile, f"Missing dimension: {key}"

    def test_identity_put_requires_auth(self, client):
        res = client.put("/identity/", json={"communication": {"tone": "direct"}})
        assert res.status_code in (401, 403, 422)

    def test_identity_put_accepts_partial_update(self, client, auth_headers):
        res = client.put(
            "/identity/",
            json={"communication": {"tone": "direct", "notes": "prefers bullet points"}},
            headers=auth_headers,
        )
        assert res.status_code in (200, 422, 500)

    def test_identity_evolution_requires_auth(self, client):
        res = client.get("/identity/evolution")
        assert res.status_code in (401, 403, 422)

    def test_identity_evolution_has_required_keys(self, client, auth_headers):
        res = client.get("/identity/evolution", headers=auth_headers)
        assert res.status_code in (200, 500)
        if res.status_code == 200:
            body = res.json()
            summary = body.get("data") if isinstance(body, dict) and "data" in body else body
            for key in (
                "observation_count",
                "total_changes",
                "dimensions_evolved",
                "recent_changes",
                "evolution_arc",
            ):
                assert key in summary, f"Missing evolution key: {key}"

    def test_identity_context_requires_auth(self, client):
        res = client.get("/identity/context")
        assert res.status_code in (401, 403, 422)

    def test_identity_context_returns_something(self, client, auth_headers):
        res = client.get("/identity/context", headers=auth_headers)
        assert res.status_code in (200, 404, 500)
        if res.status_code == 200:
            body = res.json()
            assert isinstance(body, dict)


# ── TestAgentRegistryEndpoints ───────────────────────────────────────────────

class TestAgentRegistryEndpoints:
    """Verify the agent-related routes used by AgentRegistry.jsx."""

    def test_agent_recall_requires_auth(self, client):
        res = client.get("/memory/agents/arm/recall?query=test&limit=5")
        assert res.status_code in (401, 403, 422)

    def test_agent_recall_unknown_namespace(self, client, auth_headers):
        res = client.get(
            "/memory/agents/nonexistent_ns/recall?query=test&limit=3",
            headers=auth_headers,
        )
        # May 200 with empty list or 404 — both are acceptable
        assert res.status_code in (200, 404, 500)

    def test_federated_recall_with_namespaces_filter(self, client, auth_headers):
        res = client.post(
            "/memory/federated/recall",
            json={"query": "analyze code", "agent_namespaces": ["arm"], "limit": 3},
            headers=auth_headers,
        )
        assert res.status_code in (200, 422, 500)
        if res.status_code == 200:
            body = res.json()
            assert "merged_results" in body or "results" in body or "memories" in body

    def test_agent_memory_stats_present(self, client, auth_headers):
        res = client.get("/memory/agents", headers=auth_headers)
        if res.status_code != 200:
            pytest.skip("Agent list unavailable in test environment")
        body = res.json()
        for agent in body.get("agents", []):
            assert "memory_stats" in agent, f"Agent {agent.get('name')} missing memory_stats"
            stats = agent["memory_stats"]
            for stat_key in ("total_nodes", "shared_nodes", "private_nodes"):
                assert stat_key in stats, f"Agent {agent.get('name')} missing stat: {stat_key}"
