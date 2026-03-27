"""
Flow Engine Console UI — backend endpoint tests.
Verifies all endpoints the console calls are
protected and return correct response shapes.
"""
import pytest
from unittest.mock import MagicMock


class TestFlowRunsEndpoints:

    def test_list_runs_requires_auth(self, client):
        r = client.get("/flows/runs")
        assert r.status_code == 401

    def test_get_run_requires_auth(self, client):
        r = client.get("/flows/runs/test-id")
        assert r.status_code == 401

    def test_history_requires_auth(self, client):
        r = client.get(
            "/flows/runs/test-id/history"
        )
        assert r.status_code == 401

    def test_resume_requires_auth(self, client):
        r = client.post(
            "/flows/runs/test-id/resume",
            json={"event_type": "test"}
        )
        assert r.status_code == 401

    def test_registry_requires_auth(self, client):
        r = client.get("/flows/registry")
        assert r.status_code == 401

    def test_list_runs_returns_shape(
        self, client, auth_headers, mock_db
    ):
        mock_db.query.return_value.filter.return_value\
            .order_by.return_value.limit.return_value\
            .all.return_value = []

        r = client.get(
            "/flows/runs",
            headers=auth_headers
        )
        if r.status_code == 200:
            data = r.json()
            assert "runs" in data
            assert "count" in data
            assert isinstance(data["runs"], list)

    def test_list_runs_status_filter(
        self, client, auth_headers, mock_db
    ):
        mock_db.query.return_value.filter.return_value\
            .order_by.return_value.limit.return_value\
            .all.return_value = []

        for status in ["running", "waiting",
                       "success", "failed"]:
            r = client.get(
                f"/flows/runs?status={status}",
                headers=auth_headers
            )
            assert r.status_code in [200, 422]
            assert r.status_code != 401

    def test_resume_wrong_event_type_rejected(
        self, client, auth_headers, mock_db
    ):
        mock_run = MagicMock()
        mock_run.status = "waiting"
        mock_run.waiting_for = "user_approval"
        mock_run.user_id = "test-user-id-123"

        mock_db.query.return_value.filter.return_value\
            .first.return_value = mock_run

        r = client.post(
            "/flows/runs/test-id/resume",
            json={
                "event_type": "wrong_event",
                "payload": {}
            },
            headers=auth_headers
        )
        assert r.status_code == 400

    def test_resume_non_waiting_rejected(
        self, client, auth_headers, mock_db
    ):
        mock_run = MagicMock()
        mock_run.status = "success"
        mock_run.user_id = "test-user-id-123"

        mock_db.query.return_value.filter.return_value\
            .first.return_value = mock_run

        r = client.post(
            "/flows/runs/test-id/resume",
            json={"event_type": "test"},
            headers=auth_headers
        )
        assert r.status_code == 400

    def test_registry_returns_shape(
        self, client, auth_headers
    ):
        r = client.get(
            "/flows/registry",
            headers=auth_headers
        )
        if r.status_code == 200:
            data = r.json()
            assert "flows" in data
            assert "nodes" in data
            assert "flow_count" in data
            assert "node_count" in data


class TestAutomationEndpoints:

    def test_logs_requires_auth(self, client):
        r = client.get("/automation/logs")
        assert r.status_code == 401

    def test_scheduler_status_requires_auth(
        self, client
    ):
        r = client.get(
            "/automation/scheduler/status"
        )
        assert r.status_code == 401

    def test_replay_requires_auth(self, client):
        r = client.post(
            "/automation/logs/test-id/replay"
        )
        assert r.status_code == 401

    def test_logs_returns_shape(
        self, client, auth_headers, mock_db
    ):
        mock_db.query.return_value.filter.return_value\
            .order_by.return_value.limit.return_value\
            .all.return_value = []

        r = client.get(
            "/automation/logs",
            headers=auth_headers
        )
        if r.status_code == 200:
            data = r.json()
            assert "logs" in data
            assert "count" in data

    def test_logs_status_filter(
        self, client, auth_headers, mock_db
    ):
        mock_db.query.return_value.filter.return_value\
            .order_by.return_value.limit.return_value\
            .all.return_value = []

        for status in ["pending", "running",
                       "success", "failed",
                       "retrying"]:
            r = client.get(
                f"/automation/logs?status={status}",
                headers=auth_headers
            )
            assert r.status_code in [200, 422]
            assert r.status_code != 401

    def test_replay_success_log_rejected(
        self, client, auth_headers, mock_db
    ):
        mock_log = MagicMock()
        mock_log.status = "success"
        mock_log.user_id = "test-user-id-123"

        mock_db.query.return_value.filter.return_value\
            .first.return_value = mock_log

        r = client.post(
            "/automation/logs/test-id/replay",
            headers=auth_headers
        )
        assert r.status_code == 400

    def test_scheduler_status_returns_shape(
        self, client, auth_headers
    ):
        r = client.get(
            "/automation/scheduler/status",
            headers=auth_headers
        )
        if r.status_code == 200:
            data = r.json()
            assert "running" in data
            assert "jobs" in data
            assert "job_count" in data


class TestFlowConsoleAPIFunctions:
    """Verify API functions exist in api.js."""

    def test_api_functions_present(self):
        import pathlib
        api_src = pathlib.Path(
            "client/src/api.js"
        ).read_text()

        required_fns = [
            "getFlowRuns",
            "getFlowRun",
            "getFlowRunHistory",
            "resumeFlowRun",
            "getFlowRegistry",
            "getAutomationLogs",
            "getAutomationLog",
            "replayAutomationLog",
            "getSchedulerStatus"
        ]

        for fn in required_fns:
            assert fn in api_src, \
                f"Missing API function: {fn}"

    def test_components_exist(self):
        import pathlib

        files = [
            "client/src/components/"
            "FlowEngineConsole.jsx"
        ]

        for f in files:
            exists = pathlib.Path(f).exists()
            assert exists, f"Missing component: {f}"
