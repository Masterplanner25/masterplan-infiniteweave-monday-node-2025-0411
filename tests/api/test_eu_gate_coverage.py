from __future__ import annotations

from unittest.mock import MagicMock, patch


def _assert_non_null_eu_id(body: dict) -> None:
    envelope = body.get("execution_envelope") or {}
    assert envelope.get("eu_id") is not None, (
        f"execution_envelope.eu_id is None in response: {body}"
    )


class TestGoalsEUGate:
    def test_list_goals_response_contains_eu_id(self, client, auth_headers):
        with patch("AINDY.core.execution_gate.require_execution_unit") as mock_eu:
            mock_eu.return_value = MagicMock(id="test-eu-id-goals")
            with patch(
                "AINDY.runtime.flow_engine.run_flow",
                return_value={"status": "SUCCESS", "data": {"goals": []}},
            ):
                response = client.get("/goals", headers=auth_headers)

        assert response.status_code == 200
        _assert_non_null_eu_id(response.json())


class TestResearchEUGate:
    def test_list_research_response_contains_eu_id(self, client, auth_headers):
        with patch("AINDY.core.execution_gate.require_execution_unit") as mock_eu:
            mock_eu.return_value = MagicMock(id="test-eu-id-research")
            with patch(
                "AINDY.runtime.flow_engine.run_flow",
                return_value={"status": "SUCCESS", "data": {"results": []}},
            ):
                response = client.get("/research/", headers=auth_headers)

        assert response.status_code == 200
        _assert_non_null_eu_id(response.json())


class TestLeadGenEUGate:
    def test_list_leads_response_contains_eu_id(self, client, auth_headers):
        with patch("AINDY.core.execution_gate.require_execution_unit") as mock_eu:
            mock_eu.return_value = MagicMock(id="test-eu-id-leadgen")
            with patch(
                "apps.search.services.leadgen_service.list_leads",
                return_value={"results": []},
            ):
                response = client.get("/leadgen/", headers=auth_headers)

        assert response.status_code == 200
        _assert_non_null_eu_id(response.json())


class TestFreelanceEUGate:
    def test_list_orders_response_contains_eu_id(self, client, auth_headers):
        with patch("AINDY.core.execution_gate.require_execution_unit") as mock_eu:
            mock_eu.return_value = MagicMock(id="test-eu-id-freelance")
            with patch(
                "AINDY.runtime.flow_engine.run_flow",
                return_value={"status": "SUCCESS", "data": {"orders": []}},
            ):
                response = client.get("/freelance/orders", headers=auth_headers)

        assert response.status_code == 200
        _assert_non_null_eu_id(response.json())
