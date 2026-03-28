from __future__ import annotations

import pathlib
import uuid
from datetime import datetime, timezone
from unittest.mock import patch

from db.models.automation_log import AutomationLog
from db.models.flow_run import FlowHistory, FlowRun


def _seed_flow_run(db_session, *, user_id, status="running", waiting_for=None) -> FlowRun:
    run = FlowRun(
        id=str(uuid.uuid4()),
        flow_name="generated_memory_execution",
        workflow_type="memory_execution",
        status=status,
        state={"trace_id": str(uuid.uuid4())},
        current_node="memory_execution_run",
        waiting_for=waiting_for,
        trace_id=str(uuid.uuid4()),
        user_id=user_id,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)
    return run


def _seed_automation_log(db_session, *, user_id, status="failed") -> AutomationLog:
    log = AutomationLog(
        id=str(uuid.uuid4()),
        user_id=user_id,
        source="agent",
        task_name="agent.run",
        payload={"goal": "test"},
        status=status,
        result=None,
    )
    db_session.add(log)
    db_session.commit()
    db_session.refresh(log)
    return log


class TestFlowRunsEndpoints:
    def test_list_runs_requires_auth(self, client):
        assert client.get("/flows/runs").status_code == 401

    def test_get_run_requires_auth(self, client):
        assert client.get("/flows/runs/test-id").status_code == 401

    def test_history_requires_auth(self, client):
        assert client.get("/flows/runs/test-id/history").status_code == 401

    def test_resume_requires_auth(self, client):
        assert client.post("/flows/runs/test-id/resume", json={"event_type": "test"}).status_code == 401

    def test_registry_requires_auth(self, client):
        assert client.get("/flows/registry").status_code == 401

    def test_list_runs_returns_shape(self, client, auth_headers, db_session, test_user):
        _seed_flow_run(db_session, user_id=test_user.id, status="success")

        response = client.get("/flows/runs", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert "runs" in data
        assert "count" in data
        assert isinstance(data["runs"], list)
        assert data["count"] == 1

    def test_list_runs_status_filter(self, client, auth_headers, db_session, test_user):
        _seed_flow_run(db_session, user_id=test_user.id, status="running")
        _seed_flow_run(db_session, user_id=test_user.id, status="waiting", waiting_for="user_approval")

        for status in ["running", "waiting", "success", "failed"]:
            response = client.get(f"/flows/runs?status={status}", headers=auth_headers)
            assert response.status_code == 200

    def test_resume_wrong_event_type_rejected(self, client, auth_headers, db_session, test_user):
        run = _seed_flow_run(
            db_session,
            user_id=test_user.id,
            status="waiting",
            waiting_for="user_approval",
        )

        response = client.post(
            f"/flows/runs/{run.id}/resume",
            json={"event_type": "wrong_event", "payload": {}},
            headers=auth_headers,
        )

        assert response.status_code == 400

    def test_resume_non_waiting_rejected(self, client, auth_headers, db_session, test_user):
        run = _seed_flow_run(db_session, user_id=test_user.id, status="success")

        response = client.post(
            f"/flows/runs/{run.id}/resume",
            json={"event_type": "test"},
            headers=auth_headers,
        )

        assert response.status_code == 400

    def test_registry_returns_shape(self, client, auth_headers):
        response = client.get("/flows/registry", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert "flows" in data
        assert "nodes" in data
        assert "flow_count" in data
        assert "node_count" in data

    def test_get_run_returns_persisted_state(self, client, auth_headers, db_session, test_user):
        run = _seed_flow_run(db_session, user_id=test_user.id, status="waiting", waiting_for="approval")

        response = client.get(f"/flows/runs/{run.id}", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == run.id
        assert data["status"] == "waiting"
        assert data["waiting_for"] == "approval"

    def test_history_returns_node_entries(self, client, auth_headers, db_session, test_user):
        run = _seed_flow_run(db_session, user_id=test_user.id, status="success")
        history = FlowHistory(
            id=str(uuid.uuid4()),
            flow_run_id=run.id,
            node_name="memory_execution_run",
            status="SUCCESS",
            input_state={"workflow": "analysis"},
            output_patch={"result": {"ok": True}},
            execution_time_ms=10,
        )
        db_session.add(history)
        db_session.commit()

        response = client.get(f"/flows/runs/{run.id}/history", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["run_id"] == run.id
        assert data["node_count"] == 1
        assert data["history"][0]["node_name"] == "memory_execution_run"


class TestAutomationEndpoints:
    def test_logs_requires_auth(self, client):
        assert client.get("/automation/logs").status_code == 401

    def test_scheduler_status_requires_auth(self, client):
        assert client.get("/automation/scheduler/status").status_code == 401

    def test_replay_requires_auth(self, client):
        assert client.post("/automation/logs/test-id/replay").status_code == 401

    def test_logs_returns_shape(self, client, auth_headers, db_session, test_user):
        _seed_automation_log(db_session, user_id=test_user.id, status="failed")

        response = client.get("/automation/logs", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert "logs" in data
        assert "count" in data
        assert data["count"] == 1

    def test_logs_status_filter(self, client, auth_headers, db_session, test_user):
        _seed_automation_log(db_session, user_id=test_user.id, status="failed")
        _seed_automation_log(db_session, user_id=test_user.id, status="success")

        for status in ["pending", "running", "success", "failed", "retrying"]:
            response = client.get(f"/automation/logs?status={status}", headers=auth_headers)
            assert response.status_code == 200

    def test_replay_success_log_rejected(self, client, auth_headers, db_session, test_user):
        log = _seed_automation_log(db_session, user_id=test_user.id, status="success")

        response = client.post(f"/automation/logs/{log.id}/replay", headers=auth_headers)

        assert response.status_code == 400

    def test_scheduler_status_returns_shape(self, client, auth_headers):
        class _Job:
            id = "job-1"
            name = "Heartbeat"
            next_run_time = datetime.now(timezone.utc)
            trigger = "interval[0:01:00]"

        class _Scheduler:
            running = False

            @staticmethod
            def get_jobs():
                return [_Job()]

        with patch("services.scheduler_service.get_scheduler", return_value=_Scheduler()):
            response = client.get("/automation/scheduler/status", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert "running" in data
        assert "jobs" in data
        assert "job_count" in data
        assert data["job_count"] == 1


class TestFlowConsoleAPIFunctions:
    def test_api_functions_present(self):
        api_src = pathlib.Path("client/src/api.js").read_text(encoding="utf-8")

        required_fns = [
            "getFlowRuns",
            "getFlowRun",
            "getFlowRunHistory",
            "resumeFlowRun",
            "getFlowRegistry",
            "getAutomationLogs",
            "getAutomationLog",
            "replayAutomationLog",
            "getSchedulerStatus",
        ]

        for fn in required_fns:
            assert fn in api_src, f"Missing API function: {fn}"

    def test_components_exist(self):
        assert pathlib.Path("client/src/components/FlowEngineConsole.jsx").exists()
