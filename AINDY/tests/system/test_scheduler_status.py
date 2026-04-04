from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from db.models.background_task_lease import BackgroundTaskLease


class TestIsBackgroundLeader:
    def test_returns_false_when_no_owner(self):
        import domain.task_services as ts

        original = ts._BACKGROUND_OWNER_ID
        try:
            ts._BACKGROUND_OWNER_ID = None
            assert ts.is_background_leader() is False
        finally:
            ts._BACKGROUND_OWNER_ID = original

    def test_returns_true_when_owner_matches_instance(self):
        import domain.task_services as ts

        original = ts._BACKGROUND_OWNER_ID
        try:
            instance_id = ts._get_instance_id()
            ts._BACKGROUND_OWNER_ID = instance_id
            assert ts.is_background_leader() is True
        finally:
            ts._BACKGROUND_OWNER_ID = original


class TestSchedulerStatusEndpoint:
    def test_returns_200_and_required_keys(self, client, auth_headers):
        with patch("platform_layer.scheduler_service.get_scheduler", side_effect=RuntimeError("not started")), patch(
            "domain.task_services.is_background_leader", return_value=False
        ):
            response = client.get("/observability/scheduler/status", headers=auth_headers)

        assert response.status_code == 200
        payload = response.json()
        data = payload.get("data", payload)
        assert "scheduler_running" in data
        assert "is_leader" in data
        assert "lease" in data
        assert data["scheduler_running"] is False
        assert data["lease"] is None

    def test_reports_running_scheduler_and_serialized_lease(
        self,
        client,
        db_session,
        auth_headers,
    ):
        import domain.task_services as task_services

        lease = BackgroundTaskLease(
            name=task_services._BACKGROUND_LEASE_NAME,
            owner_id="leader-1",
            acquired_at=datetime.now(timezone.utc),
            heartbeat_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        )
        db_session.add(lease)
        db_session.commit()

        class _Scheduler:
            running = True

        with patch("platform_layer.scheduler_service.get_scheduler", return_value=_Scheduler()), patch(
            "domain.task_services.is_background_leader", return_value=True
        ):
            response = client.get("/observability/scheduler/status", headers=auth_headers)

        assert response.status_code == 200
        payload = response.json()
        data = payload.get("data", payload)
        assert data["scheduler_running"] is True
        assert data["is_leader"] is True
        assert data["lease"]["owner_id"] == "leader-1"
        assert data["lease"]["expires_at"] is not None


