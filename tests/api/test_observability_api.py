from __future__ import annotations

from datetime import datetime, timezone
import uuid

from AINDY.db.models import AgentEvent, AgentRun
from AINDY.db.models.flow_run import FlowRun
from AINDY.db.models.request_metric import RequestMetric
from AINDY.db.models.system_event import SystemEvent
from AINDY.db.models.system_health_log import SystemHealthLog


def _unwrap(payload):
    if isinstance(payload, dict) and "data" in payload:
        return payload["data"]
    return payload


def test_observability_requires_auth(client):
    response = client.get("/platform/observability/requests")

    assert response.status_code == 401


def test_observability_requests_returns_real_db_summary(
    client,
    db_session,
    test_user,
    auth_headers,
):
    db_session.add(
        RequestMetric(
            request_id="req-1",
            trace_id="trace-1",
            user_id=test_user.id,
            method="GET",
            path="/health",
            status_code=200,
            duration_ms=12.5,
            created_at=datetime.now(timezone.utc),
        )
    )
    db_session.add(
        RequestMetric(
            request_id="req-2",
            trace_id="trace-2",
            user_id=test_user.id,
            method="POST",
            path="/memory/execute",
            status_code=500,
            duration_ms=48.0,
            created_at=datetime.now(timezone.utc),
        )
    )
    db_session.commit()

    response = client.get("/platform/observability/requests", headers=auth_headers)

    assert response.status_code == 200

    payload = response.json()
    data = _unwrap(payload)

    assert data["summary"]["total_requests"] == 2
    assert data["summary"]["total_errors"] == 1
    assert data["summary"]["window_requests"] == 2
    assert data["summary"]["window_errors"] == 1
    assert data["summary"]["avg_latency_ms"] == 30.25

    assert len(data["recent"]) == 2
    assert len(data["recent_errors"]) == 1
    assert data["recent_errors"][0]["trace_id"] == "trace-2"


def test_observability_dashboard_returns_real_db_sections(
    client,
    db_session,
    test_user,
    auth_headers,
):
    run_id = uuid.uuid4()
    trace_id = str(uuid.uuid4())

    db_session.add(
        AgentRun(
            id=run_id,
            user_id=test_user.id,
            agent_type="default",
            goal="observability dashboard fixture",
            plan={"steps": []},
            executive_summary="observability dashboard fixture",
            overall_risk="low",
            status="completed",
            steps_total=0,
            steps_completed=0,
            correlation_id=f"run_{uuid.uuid4()}",
            trace_id=trace_id,
            created_at=datetime.now(timezone.utc),
        )
    )
    db_session.flush()

    db_session.add(
        RequestMetric(
            request_id="req-3",
            trace_id=trace_id,
            user_id=test_user.id,
            method="GET",
            path="/apps/agent/tools",
            status_code=200,
            duration_ms=20.0,
            created_at=datetime.now(timezone.utc),
        )
    )
    db_session.add(
        SystemEvent(
            type="loop.decision",
            user_id=test_user.id,
            trace_id=trace_id,
            payload={"next_action": "continue"},
            timestamp=datetime.now(timezone.utc),
        )
    )
    db_session.add(
        AgentEvent(
            run_id=run_id,
            correlation_id=trace_id,
            user_id=test_user.id,
            event_type="COMPLETED",
            payload={"status": "ok"},
            occurred_at=datetime.now(timezone.utc),
        )
    )
    db_session.add(
        SystemHealthLog(
            status="healthy",
            components={"database": "connected"},
            api_endpoints={"health": {"status": "ok"}},
            avg_latency_ms=11.5,
            timestamp=datetime.now(timezone.utc),
        )
    )
    db_session.add(
        FlowRun(
            id=str(uuid.uuid4()),
            trace_id=trace_id,
            flow_name="watcher_ingest",
            workflow_type="watcher",
            state={"accepted": 1},
            status="running",
            current_node="persist",
            user_id=test_user.id,
            created_at=datetime.now(timezone.utc),
        )
    )
    db_session.commit()

    response = client.get("/platform/observability/dashboard", headers=auth_headers)

    assert response.status_code == 200

    payload = response.json()
    data = _unwrap(payload)

    assert data["summary"]["window_requests"] == 1
    assert data["summary"]["window_errors"] == 0
    assert data["summary"]["loop_events"] == 1
    assert data["summary"]["agent_events"] == 1
    assert data["summary"]["system_event_total"] == 1
    assert data["summary"]["health_status"] == "healthy"

    assert data["loop_activity"][0]["type"] == "loop.decision"
    assert data["agent_timeline"][0]["event_type"] == "COMPLETED"
    assert data["system_events"]["counts"]["loop.decision"] == 1
    assert data["system_health"]["latest"]["status"] == "healthy"
    assert data["flows"]["status_counts"]["running"] == 1
    assert data["flows"]["recent"][0]["trace_id"] == trace_id
